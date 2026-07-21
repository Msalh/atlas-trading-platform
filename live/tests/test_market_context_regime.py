"""
Phase N1, Sprint 3. Table-driven tests for
atlas.market_context.regime.classify_volatility_regime() - warm-up
boundaries, every VolatilityRegime bucket, percentile edge cases, and
window_integrity reuse (no new validation logic).

Most cases use a small, hand-verifiable custom RegimeClassifierDefinition
(lookback_bars=10) rather than the real 288-bar REGIME_CLASSIFIER_V1, so
every expected rank can be checked by counting on paper - one dedicated
test confirms the real constant still works end to end.
"""
from datetime import datetime, timedelta, timezone

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import (
    REGIME_CLASSIFIER_V1,
    RegimeClassifierDefinition,
    RegimeClassifierParams,
)
from atlas.market_context.models import VolatilityRegime
from atlas.market_context.regime import classify_volatility_regime
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.window_integrity import EmptyWindowError, MixedSymbolError, WindowGapError

_SMALL = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=10, min_bars_required=10, compressed_percentile=25, expanded_percentile=75,
    ),
)


def _bar(index: int, atr: float, symbol: str = "MNQU6", timeframe: str = "5m") -> MarketState:
    occurred_at = datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc) + timedelta(
        minutes=Timeframe(timeframe).duration_minutes * index,
    )
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at),
        schema_version="1.0",
        symbol=Symbol(symbol),
        timeframe=Timeframe(timeframe),
        bar_status=BarStatus.CLOSED,
        atr=atr,
    )


def _window(atrs: list[float]) -> list[MarketState]:
    return [_bar(i, atr) for i, atr in enumerate(atrs)]


# ---- 1-3: warm-up boundary ----

def test_insufficient_history_when_fewer_bars_than_min_bars_required():
    window = _window([1.0] * 5)  # 5 < min_bars_required=10
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.regime == VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.atr_percentile_rank is None
    assert result.lookback_bars_used == 5


def test_classifies_normally_at_exactly_min_bars_required():
    window = _window([1.0] * 10)  # exactly 10 == min_bars_required
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.regime != VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.atr_percentile_rank is not None
    assert result.lookback_bars_used == 10


def test_insufficient_history_one_bar_below_threshold():
    window = _window([1.0] * 9)  # one less than min_bars_required=10
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.regime == VolatilityRegime.INSUFFICIENT_HISTORY
    assert result.atr_percentile_rank is None
    assert result.lookback_bars_used == 9


def test_never_silently_classifies_normal_during_warm_up():
    for n in range(1, 10):  # every warm-up length below min_bars_required=10
        window = _window([1.0] * n)
        result = classify_volatility_regime(window, classifier=_SMALL)
        assert result.regime == VolatilityRegime.INSUFFICIENT_HISTORY, f"n={n} must be INSUFFICIENT_HISTORY"
        assert result.regime != VolatilityRegime.NORMAL


# ---- 4-6: each VolatilityRegime bucket ----

def test_compressed_when_current_bar_is_near_the_bottom_of_its_window():
    # 9 bars at atr=10, current (last) bar at atr=1: only itself is <= itself -> rank 1/10 = 0.10
    window = _window([10.0] * 9 + [1.0])
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.atr_percentile_rank == pytest.approx(0.10)
    assert result.regime == VolatilityRegime.COMPRESSED


def test_normal_when_current_bar_is_mid_pack():
    # [1,2,3,4,5,6,7,8,9,5] - current (last) = 5; values <= 5: {1,2,3,4,5,5(itself)} = 6 -> rank 0.6
    window = _window([1, 2, 3, 4, 5, 6, 7, 8, 9, 5])
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.atr_percentile_rank == pytest.approx(0.6)
    assert result.regime == VolatilityRegime.NORMAL


def test_expanded_when_current_bar_is_the_new_maximum():
    window = _window([1, 2, 3, 4, 5, 6, 7, 8, 9, 20])
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.atr_percentile_rank == pytest.approx(1.0)
    assert result.regime == VolatilityRegime.EXPANDED


# ---- 7: percentile edge cases - exactly at the configured thresholds ----

_BOUNDARY = RegimeClassifierDefinition(
    version="TEST_BOUNDARY_V1",
    params=RegimeClassifierParams(
        lookback_bars=4, min_bars_required=4, compressed_percentile=25, expanded_percentile=75,
    ),
)


def test_rank_exactly_at_the_compressed_boundary_is_compressed_not_normal():
    # [2,3,4,1] - current (last) = 1; values <= 1: {1(itself)} = 1 -> rank 1/4 = 0.25 exactly
    window = _window([2, 3, 4, 1])
    result = classify_volatility_regime(window, classifier=_BOUNDARY)
    assert result.atr_percentile_rank == pytest.approx(0.25)
    assert result.regime == VolatilityRegime.COMPRESSED


def test_rank_exactly_at_the_expanded_boundary_is_expanded_not_normal():
    # [1,2,4,3] - current (last) = 3; values <= 3: {1,2,3(itself)} = 3 -> rank 3/4 = 0.75 exactly
    window = _window([1, 2, 4, 3])
    result = classify_volatility_regime(window, classifier=_BOUNDARY)
    assert result.atr_percentile_rank == pytest.approx(0.75)
    assert result.regime == VolatilityRegime.EXPANDED


