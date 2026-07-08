"""
Tests for the live relay's safety properties: order relay must never wait on or
depend on Claude/AI, duplicate webhook deliveries must never cause a duplicate real
order, PickMyTrade failures must be recorded visibly (not hidden as success), and
later lifecycle events must never corrupt the forward status. As of Sprint 6, also
covers that AI entry scoring (on entry) and post-trade review (on exit) are scheduled
as background tasks that can never affect the response.

These are unit tests: they exercise the full request/response path through FastAPI
against the InMemoryTradeRepository test double (see conftest.py), not a real
Postgres. The Postgres-specific concurrency guarantee (the advisory-lock claim) is
covered separately in tests/integration/test_postgres_repository.py against a real
database.
"""
import asyncio
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.v1 import webhook
from tests.conftest import entry_payload


async def _seed_similar_trade(repository, correlation_id, outcome):
    """Seeds one closed trade sharing entry_payload()'s direction/setup_tag (long/BRK)
    so run_entry_score has real historical evidence and actually calls Claude to
    explain it, instead of taking the zero-history "Insufficient History" shortcut -
    see atlas/ai.py::run_entry_score and atlas/intelligence.py."""
    async def _forward_ok():
        return True, 200, None

    await repository.claim_and_forward(correlation_id, entry_payload(correlation_id), "{}", _forward_ok)
    realized = 500.0 if outcome == "won" else -300.0
    await repository.update_exit(correlation_id, outcome, 30050, realized, "2026-01-01T00:00:00+00:00")


def test_normal_webhook_stores_forwards_once_and_scores_the_entry(client, get_trade, get_ai_notes, repository):
    """1. Normal webhook: payload -> stored -> forwarded once -> AI scores it after."""
    asyncio.run(_seed_similar_trade(repository, "hist-1", "won"))
    asyncio.run(_seed_similar_trade(repository, "hist-2", "won"))

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)) as mock_forward, \
         patch.object(ai_module, "analyze_with_claude",
                       return_value=("Looks aligned with the historical winners.", None)) as mock_claude:
        resp = client.post("/webhook", json=entry_payload("corr-normal"))

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["pmt_forwarded"] is True

    mock_forward.assert_called_once()
    mock_claude.assert_called_once()  # ran (as a background task, which TestClient executes inline)

    trade = get_trade("corr-normal")
    assert trade is not None
    assert trade["pmt_forwarded"] is True
    assert trade["pmt_status_code"] == 200
    assert trade["status"] == "open"

    notes = get_ai_notes("corr-normal", note_type="entry_score")
    assert len(notes) == 1
    assert notes[0]["score"] is not None
    assert notes[0]["similar_trade_count"] == 2
    assert notes[0]["content"] == "Looks aligned with the historical winners."


def test_webhook_secret_is_never_persisted_in_raw_entry_payload(client, repository):
    """Sprint 9: the webhook secret must never be stored, even when a valid secret was
    sent - see atlas/api/v1/webhook.py::_sanitize_raw_body. Closes the Sprint 8 audit
    finding that GET /api/v1/trades/{id} (which returns raw_entry_payload unfiltered)
    used to leak the shared secret back out, defeating a correctly-configured one."""
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude"):
        resp = client.post("/webhook", json=entry_payload("corr-sanitize-check"))
    assert resp.status_code == 200

    stored = asyncio.run(repository.get_by_correlation_id("corr-sanitize-check"))
    assert "secret" not in stored["raw_entry_payload"]
    assert "test-secret" not in stored["raw_entry_payload"]
    # Every other field the payload actually carried must still be there - this is
    # sanitization, not truncation.
    assert "corr-sanitize-check" in stored["raw_entry_payload"]
    assert "BRK" in stored["raw_entry_payload"]


