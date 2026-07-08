"""
Sprint 10 - Operational alerting: PickMyTrade forward failures and sustained Claude
failures. Registered as ordinary EventBus subscribers in atlas/main.py's lifespan,
following the exact pattern atlas/events/subscribers.py::log_event already
established ("future subscribers - Discord, Telegram, Email - register the same way,
independent of the webhook/execution code that publishes events").

Non-blocking by construction, not just convention: atlas.events.bus.EventBus.publish()
awaits every subscriber directly on the request-critical path (see e.g.
atlas/api/v1/webhook.py's `await event_bus.publish(...)` calls). A subscriber that
awaited a slow or unreachable alert webhook itself would delay that response. Every
function below that actually performs the HTTP call is scheduled via
asyncio.create_task and never awaited by the subscriber that triggers it - the
subscriber returns as soon as the alert is *scheduled*, not once it's *delivered*.

Sends a Slack-compatible `{"text": ...}` JSON payload - also accepted as-is by Discord
(via a Slack-compatible incoming webhook URL) and most generic webhook receivers. If
ALERT_WEBHOOK_URL is unset, every function here is a no-op - the same "advisory only,
gracefully absent when unconfigured" pattern as PICKMYTRADE_WEBHOOK_URL/
ANTHROPIC_API_KEY.
"""
import asyncio
import logging
from typing import Any

import httpx

from atlas.config import settings

logger = logging.getLogger("atlas.alerting")

ALERT_TIMEOUT_SECONDS = 5


async def _post_alert(message: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=ALERT_TIMEOUT_SECONDS) as client:
            await client.post(settings.alert_webhook_url, json={"text": message})
    except Exception as e:
        # An alert that fails to deliver must never raise into the event loop - it's
        # commentary on top of commentary. Logged so a persistently-broken
        # ALERT_WEBHOOK_URL is at least visible in the log stream.
        logger.warning("failed to deliver alert: %s", e)


def send_alert(message: str) -> None:
    """Schedules delivery and returns immediately - callers on a response-critical
    path (indirectly, via an EventBus subscriber) must never block on this. A no-op
    when ALERT_WEBHOOK_URL isn't configured."""
    if not settings.alert_webhook_url:
        return
    asyncio.create_task(_post_alert(message))


async def alert_on_forward_failure(event_type: str, payload: dict[str, Any]) -> None:
    """Subscribed to atlas.events.types.TRADE_ENTRY_FORWARD_FAILED. One alert per
    failed forward, no debouncing - PickMyTrade failures are already rare at this
    strategy's trade volume (a handful of signals a day), unlike Claude calls (see
    ClaudeFailureTracker below), so there's no noisy-alert risk to guard against."""
    correlation_id = payload.get("correlation_id", "unknown")
    error = payload.get("pmt_error", "unknown error")
    send_alert(
        f"PickMyTrade forward FAILED for trade {correlation_id}: {error}. "
        f"This trade was stored but NOT relayed to your broker."
    )


class ClaudeFailureTracker:
    """Tracks CONSECUTIVE Claude failures across all three AI event types
    (AI_ENTRY_SCORED, AI_TRADE_REVIEWED, AI_REPORT_GENERATED - see atlas/ai.py) as one
    unified "is Claude currently healthy" signal, not three separate ones - the
    operational question ("is something wrong with our Claude integration right now")
    doesn't depend on which specific AI pass happened to fail.

    Alerts once when the consecutive-failure count reaches `threshold` - not on every
    single failure, since a single transient failure is expected and already tolerated
    by every AI module's own "advisory only" design (see atlas/ai.py's module
    docstring) - and once more on recovery, so the alert channel isn't only ever a
    one-way stream of bad news with no resolution signal. A success resets the streak
    immediately, whether or not an alert was ever sent for it.
    """

    def __init__(self, threshold: int):
        self.threshold = threshold
        self._consecutive_failures = 0
        self._alert_sent = False

    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        if payload.get("ok", True):
            if self._alert_sent:
                send_alert(
                    f"Claude AI calls are succeeding again after "
                    f"{self._consecutive_failures} consecutive failure(s)."
                )
            self._consecutive_failures = 0
            self._alert_sent = False
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= self.threshold and not self._alert_sent:
            error = payload.get("error", "unknown error")
            send_alert(
                f"{self._consecutive_failures} consecutive Claude AI failures "
                f"(most recent: {event_type}). Latest error: {error}. "
                f"AI scoring/review/reports are degraded - order execution is unaffected."
            )
            self._alert_sent = True
