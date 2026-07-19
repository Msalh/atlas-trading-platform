import json
from datetime import datetime, timedelta, timezone

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.definitions import DEFAULT_VWAP_RELATIONSHIP_DEFINITION
from atlas.rule_engine.facts import evaluate_vwap_relationship
from atlas.rule_engine.models import FactDefinition, FactResult, InsufficientData
from atlas.rule_engine.registry import REGISTRY, required_history
from atlas.rule_engine.service import build_rule_engine_output, build_rule_engine_output_window, rule_engine_output_to_dict


def _state(event_id="e1", occurred_at="2026-07-18T13:35:00", **overrides):
    fields = dict(
        envelope=Event(
            event_type="bar_closed", source="tradingview",
            occurred_at=datetime.fromisoformat(occurred_at).replace(tzinfo=timezone.utc), event_id=event_id,
        ),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
    )
    fields.update(overrides)
    return MarketState(**fields)


def _definition(threshold=1.0, version="1.0"):
    return FactDefinition(name="vwap_relationship", version=version, params={"threshold": threshold})


class TestExtendedAbove:
    def test_clearly_above_threshold_is_extended_above(self):
        state = _state(distance_from_vwap_points=15.0, atr=10.0)  # normalized = 1.5 > 1.0
        result = evaluate_vwap_relationship(state, _definition())
        assert isinstance(result, FactResult)
        assert result.value == "extended_above"


class TestExtendedBelow:
    def test_clearly_below_threshold_is_extended_below(self):
        state = _state(distance_from_vwap_points=-15.0, atr=10.0)  # normalized = -1.5 < -1.0
        result = evaluate_vwap_relationship(state, _definition())
        assert result.value == "extended_below"


class TestWithinBand:
    def test_zero_distance_is_within_band(self):
        state = _state(distance_from_vwap_points=0.0, atr=10.0)
        result = evaluate_vwap_relationship(state, _definition())
        assert result.value == "within_band"

    def test_small_positive_distance_is_within_band(self):
        state = _state(distance_from_vwap_points=5.0, atr=10.0)  # normalized = 0.5
        result = evaluate_vwap_relationship(state, _definition())
        assert result.value == "within_band"

    def test_small_negative_distance_is_within_band(self):
        state = _state(distance_from_vwap_points=-5.0, atr=10.0)  # normalized = -0.5
        result = evaluate_vwap_relationship(state, _definition())
        assert result.value == "within_band"


class TestThresholdBoundaries:
    def test_exact_positive_boundary_is_within_band_not_extended(self):
        # normalized_distance == threshold exactly - strictly greater-than,
        # matching every other fact's boundary convention (e.g. rejection's
        # wick_body_ratio > threshold, not >=).
        state = _state(distance_from_vwap_points=10.0, atr=10.0)  # normalized = 1.0 == threshold
        result = evaluate_vwap_relationship(state, _definition(threshold=1.0))
        assert result.value == "within_band"

    def test_exact_negative_boundary_is_within_band_not_extended(self):
        state = _state(distance_from_vwap_points=-10.0, atr=10.0)  # normalized = -1.0 == -threshold
        result = evaluate_vwap_relationship(state, _definition(threshold=1.0))
        assert result.value == "within_band"

    def test_just_above_the_positive_boundary_is_extended_above(self):
        state = _state(distance_from_vwap_points=10.01, atr=10.0)  # normalized = 1.001
        result = evaluate_vwap_relationship(state, _definition(threshold=1.0))
        assert result.value == "extended_above"

    def test_just_below_the_negative_boundary_is_extended_below(self):
        state = _state(distance_from_vwap_points=-10.01, atr=10.0)  # normalized = -1.001
        result = evaluate_vwap_relationship(state, _definition(threshold=1.0))
        assert result.value == "extended_below"

    def test_just_inside_both_boundaries_stays_within_band(self):
        just_inside_positive = _state(distance_from_vwap_points=9.99, atr=10.0)  # normalized = 0.999
        just_inside_negative = _state(distance_from_vwap_points=-9.99, atr=10.0)  # normalized = -0.999
        assert evaluate_vwap_relationship(just_inside_positive, _definition(threshold=1.0)).value == "within_band"
        assert evaluate_vwap_relationship(just_inside_negative, _definition(threshold=1.0)).value == "within_band"


class TestInsufficientData:
    def test_missing_distance_from_vwap_points_is_insufficient(self):
        state = _state(distance_from_vwap_points=None, atr=10.0)
        result = evaluate_vwap_relationship(state, _definition())
        assert isinstance(result, InsufficientData)
        assert result.fact_name == "vwap_relationship"
        assert "distance_from_vwap_points" in result.reason

    def test_missing_atr_is_insufficient(self):
        state = _state(distance_from_vwap_points=5.0, atr=None)
        result = evaluate_vwap_relationship(state, _definition())
        assert isinstance(result, InsufficientData)
        assert "atr" in result.reason

    def test_zero_atr_is_insufficient_not_a_division_crash(self):
        state = _state(distance_from_vwap_points=5.0, atr=0.0)
        result = evaluate_vwap_relationship(state, _definition())
        assert isinstance(result, InsufficientData)
        assert "zero" in result.reason

    def test_distance_checked_before_atr(self):
        # both missing - distance_from_vwap_points's reason wins, matching
        # the documented check order.
        state = _state(distance_from_vwap_points=None, atr=None)
        result = evaluate_vwap_relationship(state, _definition())
        assert "distance_from_vwap_points" in result.reason


