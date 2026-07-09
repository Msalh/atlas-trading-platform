"""Tests for GET /stats/today - the honestly-scoped account/risk summary placeholder."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.v1 import webhook
from tests.conftest import entry_payload


def _post_entry(client, correlation_id, **overrides):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude", return_value=("ok", None)):
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
         patch.object(ai_module, "analyze_with_claude", return_value=(None, None)):
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


def test_stats_today_excludes_test_closed_trades(client, repository):
    """scripts/close_e2e_test_trades.py marks stuck-open E2E trades status='test_closed'
    - these must not inflate entries/closed/win-loss counts, matching the exact
    status in ("won", "lost") exclusion pattern analytics/risk/intelligence already use."""
    _post_entry(client, "E2E-MNQU6-1720000000000")

    today_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    asyncio.run(repository.update_exit("E2E-MNQU6-1720000000000", "test_closed", None, 0.0, today_iso))

    resp = client.get("/api/v1/stats/today")
    body = resp.json()
    assert body["trades_entered_today"] == 0
    assert body["trades_closed_today"] == 0
    assert body["wins_today"] == 0
    assert body["losses_today"] == 0
    assert body["realized_pnl_today"] == 0
    assert body["open_position"]["correlation_id"] is None


def test_stats_today_counts_real_trades_alongside_excluded_test_closed_trade(client, repository):
    """A real won trade entered/closed today must still be counted correctly even
    while a test_closed trade exists in the same window - the exclusion must not
    accidentally swallow real data."""
    _post_entry(client, "corr-real-alongside-test")
    client.post("/webhook", json={
        "type": "exit", "correlation_id": "corr-real-alongside-test", "secret": "test-secret",
        "outcome": "WIN", "exit_price": 30050, "realized_pnl": 600,
    })

    _post_entry(client, "E2E-MNQU6-1720000000001")
    today_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    asyncio.run(repository.update_exit("E2E-MNQU6-1720000000001", "test_closed", None, 0.0, today_iso))

    resp = client.get("/api/v1/stats/today")
    body = resp.json()
    assert body["trades_entered_today"] == 1  # only the real trade
    assert body["trades_closed_today"] == 1
    assert body["wins_today"] == 1
    assert body["realized_pnl_today"] == 600
