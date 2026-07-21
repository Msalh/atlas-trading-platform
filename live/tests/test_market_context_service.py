"""
Phase N1, Sprint 4. Table-driven tests for
atlas.market_context.service.build_market_context() - the composition
layer that wires classify_session() + classify_volatility_regime() +
compute_fingerprint() together into a MarketContext, and derives
ContextQuality from their combined output.

Uses a small, hand-verifiable custom RegimeClassifierDefinition
(lookback_bars=10) rather than the real 288-bar REGIME_CLASSIFIER_V1, for
the same readability reason test_market_context_regime.py does - and the
real CME_RTH_V1 calendar, so the calibrated phase/DriftStatus behaviour
already proven in test_market_context_session.py can be reused directly.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import (
    CME_RTH_V1,
    RegimeClassifierDefinition,
    RegimeClassifierParams,
    SessionCalendarDefinition,
    SessionCalendarParams,
)
from atlas.market_context.models import ContextQuality, DriftStatus, VolatilityRegime
from atlas.market_context.regime import classify_volatility_regime
from atlas.market_context.service import build_market_context
from atlas.market_context.session import classify_session
from atlas.market_engine.models import BarStatus, MarketState

_CENTRAL = ZoneInfo("America/Chicago")
_CDT_DATE = (2026, 7, 21)

_SMALL = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=10, min_bars_required=10, compressed_percentile=25, expanded_percentile=75,
    ),
)


def _occurred_at(date_ymd: tuple, hour: int, minute: int) -> datetime:
    year, month, day = date_ymd
    ct = datetime(year, month, day, hour, minute, tzinfo=_CENTRAL)
    return ct.astimezone(timezone.utc)


def _bar(occurred_at: datetime, atr: float, symbol: str = "MNQU6", timeframe: str = "5m") -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at),
        schema_version="1.0",
        symbol=Symbol(symbol),
        timeframe=Timeframe(timeframe),
        bar_status=BarStatus.CLOSED,
        atr=atr,
    )


def _window_ending_at(
    occurred_at: datetime, n: int, symbol: str = "MNQU6", timeframe: str = "5m",
) -> list[MarketState]:
    """n contiguous bars at the given cadence, the last one at occurred_at -
    the same "window ends at the bar being classified" shape
    test_market_context_regime.py's own fixtures use."""
    step = timedelta(minutes=Timeframe(timeframe).duration_minutes)
    start = occurred_at - step * (n - 1)
    return [_bar(start + step * i, 1.0 + i, symbol, timeframe) for i in range(n)]


def _build(occurred_at, window, upstream_session_name, upstream_is_rth, calendar=CME_RTH_V1, classifier=_SMALL):
    return build_market_context(
        symbol=Symbol("MNQU6"),
        timeframe=Timeframe("5m"),
        occurred_at=occurred_at,
        window=window,
        upstream_session_name=upstream_session_name,
        upstream_is_rth=upstream_is_rth,
        calendar=calendar,
        classifier=classifier,
    )


# ---- fully trusted context ----

def test_fully_trusted_context():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)  # MID_SESSION
    window = _window_ending_at(occurred_at, 10)
    result = _build(occurred_at, window, upstream_session_name="RTH", upstream_is_rth=True)

    assert result.session.drift_status == DriftStatus.AGREEMENT
    assert result.volatility.regime != VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.quality == ContextQuality.TRUSTED

    # Composition, not duplication: the nested results must equal calling
    # classify_session()/classify_volatility_regime() directly.
    assert result.session == classify_session(occurred_at, "RTH", True, CME_RTH_V1)
    assert result.volatility == classify_volatility_regime(window, _SMALL)

    assert result.symbol == Symbol("MNQU6")
    assert result.timeframe == Timeframe("5m")
    assert result.occurred_at == occurred_at
    assert result.classifier_version == "TEST_SMALL_V1"
    assert result.calendar_version == "CME_RTH_V1"


# ---- disagreement -> DEGRADED ----

def test_disagreement_degrades_quality():
    """The calibrated one-bar RTH-open disagreement (also exercised in
    test_market_context_session.py) - volatility is trustworthy, but
    session/upstream disagree, so quality must read DEGRADED, not TRUSTED."""
    occurred_at = _occurred_at(_CDT_DATE, 8, 30)
    window = _window_ending_at(occurred_at, 10)
    result = _build(occurred_at, window, upstream_session_name="OVERNIGHT", upstream_is_rth=False)

    assert result.session.drift_status == DriftStatus.DISAGREEMENT
    assert result.volatility.regime != VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.quality == ContextQuality.DEGRADED


# ---- upstream missing -> UNKNOWN ----

def test_upstream_missing_yields_unknown():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 10)
    result = _build(occurred_at, window, upstream_session_name=None, upstream_is_rth=None)

    assert result.session.drift_status == DriftStatus.UPSTREAM_MISSING
    assert result.volatility.regime != VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.quality == ContextQuality.UNKNOWN


# ---- insufficient history -> UNKNOWN ----

def test_insufficient_history_yields_unknown_even_with_agreement():
    """UNKNOWN must win over TRUSTED even when session/upstream fully
    agree - a genuinely too-short window is the stronger signal."""
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 5)  # < _SMALL.min_bars_required=10
    result = _build(occurred_at, window, upstream_session_name="RTH", upstream_is_rth=True)

    assert result.session.drift_status == DriftStatus.AGREEMENT
    assert result.volatility.regime == VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.volatility.atr_percentile_rank is None
    assert result.volatility.lookback_bars_used == 5
    assert result.quality == ContextQuality.UNKNOWN


