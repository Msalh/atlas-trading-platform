"""Tests for GET /api/v1/activity - fetch-and-serialize wrapper around
atlas/activity.py's pure aggregation. atlas/activity.py's own test suite
(test_activity.py) covers the event-building logic in depth; these confirm the
endpoint wires real trade/AI-note/risk/status data into it correctly."""
import asyncio
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.v1 import webhook
from atlas.config import settings
from tests.conftest import entry_payload


def _post_entry(client, correlation_id, **overrides):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude", return_value=("ok", None)):
        return client.post("/webhook", json=entry_payload(correlation_id, **overrides))


def test_activity_endpoint_empty(client):
    resp = client.get("/api/v1/activity")
    assert resp.status_code == 200
    assert resp.json() == {"count": 0, "events": []}


def test_activity_endpoint_includes_trade_entry_event(client):
    _post_entry(client, "corr-1")

    resp = client.get("/api/v1/activity")
    body = resp.json()
    assert body["count"] >= 1
    trade_events = [e for e in body["events"] if e["correlation_id"] == "corr-1"]
    assert any(e["category"] == "trading" and e["severity"] == "info" for e in trade_events)


def test_activity_endpoint_includes_exit_event(client):
    _post_entry(client, "corr-1")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-1", "secret": "test-secret",
        "outcome": "WIN", "exit_price": 30050, "realized_pnl": 600,
    })

    resp = client.get("/api/v1/activity")
    events = resp.json()["events"]
    exit_events = [e for e in events if "Trade closed" in e["title"]]
    assert len(exit_events) == 1
    assert exit_events[0]["severity"] == "success"


def test_activity_endpoint_includes_ai_notes(client, repository):
    asyncio.run(repository.add_ai_note(
        trade_correlation_id=None, note_type="daily_report", model="claude-x",
        content="Solid day.", error=None,
    ))

    resp = client.get("/api/v1/activity")
    events = resp.json()["events"]
    assert any(e["category"] == "analytics" for e in events)


def test_activity_endpoint_reflects_daily_loss_breach(client, monkeypatch):
    monkeypatch.setattr(settings, "account_daily_loss_limit", 100.0)
    _post_entry(client, "corr-big-loss")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-big-loss", "secret": "test-secret",
        "outcome": "LOSS", "exit_price": 29000, "realized_pnl": -500,
    })

    resp = client.get("/api/v1/activity")
    events = resp.json()["events"]
    risk_events = [e for e in events if e["category"] == "risk"]
    assert any(e["severity"] == "critical" for e in risk_events)


def test_activity_endpoint_respects_limit_param(client):
    for i in range(5):
        _post_entry(client, f"corr-{i}")

    resp = client.get("/api/v1/activity", params={"limit": 2})
    assert resp.json()["count"] == 2


def test_activity_endpoint_rejects_limit_out_of_range(client):
    resp = client.get("/api/v1/activity", params={"limit": 0})
    assert resp.status_code == 422
