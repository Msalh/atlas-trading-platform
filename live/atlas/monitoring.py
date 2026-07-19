"""
Market Engine staleness detection - Sprint 7. A single new module, not the
full atlas/monitoring/ package (with a status.py/alerting.py relocation) the
original Market Engine roadmap sketch proposed - see the Sprint 7 write-up
for why: relocating two existing, working, imported-in-several-places files
is a broad refactor this Sprint's actual need doesn't require. If a real
second monitoring concern eventually needs a package, that's the moment to
do the relocation - not preemptively here.

Reuses, does not reinvent: atlas.status.SystemStatus already tracks "when was
event type X last seen" once MARKET_STATE_INGESTED is registered in
atlas.events.types.ALL (automatic, via atlas/main.py's existing subscription
loop); atlas.alerting.send_alert already handles delivery, including being a
no-op when ALERT_WEBHOOK_URL is unset. This module's only new contribution is
deciding WHEN a gap matters and WHETHER one is currently expected.

Everything here is pure/synchronous and unit-testable without a running
FastAPI app or event loop - atlas/main.py's background task is a thin
adapter that extracts values from app.state and calls into this module, kept
deliberately thin so the interesting logic isn't hidden behind something this
project can't easily test.
"""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from atlas.alerting import send_alert

_CT = ZoneInfo("America/Chicago")


def is_market_hours_expected(now: datetime) -> bool:
    """A deliberately conservative, NOT holiday-aware approximation of "should
    market_state events be arriving right now". Excludes: all day Saturday,
    Sunday before 17:00 CT (the week's Globex open), Friday from 16:00 CT
    onward (the week's close), and the daily maintenance window (16:00-17:00
    CT, Monday-Thursday) - the same 17:00 CT trading-day boundary already
    treated as an external CME fact elsewhere in this project.

    Does NOT know about exchange holidays or early-close days - a named,
    disclosed limitation (see the Sprint 7 write-up), not an oversight.
    Building real holiday-calendar awareness is genuinely subtle work (this
    project's own research history found it easy to get wrong even with
    dedicated effort) and is out of scope for this Sprint - the honest
    consequence is a false-positive alert on exchange holidays, not a silent
    gap in coverage."""
    ct = now.astimezone(_CT)
    weekday = ct.weekday()  # Monday=0 ... Sunday=6
    hour = ct.hour

    if weekday == 5:  # Saturday - fully closed
        return False
    if weekday == 6 and hour < 17:  # Sunday before the week's open
        return False
    if weekday == 4 and hour >= 16:  # Friday from the week's close onward
        return False
    if weekday in (0, 1, 2, 3) and 16 <= hour < 17:  # daily maintenance, Mon-Thu
        return False
    return True


def compute_staleness_minutes(last_seen_at: Optional[datetime], started_at: datetime, now: datetime) -> float:
    """Minutes since the last known market_state event, or since this process
    started if nothing has been seen yet this process - a fresh deploy
    legitimately hasn't heard from anything yet (see atlas/status.py's own
    documented reasoning), so it isn't treated as an instant gap."""
    reference = last_seen_at if last_seen_at is not None else started_at
    return (now - reference).total_seconds() / 60


class MarketStateStalenessMonitor:
    """Alert-once-on-transition, mirroring atlas.alerting.ClaudeFailureTracker's
    pattern: one alert when the threshold is first crossed, one more on
    recovery, never a repeat while already in either state - avoids
    alert-spam on a fixed check interval (default: every 60 seconds)."""

    def __init__(self, threshold_minutes: float):
        self.threshold_minutes = threshold_minutes
        self._alert_sent = False

    def check(self, last_seen_at: Optional[datetime], started_at: datetime, now: datetime) -> None:
        if not is_market_hours_expected(now):
            return  # never alert outside expected hours, regardless of staleness

        staleness_minutes = compute_staleness_minutes(last_seen_at, started_at, now)

        if staleness_minutes >= self.threshold_minutes:
            if not self._alert_sent:
                send_alert(
                    f"Market Engine: no market_state event received in over "
                    f"{staleness_minutes:.0f} minutes during expected market hours."
                )
                self._alert_sent = True
        else:
            if self._alert_sent:
                send_alert("Market Engine: market_state ingestion has resumed.")
            self._alert_sent = False