# ---- 8: constant ATR values ----

def test_constant_atr_ranks_at_1_0_and_reads_as_expanded():
    """Documented, deliberate consequence of the "<=" tie convention: a bar
    tied with its entire window ranks at the top, not the middle."""
    window = _window([7.5] * 10)
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.atr_percentile_rank == pytest.approx(1.0)
    assert result.regime == VolatilityRegime.EXPANDED


# ---- 9: strictly increasing ATR ----

def test_strictly_increasing_atr_ranks_the_current_bar_at_the_maximum():
    window = _window([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.atr_percentile_rank == pytest.approx(1.0)
    assert result.regime == VolatilityRegime.EXPANDED


# ---- 10: strictly decreasing ATR ----

def test_strictly_decreasing_atr_ranks_the_current_bar_at_the_minimum():
    window = _window([10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.atr_percentile_rank == pytest.approx(0.1)
    assert result.regime == VolatilityRegime.COMPRESSED


# ---- 11: duplicate ATR values (not all equal) ----

def test_duplicate_atr_values_count_every_tie_including_the_current_bar():
    # [1,1,1,5,5,5,9,9,9,5] - current (last) = 5; values <= 5: indices 0,1,2,3,4,5,9 = 7 -> rank 0.7
    window = _window([1, 1, 1, 5, 5, 5, 9, 9, 9, 5])
    result = classify_volatility_regime(window, classifier=_SMALL)
    assert result.atr_percentile_rank == pytest.approx(0.7)
    assert result.regime == VolatilityRegime.NORMAL


# ---- 12: window validation failures - reused as-is, no new handling ----

def test_empty_window_raises_the_existing_window_integrity_error():
    with pytest.raises(EmptyWindowError):
        classify_volatility_regime([], classifier=_SMALL)


def test_mixed_symbol_window_raises_the_existing_window_integrity_error():
    window = _window([1.0] * 9) + [_bar(9, 1.0, symbol="ESU6")]
    with pytest.raises(MixedSymbolError):
        classify_volatility_regime(window, classifier=_SMALL)


def test_non_contiguous_window_raises_the_existing_window_integrity_error():
    window = _window([1.0] * 10)
    # Introduce a gap: push the last bar's timestamp forward by an extra 5 minutes.
    gapped_last = MarketState(
        envelope=Event(
            event_type="bar_closed", source="test",
            occurred_at=window[-1].envelope.occurred_at + timedelta(minutes=5),
        ),
        schema_version="1.0", symbol=window[-1].symbol, timeframe=window[-1].timeframe,
        bar_status=BarStatus.CLOSED, atr=window[-1].atr,
    )
    window = window[:-1] + [gapped_last]
    with pytest.raises(WindowGapError):
        classify_volatility_regime(window, classifier=_SMALL)


# ---- lookback_bars capping: a caller-supplied window longer than lookback_bars ----

def test_a_window_longer_than_lookback_bars_is_capped_to_the_trailing_lookback_bars_only():
    small_cap = RegimeClassifierDefinition(
        version="TEST_CAP_V1",
        params=RegimeClassifierParams(
            lookback_bars=5, min_bars_required=5, compressed_percentile=25, expanded_percentile=75,
        ),
    )
    # 15 bars supplied, but lookback_bars=5 - only the trailing 5 [100,100,100,100,1]
    # should be used; the leading 10 low-ATR bars must not affect the rank.
    window = _window([1.0] * 10 + [100, 100, 100, 100, 1])
    result = classify_volatility_regime(window, classifier=small_cap)
    assert result.lookback_bars_used == 5
    assert result.atr_percentile_rank == pytest.approx(0.2)  # only itself <= itself among the trailing 5
    assert result.regime == VolatilityRegime.COMPRESSED


# ---- real REGIME_CLASSIFIER_V1 constant, end to end ----

def test_works_end_to_end_with_the_real_regime_classifier_v1_default():
    window = _window([10.0 if i % 2 == 0 else 50.0 for i in range(288)])
    result = classify_volatility_regime(window)  # classifier defaults to REGIME_CLASSIFIER_V1
    assert result.lookback_bars_used == 288
    assert result.atr_percentile_rank is not None
    assert result.regime in (VolatilityRegime.COMPRESSED, VolatilityRegime.NORMAL, VolatilityRegime.EXPANDED)


def test_regime_classifier_v1_constant_matches_definitions_module():
    assert REGIME_CLASSIFIER_V1.params.lookback_bars == 288
    assert REGIME_CLASSIFIER_V1.params.min_bars_required == 288


# ---- purity ----

def test_classify_volatility_regime_is_pure_same_inputs_produce_identical_output():
    window = _window([1, 2, 3, 4, 5, 6, 7, 8, 9, 5])
    first = classify_volatility_regime(window, classifier=_SMALL)
    second = classify_volatility_regime(window, classifier=_SMALL)
    assert first == second
