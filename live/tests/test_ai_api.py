"""Tests for the AI Copilot REST endpoints: GET /ai/notes, GET /ai/reports,
POST /ai/reports/{period} (Sprint 6), and GET /ai/intelligence/{correlation_id}
(Sprint 7). Report generation itself (the actual math/prompting) is covered by
test_ai.py, and atlas/intelligence.py's computation is covered in isolation by
test_intelligence.py - these confirm the endpoints wire things up correctly,
including the "202 immediately, generation happens in the background" contract for
reports and the "no Claude call, nothing persisted" contract for intelligence."""
import asyncio
from unittest.mock import patch

import atlas.ai as ai_module
from tests.conftest import entry_payload


def test_list_ai_notes_empty(client):
    resp = client.get("/api/v1/ai/notes")
    assert resp.status_code == 200
    assert resp.json() == {"count": 0, "notes": []}


def test_list_ai_notes_rejects_invalid_note_type(client):
    resp = client.get("/api/v1/ai/notes", params={"note_type": "bogus"})
    assert resp.status_code == 400


def test_trigger_report_returns_202_immediately(client):
    with patch.object(ai_module, "analyze_with_claude", return_value=("Report text.", None)):
        resp = client.post("/api/v1/ai/reports/daily")
    assert resp.status_code == 202
    assert resp.json() == {"ok": True, "status": "generating", "period": "daily"}


def test_trigger_report_rejects_invalid_period(client):
    resp = client.post("/api/v1/ai/reports/monthly")
    assert resp.status_code == 400


def test_trigger_report_actually_generates_and_is_listable(client):
    with patch.object(ai_module, "analyze_with_claude", return_value=("Weekly summary text.", None)):
        # TestClient runs the scheduled background task inline before returning, so
        # the report already exists by the time this call returns.
        client.post("/api/v1/ai/reports/weekly")

    resp = client.get("/api/v1/ai/reports", params={"period": "weekly"})
    body = resp.json()
    assert body["count"] == 1
    assert body["reports"][0]["content"] == "Weekly summary text."


def test_list_reports_rejects_invalid_period(client):
    resp = client.get("/api/v1/ai/reports", params={"period": "monthly"})
    assert resp.status_code == 400


def test_list_reports_with_no_period_combines_both(client):
    with patch.object(ai_module, "analyze_with_claude", return_value=("Daily text.", None)):
        client.post("/api/v1/ai/reports/daily")
    with patch.object(ai_module, "analyze_with_claude", return_value=("Weekly text.", None)):
        client.post("/api/v1/ai/reports/weekly")

    resp = client.get("/api/v1/ai/reports")
    body = resp.json()
    assert body["count"] == 2


# --- GET /ai/intelligence/{correlation_id} (Sprint 7) --------------------------------

async def _seed_closed_trade(repository, correlation_id, outcome):
    async def _forward_ok():
        return True, 200, None

    await repository.claim_and_forward(correlation_id, entry_payload(correlation_id), "{}", _forward_ok)
    realized = 500.0 if outcome == "won" else -300.0
    await repository.update_exit(correlation_id, outcome, 30050, realized, "2026-01-01T00:00:00+00:00")


def test_get_intelligence_404s_for_an_unknown_correlation_id(client):
    resp = client.get("/api/v1/ai/intelligence/never-existed")
    assert resp.status_code == 404


def test_get_intelligence_with_no_history_reports_insufficient_history(client, repository):
    # A historical trade exists, but with a different setup tag - not a match.
    asyncio.run(_seed_closed_trade(repository, "hist-other-setup", "won"))

    with patch.object(ai_module, "analyze_with_claude"):
        client.post("/webhook", json=entry_payload("corr-intel-open", setup_tag="RCL"))

    resp = client.get("/api/v1/ai/intelligence/corr-intel-open")
    assert resp.status_code == 200
    body = resp.json()
    assert body["correlation_id"] == "corr-intel-open"
    assert body["similar_trade_count"] == 0
    assert body["confidence_score"] is None
    assert body["confidence_label"] == "Insufficient History"
    # Factors are always reported (one per measurable field), but with no similar
    # trades there's nothing to compare against - both medians are None.
    assert len(body["factors"]) == 3
    assert all(f["winners_median"] is None and f["losers_median"] is None for f in body["factors"])


def test_get_intelligence_computes_fresh_without_calling_claude_or_persisting(client, repository):
    asyncio.run(_seed_closed_trade(repository, "hist-1", "won"))
    asyncio.run(_seed_closed_trade(repository, "hist-2", "won"))

    with patch.object(ai_module, "analyze_with_claude") as mock_claude:
        client.post("/webhook", json=entry_payload("corr-intel-live"))
    mock_claude.reset_mock()

    with patch.object(ai_module, "analyze_with_claude") as mock_claude_2:
        resp = client.get("/api/v1/ai/intelligence/corr-intel-live")
    mock_claude_2.assert_not_called()  # on-demand computation only, never touches Claude

    assert resp.status_code == 200
    body = resp.json()
    assert body["similar_trade_count"] == 2
    assert body["confidence_score"] is not None
    assert body["summary"]["total_trades"] == 2
    assert len(body["factors"]) == 3

    # Nothing was written as a side effect of this GET - the entry_score note that
    # already existed from the webhook's own background task is untouched, and no new
    # note was added.
    notes = asyncio.run(repository.list_ai_notes(trade_correlation_id="corr-intel-live"))
    assert len(notes) == 1