def test_duplicate_webhook_does_not_forward_twice(client, get_trade, get_ai_notes, repository):
    """2. Duplicate webhook: same correlation_id arrives again -> no second PickMyTrade forward,
    existing record is left untouched, response clearly flags it as a duplicate."""
    asyncio.run(_seed_similar_trade(repository, "hist-dup-1", "won"))
    asyncio.run(_seed_similar_trade(repository, "hist-dup-2", "won"))

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude", return_value=("first analysis", None)):
        first = client.post("/webhook", json=entry_payload("corr-dup"))
    assert first.status_code == 200

    # Simulate a TradingView retry of the exact same webhook delivery.
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)) as mock_forward_2, \
         patch.object(ai_module, "analyze_with_claude", return_value=("should not run", None)) as mock_claude_2:
        second = client.post("/webhook", json=entry_payload("corr-dup"))

    assert second.status_code == 208
    body = second.json()
    assert body["ok"] is True
    assert body["duplicate_already_forwarded"] is True

    mock_forward_2.assert_not_called()  # the critical assertion: no second real order
    mock_claude_2.assert_not_called()

    notes = get_ai_notes("corr-dup", note_type="entry_score")
    assert len(notes) == 1  # not scored a second time
    assert notes[0]["content"] == "first analysis"  # original record untouched


def test_claude_failure_does_not_block_or_prevent_pickmytrade_forward(client, get_trade):
    """3. AI delay/failure: Claude raises -> PickMyTrade still forwards, response still
    reflects a successful forward, and the failure is confined to the AI note."""
    def claude_raises(*args, **kwargs):
        raise TimeoutError("simulated Claude API timeout")

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)) as mock_forward, \
         patch.object(ai_module, "analyze_with_claude", side_effect=claude_raises):
        resp = client.post("/webhook", json=entry_payload("corr-claude-fail"))

    assert resp.status_code == 200
    assert resp.json()["pmt_forwarded"] is True
    mock_forward.assert_called_once()

    trade = get_trade("corr-claude-fail")
    assert trade["pmt_forwarded"] is True  # order relay succeeded regardless of AI


def test_pickmytrade_failure_is_recorded_and_visible(client, get_trade):
    """4. PickMyTrade failure: forward fails -> database records it clearly, response is a
    distinct non-200 (207) so it is not hidden, and GET /api/v1/trades/{id} (which the
    real frontend reads - the legacy server-rendered HTML dashboard was removed in
    Sprint 9) can show it."""
    with patch.object(webhook, "forward_to_pickmytrade",
                       return_value=(False, None, "connection refused")) as mock_forward, \
         patch.object(ai_module, "analyze_with_claude", return_value=("analysis ran fine", None)):
        resp = client.post("/webhook", json=entry_payload("corr-pmt-fail"))

    assert resp.status_code == 207
    body = resp.json()
    assert body["pmt_forwarded"] is False
    assert body["pmt_error"] == "connection refused"

    trade = get_trade("corr-pmt-fail")
    assert trade["pmt_forwarded"] is False
    assert trade["pmt_error"] == "connection refused"


def test_price_update_and_exit_do_not_corrupt_forward_status(client, get_trade):
    """5. Existing trade update: price_update/exit events must update only their own fields
    and must never touch pmt_forwarded/pmt_status_code/pmt_error."""
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude", return_value=("ok", None)):
        client.post("/webhook", json=entry_payload("corr-lifecycle"))

    price_update_resp = client.post("/webhook", json={
        "type": "price_update", "correlation_id": "corr-lifecycle", "secret": "test-secret",
        "current_price": 30020, "unrealized_pnl": 240,
    })
    assert price_update_resp.status_code == 200

    mid_trade = get_trade("corr-lifecycle")
    assert mid_trade["current_price"] == 30020
    assert mid_trade["unrealized_pnl"] == 240
    assert mid_trade["pmt_forwarded"] is True  # unaffected by the price update
    assert mid_trade["status"] == "open"

    with patch.object(ai_module, "analyze_with_claude", return_value=("Played out fine.", None)):
        exit_resp = client.post("/webhook", json={
            "type": "exit", "correlation_id": "corr-lifecycle", "secret": "test-secret",
            "outcome": "WIN", "exit_price": 30050, "realized_pnl": 600,
        })
    assert exit_resp.status_code == 200

    final_trade = get_trade("corr-lifecycle")
    assert final_trade["status"] == "won"
    assert final_trade["exit_price"] == 30050
    assert final_trade["realized_pnl"] == 600
    assert final_trade["pmt_forwarded"] is True  # still unaffected by the exit
    assert final_trade["pmt_status_code"] == 200


