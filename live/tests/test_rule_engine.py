import dataclasses
import json
from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository
from atlas.market_engine.service import replay_market_state
from atlas.rule_engine.definitions import (
    DEFAULT_DISPLACEMENT_DEFINITION,
    DEFAULT_LIQUIDITY_SWEEP_DEFINITION,
    DEFAULT_RECLAIM_DEFINITION,
    DEFAULT_REJECTION_DEFINITION,
    DEFAULT_TREND_5M_DEFINITION,
    DEFAULT_VOLUME_SPIKE_DEFINITION,
    DEFAULT_VWAP_RELATIONSHIP_DEFINITION,
)
from atlas.rule_engine.facts import (
    evaluate_displacement,
    evaluate_liquidity_sweep,
    evaluate_reclaim,
    evaluate_rejection,
    evaluate_trend_5m,
    evaluate_volume_spike,
    evaluate_vwap_relationship,
)
from atlas.rule_engine.models import FactDefinition, FactResult, InsufficientData
from atlas.rule_engine.registry import REGISTRY, required_history
from atlas.rule_engine.service import (
    build_rule_engine_output,
    build_rule_engine_output_window,
    evaluate_latest_rule_engine_output,
    rule_engine_output_to_dict,
)
from atlas.rule_engine.window_integrity import EmptyWindowError, WindowGapError


def _state(event_id="e1", occurred_at="2026-07-18T13:35:00", **overrides):
    fields = dict(
        envelope=Event(
            event_type="bar_closed",
            source="tradingview",
            occurred_at=datetime.fromisoformat(occurred_at).replace(tzinfo=timezone.utc),
            event_id=event_id,
        ),
        schema_version="1.0",
        symbol=Symbol("MNQU6"),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
    )
    fields.update(overrides)
    return MarketState(**fields)


def _window(closes, base_time="2026-07-18T13:00:00", **shared_overrides):
    """A chronologically ascending list of MarketState, one per close in
    `closes`, 5 minutes apart, current/latest bar last - the ordering
    convention every windowed fact expects. `shared_overrides` (e.g. atr,
    previous_day_high) applies identically to every bar - windowed facts
    only ever read reference levels/atr off the CURRENT (last) bar anyway."""
    base = datetime.fromisoformat(base_time)
    states = []
    for i, close in enumerate(closes):
        occurred_at = (base + timedelta(minutes=5 * i)).isoformat()
        fields = dict(event_id=f"e{i}", occurred_at=occurred_at, close=Price(close, 0.25))
        fields.update(shared_overrides)
        states.append(_state(**fields))
    return states


class TestFactDefinition:
    def test_params_is_immutable_even_if_constructed_from_a_plain_dict(self):
        mutable_source = {"threshold": 1.5}
        definition = FactDefinition(name="x", version="1.0", params=mutable_source)
        mutable_source["threshold"] = 999.0  # mutating the original dict afterward
        assert definition.params["threshold"] == 1.5  # must not have been affected

        with pytest.raises(TypeError):
            definition.params["threshold"] = 2.0  # MappingProxyType rejects direct writes

    def test_supports_non_float_param_types(self):
        definition = FactDefinition(
            name="x", version="1.0",
            params={"window": 20, "method": "slope", "flat": True, "threshold": 1.5},
        )
        assert definition.params["window"] == 20
        assert definition.params["method"] == "slope"
        assert definition.params["flat"] is True
        assert definition.params["threshold"] == 1.5