# ---- invalid window ----

def test_empty_window_yields_unknown_without_raising():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    result = _build(occurred_at, [], upstream_session_name="RTH", upstream_is_rth=True)

    assert result.quality == ContextQuality.UNKNOWN
    assert result.volatility.regime == VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.volatility.atr_percentile_rank is None
    assert result.volatility.lookback_bars_used == 0
    # Identity is still preserved even though the window itself was unusable -
    # it comes from the explicit symbol/timeframe/occurred_at parameters, not
    # from window[-1] (which does not exist here).
    assert result.symbol == Symbol("MNQU6")
    assert result.timeframe == Timeframe("5m")
    assert result.occurred_at == occurred_at


def test_gapped_window_yields_unknown_and_reports_bars_supplied():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 10)
    gapped = window[:5] + window[6:]  # drop one bar, breaking contiguity
    result = _build(occurred_at, gapped, upstream_session_name="RTH", upstream_is_rth=True)

    assert result.quality == ContextQuality.UNKNOWN
    assert result.volatility.regime == VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.volatility.atr_percentile_rank is None
    assert result.volatility.lookback_bars_used == len(gapped)


def test_disagreement_plus_invalid_window_prefers_unknown_over_degraded():
    """UNKNOWN must take precedence over DEGRADED when both conditions hold
    at once - a data-quality problem outranks a session-labeling
    disagreement."""
    occurred_at = _occurred_at(_CDT_DATE, 8, 30)  # the calibrated disagreement bar
    result = _build(occurred_at, [], upstream_session_name="OVERNIGHT", upstream_is_rth=False)

    assert result.session.drift_status == DriftStatus.DISAGREEMENT
    assert result.quality == ContextQuality.UNKNOWN


# ---- fingerprint ----

def test_fingerprint_is_stable_across_separately_constructed_equal_definitions():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 10)
    calendar_a = SessionCalendarDefinition(
        version="CME_RTH_V1",
        params=SessionCalendarParams(
            rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
            pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
        ),
    )
    calendar_b = SessionCalendarDefinition(
        version="CME_RTH_V1",
        params=SessionCalendarParams(
            rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
            pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
        ),
    )
    assert calendar_a is not calendar_b

    result_a = _build(occurred_at, window, "RTH", True, calendar=calendar_a)
    result_b = _build(occurred_at, window, "RTH", True, calendar=calendar_b)
    assert result_a.context_fingerprint == result_b.context_fingerprint


def test_fingerprint_changes_when_classifier_params_change_even_with_the_same_version_string():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 10)
    other_classifier = RegimeClassifierDefinition(
        version="TEST_SMALL_V1",  # identical version string
        params=RegimeClassifierParams(
            lookback_bars=10, min_bars_required=10, compressed_percentile=20, expanded_percentile=80,
        ),
    )
    base = _build(occurred_at, window, "RTH", True, classifier=_SMALL)
    changed = _build(occurred_at, window, "RTH", True, classifier=other_classifier)

    assert base.classifier_version == changed.classifier_version
    assert base.context_fingerprint != changed.context_fingerprint


def test_fingerprint_changes_when_calendar_params_change_even_with_the_same_version_string():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 10)
    other_calendar = SessionCalendarDefinition(
        version="CME_RTH_V1",  # identical version string
        params=SessionCalendarParams(
            rth_open_hour_ct=9, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
            pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
        ),
    )
    base = _build(occurred_at, window, "RTH", True, calendar=CME_RTH_V1)
    changed = _build(occurred_at, window, "RTH", True, calendar=other_calendar)

    assert base.calendar_version == changed.calendar_version
    assert base.context_fingerprint != changed.context_fingerprint


def test_fingerprint_never_reflects_occurred_at_or_upstream_values():
    """Two calls differing only in occurred_at/upstream inputs (same
    definitions) must fingerprint identically - the fingerprint covers
    configuration only, never runtime values."""
    window_a = _window_ending_at(_occurred_at(_CDT_DATE, 9, 0), 10)
    window_b = _window_ending_at(_occurred_at(_CDT_DATE, 14, 0), 10)
    result_a = _build(_occurred_at(_CDT_DATE, 9, 0), window_a, "RTH", True)
    result_b = _build(_occurred_at(_CDT_DATE, 14, 0), window_b, None, None)

    assert result_a.occurred_at != result_b.occurred_at
    assert result_a.context_fingerprint == result_b.context_fingerprint


# ---- determinism ----

def test_build_market_context_is_deterministic_across_repeated_calls():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 10)
    first = _build(occurred_at, window, "RTH", True)
    second = _build(occurred_at, window, "RTH", True)
    assert first == second


# ---- purity ----

def test_build_market_context_does_not_mutate_its_window_argument():
    occurred_at = _occurred_at(_CDT_DATE, 12, 0)
    window = _window_ending_at(occurred_at, 10)
    window_copy = list(window)

    _build(occurred_at, window, "RTH", True)

    assert window == window_copy
    assert all(a is b for a, b in zip(window, window_copy))
