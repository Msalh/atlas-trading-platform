"""
Session classification - Phase N1, Sprint 2. classify_session() computes
Atlas's own session phase from occurred_at alone, using a
SessionCalendarDefinition (CME_RTH_V1 by default, Sprint 1) - it never
trusts the incoming session_name/is_rth as authoritative. Those upstream
values are accepted as parameters and carried through on the returned
SessionClassification for comparison/drift diagnostics only; they are
never read to decide `phase`, and Atlas's own classification is never
corrected to match them.

Pure, deterministic, replay-safe, side-effect free: no logging, no
database, no environment reads, no clock other than the supplied
occurred_at. UTC -> Central Time uses only the stdlib
zoneinfo.ZoneInfo("America/Chicago") - no third-party timezone library -
which resolves CST/CDT correctly for any date from the IANA tz database,
making DST handling explicit rather than an ad hoc offset table.

Assumes rth_open/rth_close and every buffer window (pre_open,
opening_range, closing_range) fall on the same Central-Time calendar day
and never wrap past midnight - true for CME_RTH_V1's actual values
(07:30-15:05 CT, comfortably inside one day). A future calendar needing a
session that wraps midnight would need this module extended, not silently
assumed to already handle it - not built speculatively here.

--- The calibrated one-bar RTH-open disagreement (read this before "fixing" it) ---

Gate 1's calibration (97,858 real, certified MNQ1! 5-minute bars) found
that the bar reported at exactly RTH open (e.g. occurred_at = 08:30 CT
under CME_RTH_V1) disagrees with upstream is_rth on almost every session -
about 0.39% of all RTH-adjacent bars, one per session, with zero exception
found in the calibration data. This is expected, not a bug:
`occurred_at` is bar-CLOSE time (this project's established convention),
so the bar reported as closing at 08:30 actually opened five minutes
earlier, at 08:25 - still pre-open. Pine's own is_rth flag for that one
bar reflects its open, not its close, so it reports False for a bar Atlas
correctly classifies as OPENING_RANGE (is_rth=True) by close-time. Shifting
the RTH boundary does not remove this - it only relocates which single bar
disagrees (confirmed in the calibration report by testing +-5/10 minute
boundary shifts). classify_session() does not special-case this bar to
force agreement - doing so would mean silently overriding a real,
understood, bar-open-vs-bar-close convention difference with a guess about
what upstream "meant." The disagreement is reported via DriftStatus.
DISAGREEMENT, exactly like any other, real, unexplained mismatch would be -
the fact that this specific case has a full, calibrated explanation lives
in this docstring and the Gate 1 report, not in a special code path.
"""
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from atlas.market_context.definitions import CME_RTH_V1, SessionCalendarDefinition
from atlas.market_context.models import DriftStatus, SessionClassification, SessionPhase, SessionProgress

_CENTRAL = ZoneInfo("America/Chicago")

_RTH_PHASES = (SessionPhase.OPENING_RANGE, SessionPhase.MID_SESSION, SessionPhase.CLOSING_RANGE)


def _minute_of_day(hour: int, minute: int) -> int:
    return hour * 60 + minute


def _classify_phase(minute_of_day: int, calendar: SessionCalendarDefinition) -> SessionPhase:
    p = calendar.params
    open_minute = _minute_of_day(p.rth_open_hour_ct, p.rth_open_minute_ct)
    close_minute = _minute_of_day(p.rth_close_hour_ct, p.rth_close_minute_ct)
    pre_open_start_minute = open_minute - p.pre_open_minutes
    opening_range_end_minute = open_minute + p.opening_range_minutes
    closing_range_start_minute = close_minute - p.closing_range_minutes

    if pre_open_start_minute <= minute_of_day < open_minute:
        return SessionPhase.PRE_OPEN
    if open_minute <= minute_of_day < opening_range_end_minute:
        return SessionPhase.OPENING_RANGE
    if closing_range_start_minute <= minute_of_day < close_minute:
        return SessionPhase.CLOSING_RANGE
    if opening_range_end_minute <= minute_of_day < closing_range_start_minute:
        return SessionPhase.MID_SESSION
    return SessionPhase.OVERNIGHT


def _session_progress(
    occurred_ct: datetime, minute_of_day: int, phase: SessionPhase, calendar: SessionCalendarDefinition,
) -> SessionProgress:
    if phase not in _RTH_PHASES:
        return SessionProgress(
            session_open_at=None, session_close_at=None,
            minutes_since_session_open=None, minutes_until_session_close=None,
        )

    p = calendar.params
    open_minute = _minute_of_day(p.rth_open_hour_ct, p.rth_open_minute_ct)
    close_minute = _minute_of_day(p.rth_close_hour_ct, p.rth_close_minute_ct)

    # Both anchors fall on the same Central-Time calendar date as
    # occurred_ct - correct for every RTH-anchored phase, since none of
    # them can span midnight (see the module-level "no wraparound"
    # assumption above).
    session_open_ct = occurred_ct.replace(
        hour=p.rth_open_hour_ct, minute=p.rth_open_minute_ct, second=0, microsecond=0,
    )
    session_close_ct = occurred_ct.replace(
        hour=p.rth_close_hour_ct, minute=p.rth_close_minute_ct, second=0, microsecond=0,
    )

    return SessionProgress(
        session_open_at=session_open_ct.astimezone(timezone.utc),
        session_close_at=session_close_ct.astimezone(timezone.utc),
        minutes_since_session_open=minute_of_day - open_minute,
        minutes_until_session_close=close_minute - minute_of_day,
    )


def _drift_status(phase: SessionPhase, upstream_is_rth: Optional[bool]) -> DriftStatus:
    if upstream_is_rth is None:
        return DriftStatus.UPSTREAM_MISSING
    atlas_is_rth = phase in _RTH_PHASES
    return DriftStatus.AGREEMENT if atlas_is_rth == upstream_is_rth else DriftStatus.DISAGREEMENT


def classify_session(
    occurred_at: datetime,
    upstream_session_name: Optional[str],
    upstream_is_rth: Optional[bool],
    calendar: SessionCalendarDefinition = CME_RTH_V1,
) -> SessionClassification:
    """occurred_at must already be UTC and tz-aware, matching every other
    consumer of MarketState.envelope.occurred_at in this codebase (guaranteed
    by atlas.market_engine.adapters.tradingview.translator.to_canonical()) -
    not re-validated here, the same "trust the established invariant" posture
    Rule Engine facts already take on their own MarketState window input."""
    occurred_ct = occurred_at.astimezone(_CENTRAL)
    minute_of_day = _minute_of_day(occurred_ct.hour, occurred_ct.minute)

    phase = _classify_phase(minute_of_day, calendar)
    progress = _session_progress(occurred_ct, minute_of_day, phase, calendar)
    drift_status = _drift_status(phase, upstream_is_rth)

    return SessionClassification(
        phase=phase,
        progress=progress,
        upstream_session_name=upstream_session_name,
        upstream_is_rth=upstream_is_rth,
        drift_status=drift_status,
    )