class TestEvaluateVolumeSpike:
    def test_above_threshold_is_true(self):
        result = evaluate_volume_spike(_state(volume_ratio=2.0), DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert isinstance(result, FactResult)
        assert result.value is True
        assert result.evidence == {"volume_ratio": 2.0, "threshold": 1.5}
        assert result.definition_version == "1.0"

    def test_below_threshold_is_false(self):
        result = evaluate_volume_spike(_state(volume_ratio=1.0), DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert result.value is False

    def test_exactly_at_threshold_is_false(self):
        result = evaluate_volume_spike(_state(volume_ratio=1.5), DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert result.value is False

    def test_missing_volume_ratio_is_insufficient_data(self):
        result = evaluate_volume_spike(_state(volume_ratio=None), DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert result.fact_name == "volume_spike"
        assert result.definition_version == "1.0"
        assert "volume_ratio" in result.reason

    def test_deterministic_same_input_same_output(self):
        state = _state(volume_ratio=1.8)
        assert (
            evaluate_volume_spike(state, DEFAULT_VOLUME_SPIKE_DEFINITION)
            == evaluate_volume_spike(state, DEFAULT_VOLUME_SPIKE_DEFINITION)
        )

    def test_custom_definition_changes_evaluation_predictably(self):
        state = _state(volume_ratio=1.2)
        lenient = FactDefinition(name="volume_spike", version="custom", params={"threshold": 1.0})
        strict = FactDefinition(name="volume_spike", version="custom", params={"threshold": 2.0})
        assert evaluate_volume_spike(state, lenient).value is True
        assert evaluate_volume_spike(state, strict).value is False


class TestEvaluateDisplacement:
    def test_exactly_at_threshold_is_false(self):
        # range = 15, atr = 10 -> ratio = 1.5, exactly the threshold - strictly
        # greater-than, not inclusive, mirroring volume_spike's own boundary rule
        result = evaluate_displacement(
            _state(high=Price(20135.00, 0.25), low=Price(20120.00, 0.25), atr=10.0), DEFAULT_DISPLACEMENT_DEFINITION,
        )
        assert isinstance(result, FactResult)
        assert result.value is False
        assert result.evidence["range_atr_ratio"] == pytest.approx(1.5)
        assert result.evidence["threshold"] == 1.5

    def test_below_threshold_is_false(self):
        result = evaluate_displacement(
            _state(high=Price(20121.00, 0.25), low=Price(20120.00, 0.25), atr=10.0), DEFAULT_DISPLACEMENT_DEFINITION,
        )
        assert result.value is False

    def test_clearly_above_threshold_is_true(self):
        result = evaluate_displacement(
            _state(high=Price(20140.00, 0.25), low=Price(20120.00, 0.25), atr=10.0), DEFAULT_DISPLACEMENT_DEFINITION,
        )
        assert result.value is True
        assert result.evidence["range_atr_ratio"] == pytest.approx(2.0)

    def test_missing_atr_is_insufficient_data(self):
        result = evaluate_displacement(
            _state(high=Price(20130.00, 0.25), low=Price(20120.00, 0.25), atr=None), DEFAULT_DISPLACEMENT_DEFINITION,
        )
        assert isinstance(result, InsufficientData)
        assert "atr" in result.reason

    def test_missing_high_low_is_insufficient_data(self):
        result = evaluate_displacement(_state(high=None, low=None, atr=10.0), DEFAULT_DISPLACEMENT_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert "high/low" in result.reason

    def test_zero_atr_is_insufficient_data_not_a_crash(self):
        result = evaluate_displacement(
            _state(high=Price(20130.00, 0.25), low=Price(20120.00, 0.25), atr=0.0), DEFAULT_DISPLACEMENT_DEFINITION,
        )
        assert isinstance(result, InsufficientData)
        assert "zero" in result.reason

    def test_deterministic_same_input_same_output(self):
        state = _state(high=Price(20140.00, 0.25), low=Price(20120.00, 0.25), atr=10.0)
        assert (
            evaluate_displacement(state, DEFAULT_DISPLACEMENT_DEFINITION)
            == evaluate_displacement(state, DEFAULT_DISPLACEMENT_DEFINITION)
        )

    def test_custom_definition_changes_evaluation_predictably(self):
        state = _state(high=Price(20130.00, 0.25), low=Price(20120.00, 0.25), atr=10.0)  # ratio = 1.0
        lenient = FactDefinition(name="displacement", version="custom", params={"threshold": 0.5})
        strict = FactDefinition(name="displacement", version="custom", params={"threshold": 1.5})
        assert evaluate_displacement(state, lenient).value is True
        assert evaluate_displacement(state, strict).value is False


class TestEvaluateRejection:
    def test_high_side_rejection_fires(self):
        # level = 20130, high = 20132 (breaches), open=20126, close=20125 (finishes below)
        # upper_wick = 20132 - max(20126, 20125) = 6, raw_body = 1, effective_body = max(1, 0.25) = 1
        # ratio = 6 / 1 = 6.0 > 2.0
        state = _state(
            open=Price(20126.00, 0.25), high=Price(20132.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert isinstance(result, FactResult)
        assert result.value is True
        assert len(result.evidence["qualifying_levels"]) == 1
        level_evidence = result.evidence["qualifying_levels"][0]
        assert level_evidence["reference_level"] == "previous_day_high"
        assert level_evidence["side"] == "high"
        assert level_evidence["wick_length"] == pytest.approx(6.0)
        assert level_evidence["raw_body_length"] == pytest.approx(1.0)
        assert level_evidence["effective_body"] == pytest.approx(1.0)
        assert level_evidence["wick_body_ratio"] == pytest.approx(6.0)
        assert level_evidence["close_distance_from_level"] == pytest.approx(5.0)

    def test_low_side_rejection_fires(self):
        # level = 20110, low = 20108 (breaches), open=20114, close=20115 (finishes above)
        # lower_wick = min(20114, 20115) - 20108 = 6, raw_body = 1, effective_body = 1, ratio = 6.0
        state = _state(
            open=Price(20114.00, 0.25), high=Price(20116.00, 0.25), low=Price(20108.00, 0.25), close=Price(20115.00, 0.25),
            overnight_low=Price(20110.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert result.value is True
        level_evidence = result.evidence["qualifying_levels"][0]
        assert level_evidence["reference_level"] == "overnight_low"
        assert level_evidence["side"] == "low"

    def test_high_reached_but_close_does_not_finish_below_is_no_rejection(self):
        # high breaches the level but close stays AT or above it - not a rejection
        state = _state(
            open=Price(20126.00, 0.25), high=Price(20132.00, 0.25), low=Price(20124.00, 0.25), close=Price(20131.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert result.value is False
        assert result.evidence["qualifying_levels"] == []

    def test_high_never_reaches_level_is_no_rejection(self):
        state = _state(
            open=Price(20120.00, 0.25), high=Price(20125.00, 0.25), low=Price(20118.00, 0.25), close=Price(20119.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert result.value is False

    def test_low_reached_but_close_does_not_finish_above_is_no_rejection(self):
        # low breaches the level but close stays AT or below it - not a rejection
        state = _state(
            open=Price(20114.00, 0.25), high=Price(20116.00, 0.25), low=Price(20108.00, 0.25), close=Price(20109.00, 0.25),
            overnight_low=Price(20110.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert result.value is False
        assert result.evidence["qualifying_levels"] == []

    def test_wick_body_ratio_below_threshold_is_no_rejection(self):
        # level = 20130, high = 20131 (breaches), close = 20128 (below) - wick = 20131 - max(open, close)
        # open = 20129, close = 20128 -> wick = 20131 - 20129 = 2, raw_body = 1, effective_body = 1, ratio = 2.0
        # exactly at threshold (2.0), strictly greater-than required, so NOT a rejection
        state = _state(
            open=Price(20129.00, 0.25), high=Price(20131.00, 0.25), low=Price(20127.00, 0.25), close=Price(20128.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert result.value is False

    def test_multiple_qualifying_levels_all_preserved(self):
        # both previous_day_high and overnight_high sit at/below this bar's high,
        # and the close finishes below both - both should qualify independently
        state = _state(
            open=Price(20126.00, 0.25), high=Price(20140.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
            overnight_high=Price(20128.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert result.value is True
        qualifying_names = {lvl["reference_level"] for lvl in result.evidence["qualifying_levels"]}
        assert qualifying_names == {"previous_day_high", "overnight_high"}

    def test_effective_body_floors_at_tick_size(self):
        # open == close (zero raw body) - effective_body must floor at tick_size (0.25), not zero
        state = _state(
            open=Price(20125.00, 0.25), high=Price(20132.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        level_evidence = result.evidence["qualifying_levels"][0]
        assert level_evidence["raw_body_length"] == pytest.approx(0.0)
        assert level_evidence["effective_body"] == pytest.approx(0.25)

    def test_missing_ohlc_is_insufficient_data(self):
        state = _state(open=None, high=None, low=None, close=None, previous_day_high=Price(20130.00, 0.25))
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert "open/high/low/close" in result.reason

    def test_no_reference_levels_at_all_is_insufficient_data(self):
        state = _state(
            open=Price(20126.00, 0.25), high=Price(20132.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25),
        )
        result = evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert "reference levels" in result.reason

    def test_deterministic_same_input_same_output(self):
        state = _state(
            open=Price(20126.00, 0.25), high=Price(20132.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        assert evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION) == evaluate_rejection(state, DEFAULT_REJECTION_DEFINITION)

    def test_custom_definition_changes_evaluation_predictably(self):
        # ratio = 6.0 for this bar (see test_high_side_rejection_fires)
        state = _state(
            open=Price(20126.00, 0.25), high=Price(20132.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        lenient = FactDefinition(name="rejection", version="custom", params={"wick_body_ratio_threshold": 1.0, "tick_size": 0.25})
        strict = FactDefinition(name="rejection", version="custom", params={"wick_body_ratio_threshold": 10.0, "tick_size": 0.25})
        assert evaluate_rejection(state, lenient).value is True
        assert evaluate_rejection(state, strict).value is False


class TestEvaluateTrend5m:
    def test_perfectly_linear_up_trend_is_classified_up(self):
        # slope = 1.0/bar, projected_move = 1.0 * 19 = 19, atr = 10 -> normalized = 1.9 > 1.0
        closes = [100.0 + i for i in range(20)]
        window = _window(closes, atr=10.0)
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert isinstance(result, FactResult)
        assert result.value == "up"
        assert result.evidence["slope"] == pytest.approx(1.0)
        assert result.evidence["normalized_move"] == pytest.approx(1.9)

    def test_perfectly_linear_down_trend_is_classified_down(self):
        closes = [119.0 - i for i in range(20)]
        window = _window(closes, atr=10.0)
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert result.value == "down"
        assert result.evidence["slope"] == pytest.approx(-1.0)
        assert result.evidence["normalized_move"] == pytest.approx(-1.9)

    def test_zero_slope_is_classified_flat(self):
        closes = [100.0] * 20
        window = _window(closes, atr=10.0)
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert result.value == "flat"
        assert result.evidence["slope"] == pytest.approx(0.0)

    def test_small_slope_within_band_is_classified_flat(self):
        # slope = 0.25/bar (one tick), projected_move = 0.25*19 = 4.75, atr = 10 -> normalized = 0.475, within (-1, 1)
        closes = [100.0 + 0.25 * i for i in range(20)]
        window = _window(closes, atr=10.0)
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert result.value == "flat"

    def test_fewer_than_window_size_bars_is_insufficient_data(self):
        window = _window([100.0, 101.0, 102.0], atr=10.0)
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert "20" in result.reason

    def test_missing_close_in_window_is_insufficient_data(self):
        window = _window([100.0 + i for i in range(20)], atr=10.0)
        window = window[:-1] + [dataclasses.replace(window[-1], close=None)]
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert isinstance(result, InsufficientData)

    def test_missing_atr_on_current_bar_is_insufficient_data(self):
        window = _window([100.0 + i for i in range(20)], atr=10.0)
        window = window[:-1] + [dataclasses.replace(window[-1], atr=None)]
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert "atr" in result.reason

    def test_zero_atr_on_current_bar_is_insufficient_data(self):
        window = _window([100.0 + i for i in range(20)], atr=10.0)
        window = window[:-1] + [dataclasses.replace(window[-1], atr=0.0)]
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert "zero" in result.reason

    def test_only_the_last_window_size_bars_are_used(self):
        # 25 bars: the first 5 are wild outliers that would change the slope
        # if included - only the last 20 (a clean uptrend) should be used
        outliers = [-1000.0, 5000.0, -3000.0, 8000.0, -6000.0]
        clean_uptrend = [100.0 + i for i in range(20)]
        window = _window(outliers + clean_uptrend, atr=10.0)
        result = evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert result.value == "up"
        assert result.evidence["slope"] == pytest.approx(1.0)

    def test_deterministic_same_input_same_output(self):
        window = _window([100.0 + i for i in range(20)], atr=10.0)
        assert evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION) == evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)

    def test_custom_definition_changes_evaluation_predictably(self):
        # slope=1.0, normalized_move = 1.9
        window = _window([100.0 + i for i in range(20)], atr=10.0)
        lenient = FactDefinition(name="trend_5m", version="custom", params={"window": 20, "up_threshold": 1.5, "down_threshold": -1.5})
        strict = FactDefinition(name="trend_5m", version="custom", params={"window": 20, "up_threshold": 2.5, "down_threshold": -2.5})
        assert evaluate_trend_5m(window, lenient).value == "up"
        assert evaluate_trend_5m(window, strict).value == "flat"


class TestEvaluateLiquiditySweep:
    def test_high_side_sweep_fires(self):
        # bar1's high (20135) breaches previous_day_high (20130); current close (20125) back below
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20125.00, 0.25), low=Price(20122.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20135.00, 0.25), low=Price(20124.00, 0.25), close=Price(20126.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20128.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25), previous_day_high=Price(20130.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert isinstance(result, FactResult)
        assert result.value is True
        assert len(result.evidence["qualifying_levels"]) == 1
        level_evidence = result.evidence["qualifying_levels"][0]
        assert level_evidence["reference_level"] == "previous_day_high"
        assert level_evidence["side"] == "high"
        assert level_evidence["excursion"] == pytest.approx(20135.00)
        assert level_evidence["excursion_occurred_at"] == window[1].envelope.occurred_at.isoformat()

    def test_low_side_sweep_fires(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20115.00, 0.25), low=Price(20112.00, 0.25), close=Price(20114.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20114.00, 0.25), low=Price(20105.00, 0.25), close=Price(20113.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20116.00, 0.25), low=Price(20112.00, 0.25), close=Price(20115.00, 0.25), overnight_low=Price(20110.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert result.value is True
        level_evidence = result.evidence["qualifying_levels"][0]
        assert level_evidence["reference_level"] == "overnight_low"
        assert level_evidence["side"] == "low"
        assert level_evidence["excursion"] == pytest.approx(20105.00)

    def test_no_breach_is_no_sweep(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20124.00, 0.25), low=Price(20120.00, 0.25), close=Price(20122.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20126.00, 0.25), low=Price(20120.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20127.00, 0.25), low=Price(20122.00, 0.25), close=Price(20125.00, 0.25), previous_day_high=Price(20130.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert result.value is False
        assert result.evidence["qualifying_levels"] == []

    def test_breach_but_close_not_back_is_no_sweep(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20125.00, 0.25), low=Price(20122.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20135.00, 0.25), low=Price(20124.00, 0.25), close=Price(20131.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20134.00, 0.25), low=Price(20130.00, 0.25), close=Price(20132.00, 0.25), previous_day_high=Price(20130.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert result.value is False

    def test_multiple_qualifying_levels_all_preserved(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20125.00, 0.25), low=Price(20122.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20140.00, 0.25), low=Price(20124.00, 0.25), close=Price(20126.00, 0.25)),
            _state(
                event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20128.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25),
                previous_day_high=Price(20130.00, 0.25), overnight_high=Price(20128.50, 0.25),
            ),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert result.value is True
        qualifying_names = {lvl["reference_level"] for lvl in result.evidence["qualifying_levels"]}
        assert qualifying_names == {"previous_day_high", "overnight_high"}

    def test_low_side_breach_but_close_not_back_is_no_sweep(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20115.00, 0.25), low=Price(20112.00, 0.25), close=Price(20114.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20112.00, 0.25), low=Price(20105.00, 0.25), close=Price(20107.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20109.00, 0.25), low=Price(20106.00, 0.25), close=Price(20108.00, 0.25), overnight_low=Price(20110.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert result.value is False

    def test_fewer_than_window_size_bars_is_insufficient_data(self):
        window = [_state(event_id="e0"), _state(event_id="e1", occurred_at="2026-07-18T13:05:00")]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert isinstance(result, InsufficientData)

    def test_missing_close_on_current_bar_is_insufficient_data(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20125.00, 0.25), low=Price(20122.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20135.00, 0.25), low=Price(20124.00, 0.25), close=Price(20126.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20128.00, 0.25), low=Price(20124.00, 0.25), close=None, previous_day_high=Price(20130.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert "close" in result.reason

    def test_missing_high_low_in_window_is_insufficient_data(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=None, low=None, close=Price(20124.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20135.00, 0.25), low=Price(20124.00, 0.25), close=Price(20126.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20128.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25), previous_day_high=Price(20130.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert isinstance(result, InsufficientData)

    def test_no_reference_levels_is_insufficient_data(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20125.00, 0.25), low=Price(20122.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20135.00, 0.25), low=Price(20124.00, 0.25), close=Price(20126.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20128.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25)),
        ]
        result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert isinstance(result, InsufficientData)

    def test_deterministic_same_input_same_output(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20125.00, 0.25), low=Price(20122.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20135.00, 0.25), low=Price(20124.00, 0.25), close=Price(20126.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20128.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25), previous_day_high=Price(20130.00, 0.25)),
        ]
        assert evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION) == evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)

    def test_custom_definition_window_size_changes_evaluation_predictably(self):
        # the breaching bar is 2 bars back from current - visible with window=3, not with window=2
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20135.00, 0.25), low=Price(20124.00, 0.25), close=Price(20126.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20126.00, 0.25), low=Price(20122.00, 0.25), close=Price(20124.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20128.00, 0.25), low=Price(20124.00, 0.25), close=Price(20125.00, 0.25), previous_day_high=Price(20130.00, 0.25)),
        ]
        wide = FactDefinition(name="liquidity_sweep", version="custom", params={"window": 3})
        narrow = FactDefinition(name="liquidity_sweep", version="custom", params={"window": 2})
        assert evaluate_liquidity_sweep(window, wide).value is True
        assert evaluate_liquidity_sweep(window, narrow).value is False


class TestEvaluateReclaim:
    def test_low_side_reclaim_fires(self):
        # bar1 closes below previous_day_low (20110): a "break"; current closes back above
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=Price(20112.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20108.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20111.00, 0.25), previous_day_low=Price(20110.00, 0.25)),
        ]
        result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert isinstance(result, FactResult)
        assert result.value is True
        level_evidence = result.evidence["qualifying_levels"][0]
        assert level_evidence["reference_level"] == "previous_day_low"
        assert level_evidence["side"] == "low"
        assert level_evidence["break_close"] == pytest.approx(20108.00)
        assert level_evidence["break_occurred_at"] == window[1].envelope.occurred_at.isoformat()

    def test_high_side_reclaim_fires(self):
        # bar1 closes above previous_day_high (20130): a "break"; current closes back below
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=Price(20128.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20132.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20129.00, 0.25), previous_day_high=Price(20130.00, 0.25)),
        ]
        result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert result.value is True
        level_evidence = result.evidence["qualifying_levels"][0]
        assert level_evidence["reference_level"] == "previous_day_high"
        assert level_evidence["side"] == "high"

    def test_no_prior_break_is_no_reclaim(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=Price(20112.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20113.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20111.00, 0.25), previous_day_low=Price(20110.00, 0.25)),
        ]
        result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert result.value is False
        assert result.evidence["qualifying_levels"] == []

    def test_prior_break_but_current_not_back_is_no_reclaim(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=Price(20112.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20108.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20107.00, 0.25), previous_day_low=Price(20110.00, 0.25)),
        ]
        result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert result.value is False

    def test_does_not_depend_on_liquidity_sweep(self):
        """The property Sprint 13's approved spec required: a bar can WICK
        through a level (satisfying liquidity_sweep's trigger) without its
        CLOSE ever going beyond that level (never satisfying reclaim's
        trigger) - the same window must produce sweep=True, reclaim=False,
        proving reclaim's own logic never consults liquidity_sweep's
        result."""
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", high=Price(20115.00, 0.25), low=Price(20114.00, 0.25), close=Price(20114.50, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", high=Price(20112.00, 0.25), low=Price(20109.00, 0.25), close=Price(20111.00, 0.25)),
            _state(
                event_id="e2", occurred_at="2026-07-18T13:10:00", high=Price(20113.00, 0.25), low=Price(20111.00, 0.25), close=Price(20112.00, 0.25),
                previous_day_low=Price(20110.00, 0.25),
            ),
        ]
        sweep_result = evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        reclaim_result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert sweep_result.value is True   # bar1's low (20109) wicked below the level (20110)
        assert reclaim_result.value is False  # but no bar's CLOSE ever went below the level

    def test_fewer_than_window_size_bars_is_insufficient_data(self):
        window = [_state(event_id="e0"), _state(event_id="e1", occurred_at="2026-07-18T13:05:00")]
        result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert isinstance(result, InsufficientData)

    def test_window_with_no_earlier_bars_is_insufficient_data(self):
        window = [_state(event_id="e0", close=Price(20112.00, 0.25), previous_day_low=Price(20110.00, 0.25))]
        single_bar_definition = FactDefinition(name="reclaim", version="custom", params={"window": 1})
        result = evaluate_reclaim(window, single_bar_definition)
        assert isinstance(result, InsufficientData)
        assert "prior close" in result.reason

    def test_missing_close_in_window_is_insufficient_data(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=None),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20108.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20111.00, 0.25), previous_day_low=Price(20110.00, 0.25)),
        ]
        result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert isinstance(result, InsufficientData)

    def test_no_reference_levels_is_insufficient_data(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=Price(20112.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20108.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20111.00, 0.25)),
        ]
        result = evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert isinstance(result, InsufficientData)

    def test_deterministic_same_input_same_output(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=Price(20112.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20108.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20111.00, 0.25), previous_day_low=Price(20110.00, 0.25)),
        ]
        assert evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION) == evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)

    def test_custom_definition_window_size_changes_evaluation_predictably(self):
        window = [
            _state(event_id="e0", occurred_at="2026-07-18T13:00:00", close=Price(20108.00, 0.25)),
            _state(event_id="e1", occurred_at="2026-07-18T13:05:00", close=Price(20112.00, 0.25)),
            _state(event_id="e2", occurred_at="2026-07-18T13:10:00", close=Price(20111.00, 0.25), previous_day_low=Price(20110.00, 0.25)),
        ]
        wide = FactDefinition(name="reclaim", version="custom", params={"window": 3})
        narrow = FactDefinition(name="reclaim", version="custom", params={"window": 2})
        assert evaluate_reclaim(window, wide).value is True
        assert evaluate_reclaim(window, narrow).value is False


class TestBuildRuleEngineOutput:
    def _fully_populated_window(self, **overrides):
        fields = dict(
            volume_ratio=2.0, high=Price(20140.00, 0.25), low=Price(20120.00, 0.25), atr=10.0,
            open=Price(20126.00, 0.25), close=Price(20125.00, 0.25), distance_from_vwap_points=5.0,
        )
        fields.update(overrides)
        return [_state(**fields)]

    def test_shape_and_versioning(self):
        window = self._fully_populated_window()
        output = build_rule_engine_output(window)
        current = window[-1]
        assert output.schema_version == "1.0"
        assert output.symbol == "MNQU6"
        assert output.timeframe == "5m"
        assert output.occurred_at == current.envelope.occurred_at.isoformat()
        assert set(output.facts.keys()) == {
            "volume_spike", "displacement", "rejection", "trend_5m", "liquidity_sweep", "reclaim",
            "vwap_relationship",
        }

    def test_facts_reflect_individual_evaluations(self):
        window = self._fully_populated_window()
        current = window[-1]
        output = build_rule_engine_output(window)
        assert output.facts["volume_spike"] == evaluate_volume_spike(current, DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert output.facts["displacement"] == evaluate_displacement(current, DEFAULT_DISPLACEMENT_DEFINITION)
        assert output.facts["rejection"] == evaluate_rejection(current, DEFAULT_REJECTION_DEFINITION)
        assert output.facts["trend_5m"] == evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION)
        assert output.facts["liquidity_sweep"] == evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION)
        assert output.facts["reclaim"] == evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION)
        assert output.facts["vwap_relationship"] == evaluate_vwap_relationship(current, DEFAULT_VWAP_RELATIONSHIP_DEFINITION)

    def test_insufficient_data_facts_do_not_crash_assembly(self):
        window = [_state(volume_ratio=None, high=None, low=None, atr=None, open=None, close=None)]
        output = build_rule_engine_output(window)
        for fact_name in output.facts:
            assert isinstance(output.facts[fact_name], InsufficientData)

    def test_windowed_facts_produce_a_real_result_given_enough_history(self):
        # a full 20-bar, perfectly linear up-trending window - long enough for
        # trend_5m, and with a breach+reclose bar for liquidity_sweep too
        closes = [100.0 + i for i in range(20)]
        window = _window(
            closes, atr=10.0,
            open=Price(20126.00, 0.25), high=Price(20140.00, 0.25), low=Price(20120.00, 0.25),
            previous_day_high=Price(20130.00, 0.25),
        )
        output = build_rule_engine_output(window)
        assert isinstance(output.facts["trend_5m"], FactResult)
        assert output.facts["trend_5m"].value == "up"

    def test_deterministic_same_input_same_output(self):
        window = self._fully_populated_window()
        assert build_rule_engine_output(window) == build_rule_engine_output(window)


class TestBuildRuleEngineOutputWindow:
    def _full_window(self, count=20, **overrides):
        closes = [100.0 + i for i in range(count)]
        fields = dict(
            atr=10.0, open=Price(20126.00, 0.25), high=Price(20140.00, 0.25),
            low=Price(20120.00, 0.25), previous_day_high=Price(20130.00, 0.25),
        )
        fields.update(overrides)
        return _window(closes, **fields)

    def test_empty_window_raises_empty_window_error(self):
        with pytest.raises(EmptyWindowError):
            build_rule_engine_output_window([])

    def test_gap_in_window_raises_before_evaluating_anything(self):
        window = self._full_window(count=2)
        window[1] = _state(
            event_id="e1b",
            occurred_at=(window[0].envelope.occurred_at + timedelta(minutes=10)).isoformat(),
            close=Price(101.0, 0.25),
        )
        with pytest.raises(WindowGapError):
            build_rule_engine_output_window(window)

    def test_one_output_per_input_bar_in_the_same_order(self):
        window = self._full_window()
        outputs = build_rule_engine_output_window(window)
        assert len(outputs) == len(window)
        assert [o.occurred_at for o in outputs] == [s.envelope.occurred_at.isoformat() for s in window]

    def test_early_bars_show_insufficient_data_for_long_window_facts(self):
        window = self._full_window()
        outputs = build_rule_engine_output_window(window)
        assert isinstance(outputs[0].facts["trend_5m"], InsufficientData)
        assert isinstance(outputs[-1].facts["trend_5m"], FactResult)
        assert outputs[-1].facts["trend_5m"].value == "up"

    def test_single_bar_facts_compute_even_on_the_first_bar(self):
        window = self._full_window(volume_ratio=2.0)
        outputs = build_rule_engine_output_window(window)
        assert isinstance(outputs[0].facts["volume_spike"], FactResult)

    def test_matches_build_rule_engine_output_called_per_bar(self):
        window = self._full_window()
        outputs = build_rule_engine_output_window(window)
        depth = required_history(REGISTRY)
        for i, output in enumerate(outputs):
            assert output == build_rule_engine_output(window[max(0, i - depth + 1): i + 1])

    def test_deterministic_same_input_same_output(self):
        window = self._full_window(count=3)
        assert build_rule_engine_output_window(window) == build_rule_engine_output_window(window)


class TestEvaluateLatestRuleEngineOutput:
    @pytest.fixture
    def repo(self):
        return InMemoryMarketStateRepository()

    @pytest.mark.asyncio
    async def test_no_data_returns_none(self, repo):
        result = await evaluate_latest_rule_engine_output(Symbol("MNQU6"), Timeframe.M5, repo)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_output_for_latest_stored_state(self, repo):
        state = _state(volume_ratio=2.0, high=Price(20140.00, 0.25), low=Price(20120.00, 0.25), atr=10.0)
        await repo.ingest(state, raw_payload="{}")
        result = await evaluate_latest_rule_engine_output(Symbol("MNQU6"), Timeframe.M5, repo)
        assert result == build_rule_engine_output([state])

    @pytest.mark.asyncio
    async def test_fetches_enough_history_for_windowed_facts(self, repo):
        # ingest 20 ascending bars - the live path must fetch enough history
        # (HISTORY_LIMIT=20) for trend_5m to actually compute, not just
        # evaluate the single latest bar
        closes = [100.0 + i for i in range(20)]
        for i, close in enumerate(closes):
            await repo.ingest(
                _state(event_id=f"e{i}", occurred_at=f"2026-07-18T13:{i:02d}:00", close=Price(close, 0.25), atr=10.0),
                raw_payload="{}",
            )
        result = await evaluate_latest_rule_engine_output(Symbol("MNQU6"), Timeframe.M5, repo)
        assert isinstance(result.facts["trend_5m"], FactResult)
        assert result.facts["trend_5m"].value == "up"


class TestReplayReproducibility:
    """The property Sprint 11 introduced and Sprints 12/13 continue to
    prove: the Rule Engine's output depends only on the WINDOW of
    MarketState's own field values, never on how that window arrived.
    Ingest once, then fetch the exact same underlying data through two
    different Market Engine read paths - live (get_history, reversed) and
    Sprint 10's replay (replay_market_state) - and assert the Rule Engine
    produces byte-for-byte identical output either way, across every
    registered fact including this Sprint's three windowed ones."""

    @pytest.fixture
    def repo(self):
        return InMemoryMarketStateRepository()

    @pytest.mark.asyncio
    async def test_live_and_replayed_window_produce_identical_rule_engine_output(self, repo):
        state = _state(
            event_id="e-replay-1",
            volume_ratio=2.2,
            open=Price(20126.00, 0.25), high=Price(20145.00, 0.25), low=Price(20120.00, 0.25), close=Price(20125.00, 0.25),
            atr=8.0,
            previous_day_high=Price(20130.00, 0.25),
        )
        await repo.ingest(state, raw_payload="{}")

        live_history = await repo.get_history(Symbol("MNQU6"), Timeframe.M5, limit=20)
        live_window = list(reversed(live_history))

        replayed_window = [
            s async for s in replay_market_state(
                Symbol("MNQU6"), Timeframe.M5,
                datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
                10000, repo,
            )
        ]
        assert len(replayed_window) == 1

        assert build_rule_engine_output(live_window) == build_rule_engine_output(replayed_window)

    @pytest.mark.asyncio
    async def test_reproducible_across_a_full_replayed_series(self, repo):
        closes = [100.0 + i for i in range(20)]
        states = [
            _state(
                event_id=f"e-series-{i}", occurred_at=f"2026-07-18T13:{i:02d}:00",
                volume_ratio=1.0 + i * 0.05,
                open=Price(20120.00, 0.25), high=Price(20120.00 + (i % 3), 0.25), low=Price(20115.00, 0.25),
                close=Price(closes[i], 0.25),
                atr=5.0,
                previous_day_high=Price(20119.00, 0.25),
            )
            for i in range(20)
        ]
        for state in states:
            await repo.ingest(state, raw_payload="{}")

        # cumulative windows: "as of bar i", the window is every bar up to
        # and including i - matching what a real caller evaluating the Rule
        # Engine at that point in time would have seen
        expected_outputs = {
            states[i].envelope.event_id: build_rule_engine_output(states[: i + 1])
            for i in range(len(states))
        }

        replayed = [
            s async for s in replay_market_state(
                Symbol("MNQU6"), Timeframe.M5,
                datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
                10000, repo,
            )
        ]
        assert len(replayed) == 20
        for i in range(len(replayed)):
            cumulative_replayed_window = replayed[: i + 1]
            expected = expected_outputs[replayed[i].envelope.event_id]
            assert build_rule_engine_output(cumulative_replayed_window) == expected


class TestRuleEngineOutputToDict:
    """Sprint 15. rule_engine_output_to_dict is a pure domain serialization
    function - these tests never touch HTTP/FastAPI, matching the
    requirement that this function must not know about the transport
    envelope."""

    def _full_window(self):
        # a complete window: every fact computes a real FactResult, not
        # InsufficientData - the same construction Sprint 14's registry
        # behavior-equivalence test used, duplicated here per this project's
        # established per-file-helper convention.
        closes = [100.0 + i for i in range(20)]
        states = []
        for i, close in enumerate(closes):
            states.append(_state(
                event_id=f"e{i}", occurred_at=f"2026-07-18T13:{i:02d}:00",
                close=Price(close, 0.25), open=Price(close - 1, 0.25),
                high=Price(close + 5, 0.25), low=Price(close - 5, 0.25),
                volume_ratio=2.0, atr=10.0,
                previous_day_high=Price(200.0, 0.25), previous_day_low=Price(50.0, 0.25),
                overnight_high=Price(200.0, 0.25), overnight_low=Price(50.0, 0.25),
            ))
        return states

    def test_does_not_build_the_http_envelope(self):
        # proves the "must not know about FastAPI" boundary directly: no
        # ok/found keys - those belong to the route, not this function
        output = build_rule_engine_output(self._full_window())
        result = rule_engine_output_to_dict(output)
        assert "ok" not in result
        assert "found" not in result
        assert set(result.keys()) == {"schema_version", "symbol", "timeframe", "occurred_at", "facts"}

    def test_schema_version_symbol_timeframe_occurred_at_present(self):
        window = self._full_window()
        output = build_rule_engine_output(window)
        result = rule_engine_output_to_dict(output)
        assert result["schema_version"] == output.schema_version
        assert result["symbol"] == "MNQU6"
        assert result["timeframe"] == "5m"
        assert result["occurred_at"] == window[-1].envelope.occurred_at.isoformat()

    def test_facts_is_a_list_not_an_object(self):
        output = build_rule_engine_output(self._full_window())
        result = rule_engine_output_to_dict(output)
        assert isinstance(result["facts"], list)

    def test_facts_preserve_registry_order(self):
        output = build_rule_engine_output(self._full_window())
        result = rule_engine_output_to_dict(output)
        assert [f["name"] for f in result["facts"]] == [r.name for r in REGISTRY]

    def test_computed_fact_serializes_with_value_and_evidence(self):
        output = build_rule_engine_output(self._full_window())
        result = rule_engine_output_to_dict(output)
        volume_spike = next(f for f in result["facts"] if f["name"] == "volume_spike")
        assert volume_spike["status"] == "computed"
        assert volume_spike["value"] is True
        assert volume_spike["definition_version"] == "1.0"
        assert volume_spike["evidence"] == {"volume_ratio": 2.0, "threshold": 1.5}
        assert "reason" not in volume_spike

    def test_insufficient_data_fact_serializes_with_reason(self):
        # a single-bar window - trend_5m (needs 20 bars) reports InsufficientData
        window = [_state(volume_ratio=1.0)]
        output = build_rule_engine_output(window)
        result = rule_engine_output_to_dict(output)
        trend_5m = next(f for f in result["facts"] if f["name"] == "trend_5m")
        assert trend_5m["status"] == "insufficient_data"
        assert trend_5m["definition_version"] == "1.0"
        assert isinstance(trend_5m["reason"], str) and trend_5m["reason"]
        assert "value" not in trend_5m
        assert "evidence" not in trend_5m

    def test_every_fact_carries_its_own_definition_version(self):
        output = build_rule_engine_output(self._full_window())
        result = rule_engine_output_to_dict(output)
        assert all(isinstance(f["definition_version"], str) and f["definition_version"] for f in result["facts"])

    def test_complete_output_is_json_dumps_safe(self):
        # the explicit regression guard: every one of the six current facts'
        # evidence must already be built from ordinary JSON-native
        # primitives/lists/dicts - no default=str, no conversion framework,
        # this must succeed with zero special handling
        output = build_rule_engine_output(self._full_window())
        result = rule_engine_output_to_dict(output)
        serialized = json.dumps(result)
        assert json.loads(serialized) == result
