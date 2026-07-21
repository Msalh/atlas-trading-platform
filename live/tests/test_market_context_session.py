"""
Phase N1, Sprint 2. Table-driven tests for atlas.market_context.session.
classify_session() - phase boundaries (using CME_RTH_V1's actual calibrated
values: PRE_OPEN 07:30, OPENING_RANGE 08:30, MID_SESSION 09:00,
CLOSING_RANGE 14:50, OVERNIGHT 15:05, all CT), DST correctness via
zoneinfo, SessionProgress, and DriftStatus - including the calibrated
one-bar RTH-open disagreement (Gate 1), which must appear here exactly
where the calibration report says it does, not be "corrected" away.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from atlas.market_context.definitions import CME_RTH_V1
from atlas.market_context.models import DriftStatus, SessionPhase
from atlas.market_context.session import classify_session

_CENTRAL = ZoneInfo("America/Chicago")

# A fixed CDT (summer) Tuesday used for every phase-boundary/SessionProgress
# case below, so those tests are about phase logic, not DST - DST gets its
# own dedicated tests further down.
_CDT_DATE = (2026, 7, 21)


def _occurred_at(date_ymd: tuple, hour: int, minute: int) -> datetime:
    """The one supported way to build a test input: a Central-Time
    wall-clock moment, converted to the UTC, tz-aware datetime
    classify_session() actually expects - exactly what
    translator.to_canonical() would have produced from a real bar."""
    year, month, day = date_ymd
    ct = datetime(year, month, day, hour, minute, tzinfo=_CENTRAL)
    return ct.astimezone(timezone.utc)


# ---- Phase boundaries, every SessionPhase, every transition ----

_PHASE_CASES = [
    # (CT hour, CT minute, expected phase, case id)
    (0, 0, SessionPhase.OVERNIGHT, "midnight"),
    (7, 0, SessionPhase.OVERNIGHT, "overnight-well-before-pre-open"),
    (7, 29, SessionPhase.OVERNIGHT, "last-minute-before-pre-open"),
    (7, 30, SessionPhase.PRE_OPEN, "first-minute-of-pre-open"),
    (8, 0, SessionPhase.PRE_OPEN, "mid-pre-open"),
    (8, 29, SessionPhase.PRE_OPEN, "last-minute-before-rth-open"),
    (8, 30, SessionPhase.OPENING_RANGE, "first-minute-of-opening-range-rth-open"),
    (8, 45, SessionPhase.OPENING_RANGE, "mid-opening-range"),
    (8, 59, SessionPhase.OPENING_RANGE, "last-minute-of-opening-range"),
    (9, 0, SessionPhase.MID_SESSION, "first-minute-of-mid-session"),
    (12, 0, SessionPhase.MID_SESSION, "noon-mid-session"),
    (14, 49, SessionPhase.MID_SESSION, "last-minute-before-closing-range"),
    (14, 50, SessionPhase.CLOSING_RANGE, "first-minute-of-closing-range"),
    (15, 0, SessionPhase.CLOSING_RANGE, "last-real-rth-bar-per-gate-1"),
    (15, 4, SessionPhase.CLOSING_RANGE, "last-minute-before-rth-close"),
    (15, 5, SessionPhase.OVERNIGHT, "first-minute-after-rth-close"),
    (15, 30, SessionPhase.OVERNIGHT, "overnight-after-close"),
    (23, 59, SessionPhase.OVERNIGHT, "last-minute-of-day"),
]


def test_every_phase_boundary_case():
    for hour, minute, expected_phase, case_id in _PHASE_CASES:
        occurred_at = _occurred_at(_CDT_DATE, hour, minute)
        result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
        assert result.phase == expected_phase, (
            f"{case_id}: {hour:02d}:{minute:02d} CT expected {expected_phase}, got {result.phase}"
        )


def test_all_five_session_phases_are_reachable():
    """Every case above must actually be exercised - if a future edit to
    _PHASE_CASES accidentally drops a phase, this catches it independently
    of the per-case assertions."""
    seen = {classify_session(_occurred_at(_CDT_DATE, h, m), None, None).phase for h, m, _, _ in _PHASE_CASES}
    assert seen == set(SessionPhase)


# ---- DST: one CST date, one CDT date, proving ZoneInfo resolves the offset ----

def test_cst_date_08_30_ct_resolves_to_14_30_utc_and_classifies_as_opening_range():
    """2026-01-15 - deep winter, unambiguously CST (UTC-6)."""
    occurred_at = _occurred_at((2026, 1, 15), 8, 30)
    assert occurred_at == datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.phase == SessionPhase.OPENING_RANGE


def test_cdt_date_08_30_ct_resolves_to_13_30_utc_and_classifies_as_opening_range():
    """2026-07-21 - deep summer, unambiguously CDT (UTC-5)."""
    occurred_at = _occurred_at((2026, 7, 21), 8, 30)
    assert occurred_at == datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.phase == SessionPhase.OPENING_RANGE


def test_cst_and_cdt_dates_use_different_utc_offsets_for_the_same_ct_wall_clock_time():
    """The same 08:30 CT moment must NOT map to the same UTC instant across
    the two dates - if it did, DST would not actually be in effect."""
    cst = _occurred_at((2026, 1, 15), 8, 30)
    cdt = _occurred_at((2026, 7, 21), 8, 30)
    assert cst.hour == 14  # UTC-6
    assert cdt.hour == 13  # UTC-5
    assert cst.hour != cdt.hour


# ---- SessionProgress ----

def test_session_progress_at_the_first_rth_bar():
    occurred_at = _occurred_at(_CDT_DATE, 8, 30)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.progress.minutes_since_session_open == 0
    assert result.progress.minutes_until_session_close == 395  # 905 - 510
    assert result.progress.session_open_at == _occurred_at(_CDT_DATE, 8, 30)
    assert result.progress.session_close_at == _occurred_at(_CDT_DATE, 15, 5)


def test_session_progress_in_the_middle_of_the_session():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.progress.minutes_since_session_open == 210  # 720 - 510
    assert result.progress.minutes_until_session_close == 185  # 905 - 720
    assert result.progress.session_open_at == _occurred_at(_CDT_DATE, 8, 30)
    assert result.progress.session_close_at == _occurred_at(_CDT_DATE, 15, 5)


def test_session_progress_at_the_final_rth_bar():
    """15:00 CT - the last bar Gate 1 found to genuinely be RTH; 15:05 is
    already OVERNIGHT."""
    occurred_at = _occurred_at(_CDT_DATE, 15, 0)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.phase == SessionPhase.CLOSING_RANGE
    assert result.progress.minutes_since_session_open == 390  # 900 - 510
    assert result.progress.minutes_until_session_close == 5  # 905 - 900


def test_session_progress_is_none_during_pre_open():
    occurred_at = _occurred_at(_CDT_DATE, 8, 0)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.phase == SessionPhase.PRE_OPEN
    assert result.progress.session_open_at is None
    assert result.progress.session_close_at is None
    assert result.progress.minutes_since_session_open is None
    assert result.progress.minutes_until_session_close is None


def test_session_progress_is_none_during_overnight():
    occurred_at = _occurred_at(_CDT_DATE, 20, 0)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.phase == SessionPhase.OVERNIGHT
    assert result.progress.session_open_at is None
    assert result.progress.session_close_at is None
    assert result.progress.minutes_since_session_open is None
    assert result.progress.minutes_until_session_close is None


# ---- DriftStatus ----

def test_drift_status_agreement_during_mid_session():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    result = classify_session(occurred_at, upstream_session_name="RTH", upstream_is_rth=True)
    assert result.phase == SessionPhase.MID_SESSION
    assert result.drift_status == DriftStatus.AGREEMENT


def test_drift_status_agreement_during_overnight():
    occurred_at = _occurred_at(_CDT_DATE, 20, 0)
    result = classify_session(occurred_at, upstream_session_name="OVERNIGHT", upstream_is_rth=False)
    assert result.phase == SessionPhase.OVERNIGHT
    assert result.drift_status == DriftStatus.AGREEMENT


def test_drift_status_disagreement_the_calibrated_one_bar_rth_open_case():
    """The exact case documented in session.py's module docstring and the
    Gate 1 calibration report: occurred_at = RTH open (08:30 CT). Atlas
    classifies this bar OPENING_RANGE (is_rth=True by close time), but
    Pine's own is_rth for this specific bar reflects its open (08:25,
    still pre-open) and reports False. This must surface as DISAGREEMENT,
    not be silently corrected to match upstream."""
    occurred_at = _occurred_at(_CDT_DATE, 8, 30)
    result = classify_session(occurred_at, upstream_session_name="OVERNIGHT", upstream_is_rth=False)
    assert result.phase == SessionPhase.OPENING_RANGE
    assert result.drift_status == DriftStatus.DISAGREEMENT
    # Upstream's (wrong-by-this-comparison) values are still preserved verbatim -
    # never overwritten to make the two sides agree.
    assert result.upstream_is_rth is False
    assert result.upstream_session_name == "OVERNIGHT"


def test_drift_status_disagreement_is_not_one_directional_only():
    """A hypothetical, not-observed-in-real-data case: upstream claims RTH
    during a bar Atlas classifies OVERNIGHT. The implementation must not be
    hardcoded to only ever detect disagreement in the RTH-open direction."""
    occurred_at = _occurred_at(_CDT_DATE, 20, 0)
    result = classify_session(occurred_at, upstream_session_name="RTH", upstream_is_rth=True)
    assert result.phase == SessionPhase.OVERNIGHT
    assert result.drift_status == DriftStatus.DISAGREEMENT


def test_drift_status_upstream_missing_when_is_rth_is_none():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    result = classify_session(occurred_at, upstream_session_name=None, upstream_is_rth=None)
    assert result.drift_status == DriftStatus.UPSTREAM_MISSING
    assert result.upstream_session_name is None
    assert result.upstream_is_rth is None


def test_drift_status_upstream_missing_takes_precedence_even_with_a_session_name_present():
    """upstream_session_name being present doesn't substitute for
    upstream_is_rth - the drift check is defined purely in terms of
    is_rth."""
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    result = classify_session(occurred_at, upstream_session_name="RTH", upstream_is_rth=None)
    assert result.drift_status == DriftStatus.UPSTREAM_MISSING


# ---- Purity / determinism (classify_session's own property, not the
# cross-module test_market_context_determinism.py suite, which is a later
# sprint's responsibility once service.py exists) ----

def test_classify_session_is_pure_same_inputs_produce_identical_output():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    first = classify_session(occurred_at, upstream_session_name="RTH", upstream_is_rth=True, calendar=CME_RTH_V1)
    second = classify_session(occurred_at, upstream_session_name="RTH", upstream_is_rth=True, calendar=CME_RTH_V1)
    assert first == second