def test_exit_schedules_a_post_trade_review(client, get_ai_notes):
    """New in Sprint 6: closing a trade schedules a post-trade review as a background
    task, same non-blocking discipline as entry scoring."""
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude", return_value=("entry score text", None)):
        client.post("/webhook", json=entry_payload("corr-review"))

    with patch.object(ai_module, "analyze_with_claude", return_value=("This played out as expected.", None)) as mock:
        resp = client.post("/webhook", json={
            "type": "exit", "correlation_id": "corr-review", "secret": "test-secret",
            "outcome": "WIN", "exit_price": 100, "realized_pnl": 500,
        })

    assert resp.status_code == 200  # exit response unaffected by the review running
    mock.assert_called_once()

    reviews = get_ai_notes("corr-review", note_type="post_trade_review")
    assert len(reviews) == 1
    assert reviews[0]["content"] == "This played out as expected."


def test_post_trade_review_failure_does_not_affect_the_exit_response(client):
    """A failing/slow AI review must never surface as an exit-handling error - the
    exit itself already succeeded before the review is even scheduled."""
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude", return_value=("entry score text", None)):
        client.post("/webhook", json=entry_payload("corr-review-fail"))

    def claude_raises(*args, **kwargs):
        raise TimeoutError("simulated timeout")

    with patch.object(ai_module, "analyze_with_claude", side_effect=claude_raises):
        resp = client.post("/webhook", json={
            "type": "exit", "correlation_id": "corr-review-fail", "secret": "test-secret",
            "outcome": "LOSS", "exit_price": 90, "realized_pnl": -100,
        })

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_unknown_correlation_id_price_update_returns_warning_not_error(client):
    """A price_update/exit for a correlation_id that was never an entry must not 500 -
    it should be acknowledged with a warning so TradingView doesn't retry forever."""
    resp = client.post("/webhook", json={
        "type": "price_update", "correlation_id": "never-existed", "secret": "test-secret",
        "current_price": 1, "unrealized_pnl": 1,
    })
    assert resp.status_code == 200
    assert "no trade found" in resp.json()["warning"]


def test_unknown_correlation_id_exit_does_not_schedule_a_review(client):
    """An exit for a correlation_id that doesn't exist has nothing to review."""
    with patch.object(ai_module, "analyze_with_claude") as mock:
        resp = client.post("/webhook", json={
            "type": "exit", "correlation_id": "never-existed", "secret": "test-secret",
            "outcome": "WIN", "exit_price": 1, "realized_pnl": 1,
        })
    assert resp.status_code == 200
    mock.assert_not_called()


def test_bad_secret_is_rejected(client):
    """Sanity check that the webhook secret is still enforced end to end - a payload
    with the wrong secret must be rejected before any DB write or PickMyTrade call."""
    with patch.object(webhook, "forward_to_pickmytrade") as mock_forward:
        resp = client.post("/webhook", json=entry_payload("corr-bad-secret", secret="wrong-secret"))

    assert resp.status_code == 401
    mock_forward.assert_not_called()


def test_missing_correlation_id_is_rejected(client):
    """Sprint 9: schema validation failures (WebhookPayload) return 422, distinct from
    400 (reserved for "not valid JSON at all" - see the malformed-payload tests in
    test_webhook_validation.py)."""
    resp = client.post("/webhook", json={"type": "entry", "secret": "test-secret"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["ok"] is False
    assert any(err.get("loc") == ["correlation_id"] for err in body["details"])
