from datetime import datetime, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
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
from atlas.rule_engine.registry import (
    REGISTRY,
    FactRegistration,
    required_history,
    single_bar_adapter,
    validate_registry,
)
from atlas.rule_engine.service import build_rule_engine_output


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


def _valid_definition(name="x", version="1.0", **params):
    return FactDefinition(name=name, version=version, params=params)


class TestFactRegistrationRequiredWindow:
    def test_single_bar_facts_require_window_of_one(self):
        for r in REGISTRY:
            if r.window_param is None:
                assert r.required_window == 1

    def test_windowed_facts_derive_from_definition_params(self):
        by_name = {r.name: r for r in REGISTRY}
        assert by_name["trend_5m"].required_window == DEFAULT_TREND_5M_DEFINITION.params["window"] == 20
        assert by_name["liquidity_sweep"].required_window == DEFAULT_LIQUIDITY_SWEEP_DEFINITION.params["window"] == 3
        assert by_name["reclaim"].required_window == DEFAULT_RECLAIM_DEFINITION.params["window"] == 3

    def test_required_window_reflects_the_definition_live_not_a_cached_copy(self):
        # proves required_window is DERIVED, not a second stored value that
        # could drift - constructing a registration against a custom
        # definition with a different window must reflect that window
        custom = FactRegistration(
            "custom", evaluate_trend_5m, _valid_definition(name="custom", window=42), window_param="window",
        )
        assert custom.required_window == 42


class TestValidateRegistry:
    def test_default_registry_is_valid(self):
        validate_registry(REGISTRY)  # must not raise

    def test_empty_registry_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_registry(())

    def test_duplicate_names_rejected(self):
        r1 = FactRegistration("dup", single_bar_adapter(evaluate_volume_spike), _valid_definition(name="dup", threshold=1.0))
        r2 = FactRegistration("dup", single_bar_adapter(evaluate_displacement), _valid_definition(name="dup", threshold=1.0))
        with pytest.raises(ValueError, match="duplicate"):
            validate_registry((r1, r2))

    def test_name_definition_mismatch_rejected(self):
        r = FactRegistration("a", single_bar_adapter(evaluate_volume_spike), _valid_definition(name="b", threshold=1.0))
        with pytest.raises(ValueError, match="does not match"):
            validate_registry((r,))

    def test_blank_definition_name_rejected(self):
        r = FactRegistration("a", single_bar_adapter(evaluate_volume_spike), _valid_definition(name="", threshold=1.0))
        with pytest.raises(ValueError, match="name must not be blank"):
            validate_registry((r,))

    def test_blank_definition_version_rejected(self):
        r = FactRegistration("a", single_bar_adapter(evaluate_volume_spike), _valid_definition(name="a", version="", threshold=1.0))
        with pytest.raises(ValueError, match="version must not be blank"):
            validate_registry((r,))

    def test_missing_window_param_key_rejected(self):
        r = FactRegistration("a", evaluate_trend_5m, _valid_definition(name="a", threshold=1.0), window_param="window")
        with pytest.raises(ValueError, match="is not present"):
            validate_registry((r,))

    def test_non_int_float_window_value_rejected(self):
        r = FactRegistration("a", evaluate_trend_5m, _valid_definition(name="a", window=20.5), window_param="window")
        with pytest.raises(ValueError, match="must be an int"):
            validate_registry((r,))

    def test_non_int_string_window_value_rejected(self):
        r = FactRegistration("a", evaluate_trend_5m, _valid_definition(name="a", window="20"), window_param="window")
        with pytest.raises(ValueError, match="must be an int"):
            validate_registry((r,))

    def test_bool_window_value_rejected_despite_being_an_int_subclass(self):
        # Python: isinstance(True, int) is True - a naive isinstance check
        # would wrongly accept this. type(value) is int must reject it.
        r = FactRegistration("a", evaluate_trend_5m, _valid_definition(name="a", window=True), window_param="window")
        with pytest.raises(ValueError, match="must be an int"):
            validate_registry((r,))

    def test_zero_window_value_rejected(self):
        r = FactRegistration("a", evaluate_trend_5m, _valid_definition(name="a", window=0), window_param="window")
        with pytest.raises(ValueError, match="must be >= 1"):
            validate_registry((r,))

    def test_negative_window_value_rejected(self):
        r = FactRegistration("a", evaluate_trend_5m, _valid_definition(name="a", window=-5), window_param="window")
        with pytest.raises(ValueError, match="must be >= 1"):
            validate_registry((r,))


