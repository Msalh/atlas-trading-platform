"""
Tests for kill switch enforcement (Sprint 9) - RISK_ENFORCEMENT=true|false gating
whether a breached daily-loss-limit/trailing-drawdown actually blocks the PickMyTrade
forward. Before this sprint, atlas/risk.py's kill switch was entirely display-only
(KillSwitchStatus.enforced hardcoded False) - this is the first sprint where a real
risk breach can affect the order-relay path at all, so these tests focus specifically
on: does it actually block when enabled, does it leave everything unchanged when
disabled (the existing default), and does it leave analytics/AI/storage untouched
either way (the trade must still be recorded and still be scored - only the PMT
forward itself is gated).
"""
from datetime import datetime, timezone
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.v1 import webhook
from atlas.config import settings
from tests.conftest import entry_payload

ACCOUNT_KWARGS = dict(
    account_starting_balance=10000.0,
    account_daily_loss_limit=500.0,
    account_trailing_drawdown_limit=1000.0,
    account_max_contracts=5,
    account_configured=True,
)


async def _breach_daily_loss_limit(repository):
    """Seeds one closed trade today that alone blows through the $500 daily loss
    limit configured above, so compute_risk_snapshot's kill switch trips."""
    async def _forward_ok():
        return True, 200, None

    await repository.claim_and_forward("hist-loss", entry_payload("hist-loss"), "{}", _forward_ok)
    today = datetime.now(timezone.utc).date().isoformat()
    await repository.update_exit("hist-loss", "lost", 29900, -600.0, f"{today}T12:00:00+00:00")


def _apply_account_settings(monkeypatch):
    for key, value in ACCOUNT_KWARGS.items():
        monkeypatch.setattr(settings, key, value)


async def test_kill_switch_enabled_blocks_pmt_forward_when_breached(client, repository, monkeypatch):
    _apply_account_settings(monkeypatch)
    monkeypatch.setattr(settings, "risk_enforcement", True)
    await _breach_daily_loss_limit(repository)

    with patch.object(webhook, "forward_to_pickmytrade") as mock_forward, \
         patch.object(ai_module, "analyze_with_claude"):
        resp = client.post("/webhook", json=entry_payload("corr-blocked"))

    mock_forward.assert_not_called()  # the real HTTP call to PickMyTrade never happens
    assert resp.status_code == 207
    body = resp.json()
    assert body["pmt_forwarded"] is False
    assert "blocked by risk engine" in body["pmt_error"]


async def test_kill_switch_disabled_does_not_block_despite_breach(client, repository, monkeypatch):
    """RISK_ENFORCEMENT=false is the default - a breach must remain purely
    informational (as it always has been, pre-Sprint-9), never blocking."""
    _apply_account_settings(monkeypatch)
    monkeypatch.setattr(settings, "risk_enforcement", False)
    await _breach_daily_loss_limit(repository)

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)) as mock_forward, \
         patch.object(ai_module, "analyze_with_claude"):
        resp = client.post("/webhook", json=entry_payload("corr-not-blocked"))

    mock_forward.assert_called_once()
    assert resp.status_code == 200
    assert resp.json()["pmt_forwarded"] is True


async def test_kill_switch_enabled_does_not_block_when_not_breached(client, repository, monkeypatch):
    """Enforcement being ON doesn't mean everything gets blocked - only an actual
    breach does."""
    _apply_account_settings(monkeypatch)
    monkeypatch.setattr(settings, "risk_enforcement", True)
    # No losing trades seeded - nothing has breached anything.

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)) as mock_forward, \
         patch.object(ai_module, "analyze_with_claude"):
        resp = client.post("/webhook", json=entry_payload("corr-clean"))

    mock_forward.assert_called_once()
    assert resp.status_code == 200


async def test_blocked_entry_is_still_stored_and_still_scored_by_ai(client, repository, monkeypatch):
    """The kill switch gates the PickMyTrade forward only - it must never affect
    storage, analytics, or AI scoring (explicit Sprint 9 requirement). Uses
    `repository` directly (awaited in-line) rather than the get_trade/get_ai_notes
    fixtures, which call asyncio.run() internally and can't be used from inside an
    already-running event loop (this test is itself async, unlike most others in the
    suite, because it needs to await _breach_daily_loss_limit directly)."""
    _apply_account_settings(monkeypatch)
    monkeypatch.setattr(settings, "risk_enforcement", True)
    await _breach_daily_loss_limit(repository)

    with patch.object(webhook, "forward_to_pickmytrade") as mock_forward, \
         patch.object(ai_module, "analyze_with_claude", return_value=("scored anyway", None)):
        client.post("/webhook", json=entry_payload("corr-still-scored"))

    mock_forward.assert_not_called()

    trade = await repository.get_by_correlation_id("corr-still-scored")
    assert trade is not None
    assert trade["status"] == "open"  # stored exactly as any other entry would be

    notes = await repository.list_ai_notes(trade_correlation_id="corr-still-scored", note_type="entry_score")
    assert len(notes) == 1  # AI scoring still ran, unaffected by the block
