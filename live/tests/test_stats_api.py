"""Tests for GET /stats/today - the honestly-scoped account/risk summary placeholder."""
from unittest.mock import patch

from atlas.api.v1 import webhook
from tests.conftest import entry_payload


def _post_entry(client, correlation_id, **overrides):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(webhook, "analyze_with_claude", return_value=("ok", None)):
        return client.post("/webhook", json=entry_payload(correlation_id, **overrides))


def test_stats_today_with_no_trades(client):
    resp = client.get("/api/v1/stats/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trades_entered_today"] == 0
    assert body["trades_closed_today"] == 0
    assert body["wins_today"] == 0
    assert body["losses_today"] == 0
    assert body["realized_pnl_today"] == 0
    assert body["pmt_forward_failures_today"] == 0
    assert body["open_position"]["correlation_id"] is None


def test_stats_today_counts_entries_wins_losses_and_pnl(client):
    _post_entry(client, "corr-stats-win")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-stats-win", "secret": "test-secret",
        "outcome": "WIN", "exit_price": 30050, "realized_pnl": 600,
    })

    _post_entry(client, "corr-stats-loss")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-stats-loss", "secret": "test-secret",
        "outcome": "LOSS", "exit_price": 29900, "realized_pnl": -300,
    })

    resp = client.get("/api/v1/stats/today")
    body = resp.json()
    assert body["trades_entered_today"] == 2
    assert body["trades_closed_today"] == 2
    assert body["wins_today"] == 1
    assert body["losses_today"] == 1
    assert body["realized_pnl_today"] == 300


def test_stats_today_counts_pmt_forward_failures(client):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(False, None, "down")), \
         patch.object(webhook, "analyze_with_claude", return_value=(None, None)):
        client.post("/webhook", json=entry_payload("corr-stats-relay-fail"))

    resp = client.get("/api/v1/stats/today")
    body = resp.json()
    assert body["pmt_forward_failures_today"] == 1


def test_stats_today_open_position_risk_reward_long(client):
    _post_entry(client, "corr-stats-long", direction="long", entry_price=30000, sl=29950, tp=30100)

    resp = client.get("/api/v1/stats/today")
    body = resp.json()
    assert body["open_position"]["correlation_id"] == "corr-stats-long"
    assert body["open_position"]["risk_points"] == 50
    assert body["open_position"]["reward_points"] == 100


def test_stats_today_open_position_risk_reward_short(client):
    _post_entry(client, "corr-stats-short", direction="short", entry_price=30000, sl=30050, tp=29900)

    resp = client.get("/api/v1/stats/today")
    body = resp.json()
    assert body["open_position"]["correlation_id"] == "corr-stats-short"
    assert body["open_position"]["risk_points"] == 50
    assert body["open_position"]["reward_points"] == 100