class TestRequiredHistory:
    def test_default_registry_required_history_is_twenty(self):
        assert required_history(REGISTRY) == 20

    def test_reflects_a_different_registry_not_hardcoded(self):
        # proves required_history() is computed from whatever registry it's
        # given, not hardcoded to 20 - a synthetic registry with a larger
        # window must produce a larger result
        larger = (
            FactRegistration("big", evaluate_trend_5m, _valid_definition(name="big", window=100), window_param="window"),
            FactRegistration("small", single_bar_adapter(evaluate_volume_spike), _valid_definition(name="small", threshold=1.0)),
        )
        assert required_history(larger) == 100

    def test_all_single_bar_registry_required_history_is_one(self):
        only_single_bar = (
            FactRegistration("a", single_bar_adapter(evaluate_volume_spike), _valid_definition(name="a", threshold=1.0)),
        )
        assert required_history(only_single_bar) == 1


class TestSingleBarAdapter:
    def test_empty_window_returns_insufficient_data_not_index_error(self):
        adapted = single_bar_adapter(evaluate_volume_spike)
        result = adapted([], DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert isinstance(result, InsufficientData)
        assert result.fact_name == "volume_spike"
        assert "empty" in result.reason

    def test_non_empty_window_delegates_to_current_bar(self):
        adapted = single_bar_adapter(evaluate_volume_spike)
        older = _state(event_id="e0", occurred_at="2026-07-18T13:00:00", volume_ratio=0.1)
        current = _state(event_id="e1", occurred_at="2026-07-18T13:05:00", volume_ratio=2.0)
        result = adapted([older, current], DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert result == evaluate_volume_spike(current, DEFAULT_VOLUME_SPIKE_DEFINITION)
        assert result.value is True  # uses the CURRENT bar's ratio (2.0), not the older one's (0.1)


class TestRegistryOrder:
    def test_registration_order_is_deterministic(self):
        assert [r.name for r in REGISTRY] == [
            "volume_spike", "displacement", "rejection", "trend_5m", "liquidity_sweep", "reclaim",
            "vwap_relationship",
        ]

    def test_output_facts_preserve_registration_order(self):
        window = [_state(volume_ratio=1.0, open=Price(100.0, 0.25), high=Price(101.0, 0.25), low=Price(99.0, 0.25), close=Price(100.0, 0.25), atr=5.0)]
        output = build_rule_engine_output(window)
        assert list(output.facts.keys()) == [r.name for r in REGISTRY]


class TestRegistryBehaviorEquivalence:
    """The property this whole Sprint exists to prove without changing any
    observable behavior: the registry-driven build_rule_engine_output must
    produce EXACTLY what explicit, direct evaluation of all six facts
    already produced before this Sprint (Sprints 11-13's own approach)."""

    def _full_window(self):
        closes = [100.0 + i for i in range(20)]
        states = []
        for i, close in enumerate(closes):
            states.append(_state(
                event_id=f"e{i}", occurred_at=f"2026-07-18T13:{i:02d}:00",
                close=Price(close, 0.25), open=Price(close - 1, 0.25),
                high=Price(close + 5, 0.25), low=Price(close - 5, 0.25),
                volume_ratio=2.0, atr=10.0, distance_from_vwap_points=5.0,
                previous_day_high=Price(200.0, 0.25), previous_day_low=Price(50.0, 0.25),
                overnight_high=Price(200.0, 0.25), overnight_low=Price(50.0, 0.25),
            ))
        return states

    def test_registry_output_matches_explicit_direct_evaluation(self):
        window = self._full_window()
        current = window[-1]

        registry_output = build_rule_engine_output(window)

        expected_facts = {
            "volume_spike": evaluate_volume_spike(current, DEFAULT_VOLUME_SPIKE_DEFINITION),
            "displacement": evaluate_displacement(current, DEFAULT_DISPLACEMENT_DEFINITION),
            "rejection": evaluate_rejection(current, DEFAULT_REJECTION_DEFINITION),
            "trend_5m": evaluate_trend_5m(window, DEFAULT_TREND_5M_DEFINITION),
            "liquidity_sweep": evaluate_liquidity_sweep(window, DEFAULT_LIQUIDITY_SWEEP_DEFINITION),
            "reclaim": evaluate_reclaim(window, DEFAULT_RECLAIM_DEFINITION),
            "vwap_relationship": evaluate_vwap_relationship(current, DEFAULT_VWAP_RELATIONSHIP_DEFINITION),
        }

        assert registry_output.facts == expected_facts
        # a meaningful equivalence check, not a trivial all-InsufficientData one
        assert all(isinstance(outcome, FactResult) for outcome in expected_facts.values())
