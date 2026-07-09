"""Tests for the read-only trade endpoints powering the Sprint 2 UI: current
position, trade history, and single-trade detail + derived timeline (which, as of
Sprint 6, includes real AI notes - entry scores and post-trade reviews - not just the
old single-slot legacy analysis field)."""
import asyncio
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.v1 import webhook
from tests.conftest import entry_payload


def _post_entry(client, correlation_id, **overrides):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude", return_value=("looks fine", None)):
        return client.post("/webhook", json=entry_payload(correlation_id, **overrides))


async def _seed_similar_trade(repository, correlation_id):
    """Seeds one closed trade sharing entry_payload()'s direction/setup_tag so
    run_entry_score has historical evidence and actually calls Claude (rather than
    taking the zero-history shortcut where Claude is never invoked at all)."""
    async def _forward_ok():
        return True, 200, None

    await repository.claim_and_forward(correlation_id, entry_payload(correlation_id), "{}", _forward_ok)
    await repository.update_exit(correlation_id, "won", 30050, 500.0, "2026-01-01T00:00:00+00:00")


def test_current_trade_is_null_when_flat(client):
    resp = client.get("/api/v1/trades/current")
    assert resp.status_code == 200
    assert resp.json() == {"open": False, "trade": None}


def test_current_trade_returns_the_open_position(client):
    _post_entry(client, "corr-current")

    resp = client.get("/api/v1/trades/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["open"] is True
    assert body["trade"]["correlation_id"] == "corr-current"
    assert body["trade"]["status"] == "open"


def test_current_trade_is_null_again_after_exit(client):
    _post_entry(client, "corr-flat-again")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-flat-again", "secret": "test-secret",
        "outcome": "WIN", "exit_price": 100, "realized_pnl": 50,
    })

    resp = client.get("/api/v1/trades/current")
    assert resp.json() == {"open": False, "trade": None}


def test_list_trades_returns_most_recent_first(client):
    _post_entry(client, "corr-a")
    _post_entry(client, "corr-b")

    resp = client.get("/api/v1/trades")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert [t["correlation_id"] for t in body["trades"]] == ["corr-b", "corr-a"]


def test_list_trades_filters_by_status(client):
    _post_entry(client, "corr-still-open")
    _post_entry(client, "corr-will-close")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-will-close", "secret": "test-secret",
        "outcome": "LOSS", "exit_price": 90, "realized_pnl": -50,
    })

    resp = client.get("/api/v1/trades", params={"status": "open"})
    body = resp.json()
    assert body["count"] == 1
    assert body["trades"][0]["correlation_id"] == "corr-still-open"

    resp = client.get("/api/v1/trades", params={"status": "lost"})
    body = resp.json()
    assert body["count"] == 1
    assert body["trades"][0]["correlation_id"] == "corr-will-close"


def test_list_trades_rejects_invalid_status(client):
    resp = client.get("/api/v1/trades", params={"status": "bogus"})
    assert resp.status_code == 400


def test_list_trades_filters_by_test_closed_status(client, repository):
    """test_closed (scripts/close_e2e_test_trades.py) must stay a valid, searchable
    filter value - it's a real status, just not a performance outcome."""
    _post_entry(client, "corr-real-open")
    _post_entry(client, "E2E-MNQU6-1720000000000")
    asyncio.run(repository.update_exit(
        "E2E-MNQU6-1720000000000", "test_closed", None, 0.0, "2026-01-01T00:00:00+00:00",
    ))

    resp = client.get("/api/v1/trades", params={"status": "test_closed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["trades"][0]["correlation_id"] == "E2E-MNQU6-1720000000000"

    # and it does not leak into the "open" filter, since it's no longer open
    resp = client.get("/api/v1/trades", params={"status": "open"})
    body = resp.json()
    assert body["count"] == 1
    assert body["trades"][0]["correlation_id"] == "corr-real-open"


def test_trade_detail_404_for_unknown_correlation_id(client):
    resp = client.get("/api/v1/trades/does-not-exist")
    assert resp.status_code == 404


def test_trade_detail_includes_full_derived_timeline(client):
    _post_entry(client, "corr-timeline")
    client.post("/webhook", json={
        "type": "price_update", "correlation_id": "corr-timeline", "secret": "test-secret",
        "current_price": 30020, "unrealized_pnl": 200,
    })
    with patch.object(ai_module, "analyze_with_claude", return_value=("Played out as expected.", None)):
        client.post("/webhook", json={
            "type": "exit", "correlation_id": "corr-timeline", "secret": "test-secret",
            "outcome": "WIN", "exit_price": 30050, "realized_pnl": 600,
        })

    resp = client.get("/api/v1/trades/corr-timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trade"]["correlation_id"] == "corr-timeline"

    event_types = [e["type"] for e in body["timeline"]]
    assert event_types == [
        "entry_received", "pmt_forwarded", "entry_score", "price_update", "exit", "post_trade_review",
    ]

    price_update_event = next(e for e in body["timeline"] if e["type"] == "price_update")
    assert price_update_event["current_price"] == 30020

    exit_event = next(e for e in body["timeline"] if e["type"] == "exit")
    assert exit_event["realized_pnl"] == 600

    review_event = next(e for e in body["timeline"] if e["type"] == "post_trade_review")
    assert review_event["content"] == "Played out as expected."


def test_trade_detail_timeline_reflects_ai_failure(client, repository):
    asyncio.run(_seed_similar_trade(repository, "hist-failed-relay"))

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(False, None, "timeout")), \
         patch.object(ai_module, "analyze_with_claude", return_value=(None, "ANTHROPIC_API_KEY not configured")):
        client.post("/webhook", json=entry_payload("corr-failed-relay"))

    resp = client.get("/api/v1/trades/corr-failed-relay")
    body = resp.json()

    forward_event = next(e for e in body["timeline"] if e["type"] == "pmt_forward_failed")
    assert forward_event["error"] == "timeout"

    score_event = next(e for e in body["timeline"] if e["type"] == "entry_score")
    assert score_event["error"] == "ANTHROPIC_API_KEY not configured"
    # Sprint 7: the score comes from atlas/intelligence.py's deterministic computation,
    # not from Claude - a Claude failure only means no narrative explanation was
    # generated, the structured score/expected_r/win_rate are unaffected.
    assert score_event["score"] is not None
