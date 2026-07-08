"""
Tests for atlas/alerting.py (Sprint 10) - PickMyTrade forward-failure alerts and the
ClaudeFailureTracker's consecutive-failure/recovery logic. send_alert() schedules
delivery via asyncio.create_task and never awaits it directly (see that module's
docstring for why) - tests that need to observe a scheduled alert actually complete
await asyncio.sleep(0) after triggering it, giving the event loop one turn to run the
task before asserting on it.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import atlas.alerting as alerting_module
from atlas.config import settings


@pytest.fixture(autouse=True)
def _configured_alert_webhook(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", "https://hooks.example.com/alert")


# --- send_alert / _post_alert ---------------------------------------------------------

async def test_send_alert_is_a_no_op_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "alert_webhook_url", "")
    with patch.object(alerting_module, "_post_alert", new_callable=AsyncMock) as mock_post_alert:
        alerting_module.send_alert("should not be sent")
        await asyncio.sleep(0)
    mock_post_alert.assert_not_called()


async def test_send_alert_schedules_delivery_when_configured():
    with patch.object(alerting_module, "_post_alert", new_callable=AsyncMock) as mock_post_alert:
        alerting_module.send_alert("hello")
        await asyncio.sleep(0)  # let the scheduled task actually run
    mock_post_alert.assert_called_once_with("hello")


async def test_post_alert_sends_a_slack_compatible_payload_to_the_configured_url():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await alerting_module._post_alert("test message")
    mock_post.assert_called_once_with("https://hooks.example.com/alert", json={"text": "test message"})


async def test_post_alert_swallows_delivery_failures():
    with patch("httpx.AsyncClient.post", side_effect=Exception("network error")):
        await alerting_module._post_alert("test message")  # must not raise


# --- alert_on_forward_failure -----------------------------------------------------------

async def test_alert_on_forward_failure_names_the_trade_and_the_error():
    with patch.object(alerting_module, "send_alert") as mock_send:
        await alerting_module.alert_on_forward_failure(
            "trade.entry.forward_failed", {"correlation_id": "corr-1", "pmt_error": "connection refused"},
        )
    mock_send.assert_called_once()
    message = mock_send.call_args[0][0]
    assert "corr-1" in message
    assert "connection refused" in message


# --- ClaudeFailureTracker ---------------------------------------------------------------

async def test_tracker_does_not_alert_below_threshold():
    tracker = alerting_module.ClaudeFailureTracker(threshold=3)
    with patch.object(alerting_module, "send_alert") as mock_send:
        await tracker.record("ai.entry_scored", {"ok": False, "error": "timeout"})
        await tracker.record("ai.entry_scored", {"ok": False, "error": "timeout"})
    mock_send.assert_not_called()


async def test_tracker_alerts_once_at_threshold():
    tracker = alerting_module.ClaudeFailureTracker(threshold=3)
    with patch.object(alerting_module, "send_alert") as mock_send:
        for _ in range(3):
            await tracker.record("ai.entry_scored", {"ok": False, "error": "timeout"})
    mock_send.assert_called_once()


async def test_tracker_does_not_re_alert_on_further_failures_past_threshold():
    tracker = alerting_module.ClaudeFailureTracker(threshold=3)
    with patch.object(alerting_module, "send_alert") as mock_send:
        for _ in range(6):
            await tracker.record("ai.entry_scored", {"ok": False, "error": "timeout"})
    mock_send.assert_called_once()  # not six times


async def test_tracker_counts_failures_across_different_ai_event_types_as_one_streak():
    """One unified streak, not three separate ones per AI event type - see the class
    docstring for why the operational question doesn't care which pass failed."""
    tracker = alerting_module.ClaudeFailureTracker(threshold=3)
    with patch.object(alerting_module, "send_alert") as mock_send:
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e1"})
        await tracker.record("ai.trade_reviewed", {"ok": False, "error": "e2"})
        await tracker.record("ai.report_generated", {"ok": False, "error": "e3"})
    mock_send.assert_called_once()


async def test_tracker_resets_and_sends_a_recovery_alert_after_success():
    tracker = alerting_module.ClaudeFailureTracker(threshold=2)
    with patch.object(alerting_module, "send_alert") as mock_send:
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e"})
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e"})  # crosses threshold
        await tracker.record("ai.entry_scored", {"ok": True})  # recovers
    assert mock_send.call_count == 2  # one failure alert, one recovery alert
    recovery_message = mock_send.call_args_list[1][0][0]
    assert "succeeding again" in recovery_message


async def test_tracker_success_before_threshold_sends_no_alert_at_all():
    tracker = alerting_module.ClaudeFailureTracker(threshold=3)
    with patch.object(alerting_module, "send_alert") as mock_send:
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e"})
        await tracker.record("ai.entry_scored", {"ok": True})  # recovers before ever crossing threshold
    mock_send.assert_not_called()  # never alerted about the failure, so no recovery alert either


async def test_tracker_can_re_alert_after_a_second_separate_failure_streak():
    tracker = alerting_module.ClaudeFailureTracker(threshold=2)
    with patch.object(alerting_module, "send_alert") as mock_send:
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e"})
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e"})  # alert #1 (failure)
        await tracker.record("ai.entry_scored", {"ok": True})  # alert #2 (recovery)
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e"})
        await tracker.record("ai.entry_scored", {"ok": False, "error": "e"})  # alert #3 (new failure streak)
    assert mock_send.call_count == 3