class TestDeterministicEvidence:
    def test_evidence_contains_all_four_documented_fields(self):
        state = _state(distance_from_vwap_points=15.0, atr=10.0)
        result = evaluate_vwap_relationship(state, _definition(threshold=1.0))
        assert result.evidence == {
            "distance_from_vwap_points": 15.0, "atr": 10.0, "normalized_distance": 1.5, "threshold": 1.0,
        }

    def test_evidence_normalized_distance_is_signed(self):
        above = evaluate_vwap_relationship(_state(distance_from_vwap_points=20.0, atr=10.0), _definition())
        below = evaluate_vwap_relationship(_state(distance_from_vwap_points=-20.0, atr=10.0), _definition())
        assert above.evidence["normalized_distance"] == 2.0
        assert below.evidence["normalized_distance"] == -2.0

    def test_deterministic_same_input_same_output(self):
        state = _state(distance_from_vwap_points=15.0, atr=10.0)
        assert evaluate_vwap_relationship(state, _definition()) == evaluate_vwap_relationship(state, _definition())

    def test_custom_definition_changes_evaluation_predictably(self):
        state = _state(distance_from_vwap_points=15.0, atr=10.0)  # normalized = 1.5
        assert evaluate_vwap_relationship(state, _definition(threshold=1.0)).value == "extended_above"
        assert evaluate_vwap_relationship(state, _definition(threshold=2.0)).value == "within_band"


class TestSerialization:
    def test_extended_value_is_json_dumps_safe(self):
        window = [_state(distance_from_vwap_points=15.0, atr=10.0)]
        output = build_rule_engine_output(window)
        as_dict = rule_engine_output_to_dict(output)
        json.dumps(as_dict)  # must not raise

        vwap_entry = next(f for f in as_dict["facts"] if f["name"] == "vwap_relationship")
        assert vwap_entry["status"] == "computed"
        assert vwap_entry["value"] == "extended_above"

    def test_insufficient_value_serializes_cleanly(self):
        window = [_state(distance_from_vwap_points=None, atr=10.0)]
        output = build_rule_engine_output(window)
        as_dict = rule_engine_output_to_dict(output)
        vwap_entry = next(f for f in as_dict["facts"] if f["name"] == "vwap_relationship")
        assert vwap_entry["status"] == "insufficient_data"


class TestRegistryIntegration:
    def test_vwap_relationship_is_registered(self):
        assert "vwap_relationship" in [r.name for r in REGISTRY]

    def test_registered_after_reclaim_appended_not_inserted(self):
        names = [r.name for r in REGISTRY]
        assert names[-1] == "vwap_relationship"
        assert names.index("vwap_relationship") == names.index("reclaim") + 1

    def test_registration_uses_default_definition(self):
        registration = next(r for r in REGISTRY if r.name == "vwap_relationship")
        assert registration.definition == DEFAULT_VWAP_RELATIONSHIP_DEFINITION

    def test_registration_is_single_bar_required_window_one(self):
        registration = next(r for r in REGISTRY if r.name == "vwap_relationship")
        assert registration.window_param is None
        assert registration.required_window == 1

    def test_registry_wide_required_history_unaffected_still_twenty(self):
        # trend_5m's window (20) remains the registry-wide maximum -
        # vwap_relationship (a single-bar fact) does not change it.
        assert required_history(REGISTRY) == 20


class TestEndToEndWindowOrchestration:
    def test_build_rule_engine_output_window_includes_vwap_relationship(self):
        base = datetime.fromisoformat("2026-07-18T13:00:00")
        window = [
            _state(
                event_id=f"e{i}", occurred_at=(base + timedelta(minutes=5 * i)).isoformat(),
                distance_from_vwap_points=15.0, atr=10.0,
            )
            for i in range(3)
        ]
        outputs = build_rule_engine_output_window(window)
        assert len(outputs) == 3
        for output in outputs:
            assert "vwap_relationship" in output.facts
            assert isinstance(output.facts["vwap_relationship"], FactResult)
            assert output.facts["vwap_relationship"].value == "extended_above"

    def test_early_bars_in_a_short_window_still_resolve_vwap_relationship(self):
        # vwap_relationship needs no history window (required_window == 1),
        # so it resolves on every bar even when other facts in the same
        # window are InsufficientData for lacking their own longer history.
        base = datetime.fromisoformat("2026-07-18T13:00:00")
        window = [
            _state(
                event_id=f"e{i}", occurred_at=(base + timedelta(minutes=5 * i)).isoformat(),
                distance_from_vwap_points=-15.0, atr=10.0,
            )
            for i in range(2)
        ]
        outputs = build_rule_engine_output_window(window)
        assert isinstance(outputs[0].facts["vwap_relationship"], FactResult)
        assert outputs[0].facts["vwap_relationship"].value == "extended_below"
        assert isinstance(outputs[0].facts["trend_5m"], InsufficientData)  # needs 20 bars, only 1 available
