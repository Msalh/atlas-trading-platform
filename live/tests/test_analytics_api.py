"""Tests for the three analytics endpoints - confirms real trade data flows through
compute_summary/compute_equity_curve/compute_breakdown correctly end to end. The math
itself is covered in depth by test_analytics.py."""
from unittest.mock import patch

from atlas.api.v1 import webhook
from atlas.config import settings
from tests.conftest import entry_payload


def _closed_trade(client, correlation_id, outcome, realized_pnl, **overrides):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(webhook, "analyze_with_claude", return_value=("ok", None)):
        client.post("/webhook", json=entry_payload(correlation_id, **overrides))
    client.post("/webhook", json={
        "type": "exit", "correlation_id": correlation_id, "secret": "test-secret",
        "outcome": outcome, "exit_price": 100, "realized_pnl": realized_pnl,
    })


def test_analytics_summary_with_no_trades(client):
    resp = client.get("/api/v1/analytics/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_trades"] == 0
    assert body["profit_factor"] is None


def test_analytics_summary_reflects_closed_trades(client):
    _closed_trade(client, "corr-win", "WIN", 500)
    _closed_trade(client, "corr-loss", "LOSS", -200)

    resp = client.get("/api/v1/analytics/summary")
    body = resp.json()
    assert body["total_trades"] == 2
    assert body["wins"] == 1
    assert body["losses"] == 1
    assert body["gross_profit"] == 500
    assert body["gross_loss"] == 200


def test_analytics_equity_curve_starts_at_configured_starting_balance(client, monkeypatch):
    monkeypatch.setattr(settings, "account_starting_balance", 25_000.0)

    _closed_trade(client, "corr-1", "WIN", 300)

    resp = client.get("/api/v1/analytics/equity-curve")
    body = resp.json()
    assert body["starting_balance"] == 25_000.0
    assert body["ending_equity"] == 25_300.0
    assert len(body["points"]) == 1
    assert body["points"][0]["correlation_id"] == "corr-1"


def test_analytics_breakdown_groups_by_session_and_setup(client):
    _closed_trade(client, "corr-ny", "WIN", 400, session="NY", setup_tag="BRK")
    _closed_trade(client, "corr-london", "LOSS", -100, session="London", setup_tag="RCL")

    resp = client.get("/api/v1/analytics/breakdown")
    body = resp.json()

    session_keys = {g["key"] for g in body["by_session"]}
    setup_keys = {g["key"] for g in body["by_setup"]}
    assert session_keys == {"NY", "London"}
    assert setup_keys == {"BRK", "RCL"}
    assert len(body["by_weekday"]) >= 1
