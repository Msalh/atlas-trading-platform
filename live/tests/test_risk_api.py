"""Tests for GET /api/v1/risk - fetch-and-serialize wrapper around atlas/risk.py's pure
computation. atlas/risk.py's own test suite (test_risk.py) covers the math in depth;
these tests confirm the endpoint wires real trade data and settings into it correctly."""
from unittest.mock import patch

from atlas.api.v1 import webhook
from atlas.config import settings
from tests.conftest import entry_payload


def _post_entry(client, correlation_id, **overrides):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(webhook, "analyze_with_claude", return_value=("ok", None)):
        return client.post("/webhook", json=entry_payload(correlation_id, **overrides))


def test_risk_endpoint_with_no_trades(client, monkeypatch):
    monkeypatch.setattr(settings, "account_starting_balance", 50_000.0)
    monkeypatch.setattr(settings, "account_daily_loss_limit", 1_000.0)
    monkeypatch.setattr(settings, "account_trailing_drawdown_limit", 2_000.0)
    monkeypatch.setattr(settings, "account_max_contracts", 5)
    monkeypatch.setattr(settings, "account_configured", True)

    resp = client.get("/api/v1/risk")
    assert resp.status_code == 200
    body = resp.json()

    assert body["current_balance"] == 50_000.0
    assert body["high_water_mark"] == 50_000.0
    assert body["open_position"] is None
    assert body["kill_switch"]["should_trigger"] is False
    assert body["kill_switch"]["enforced"] is False
    assert body["account_configured"] is True


def test_risk_endpoint_reflects_closed_and_open_trades(client):
    _post_entry(client, "corr-closed", direction="long", entry_price=100, sl=90, tp=130, quantity=2)
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-closed", "secret": "test-secret",
        "outcome": "WIN", "exit_price": 130, "realized_pnl": 600,
    })
    _post_entry(client, "corr-open", direction="short", entry_price=200, sl=210, tp=170, quantity=3)

    resp = client.get("/api/v1/risk")
    body = resp.json()

    assert body["current_balance"] == body["starting_balance"] + 600
    assert body["daily_realized_pnl"] == 600
    assert body["open_position"]["correlation_id"] == "corr-open"
    assert body["open_position"]["direction"] == "short"
    assert body["open_position"]["quantity"] == 3
    assert body["open_position"]["risk_points"] == 10  # sl 210 - entry 200
    assert body["open_position"]["reward_points"] == 30  # entry 200 - tp 170


def test_risk_endpoint_kill_switch_triggers_when_daily_loss_limit_is_small(client, monkeypatch):
    monkeypatch.setattr(settings, "account_daily_loss_limit", 100.0)

    _post_entry(client, "corr-big-loss")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-big-loss", "secret": "test-secret",
        "outcome": "LOSS", "exit_price": 29000, "realized_pnl": -500,
    })

    resp = client.get("/api/v1/risk")
    body = resp.json()

    assert body["daily_loss_limit_breached"] is True
    assert body["kill_switch"]["should_trigger"] is True
    assert body["kill_switch"]["enforced"] is False
    assert any("Daily loss limit" in r for r in body["kill_switch"]["reasons"])


def test_risk_endpoint_reports_unconfigured_account(client, monkeypatch):
    monkeypatch.setattr(settings, "account_configured", False)

    resp = client.get("/api/v1/risk")
    assert resp.json()["account_configured"] is False
