import json
from datetime import datetime, timedelta, timezone

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.models import FactResult
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.models import InsufficientData, SetupEvaluationContext, SetupFamily, SetupResult, Severity
from atlas.setup_engine.registry import REGISTRY, required_history, validate_registry
from atlas.setup_engine.service import build_setup_engine_output, setup_engine_output_to_dict
from atlas.setup_engine.setups.vwap_extension_with_volume_confirmation import (
    DEFAULT_VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_DEFINITION,
    VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION,
    evaluate_vwap_extension_with_volume_confirmation,
)


def _vwap_relationship(value="extended_above", distance=15.0, atr=10.0, threshold=1.0):
    return FactResult(
        fact_name="vwap_relationship", definition_version="1.0", value=value,
        evidence={"distance_from_vwap_points": distance, "atr": atr, "normalized_distance": distance / atr, "threshold": threshold},
    )


def _vwap_relationship_insufficient(reason="atr is zero - a normalized distance is undefined"):
    return FactInsufficientData(fact_name="vwap_relationship", definition_version="1.0", reason=reason)


def _volume_spike(value=True, ratio=2.0, threshold=1.5):
    return FactResult(
        fact_name="volume_spike", definition_version="1.0", value=value,
        evidence={"volume_ratio": ratio, "threshold": threshold},
    )


def _volume_spike_insufficient(reason="volume_ratio is not present on this MarketState"):
    return FactInsufficientData(fact_name="volume_spike", definition_version="1.0", reason=reason)


def _rule_engine_output(vwap_relationship, volume_spike, occurred_at="2026-07-18T13:35:00"):
    return RuleEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at,
        facts={"vwap_relationship": vwap_relationship, "volume_spike": volume_spike},
    )


def _context(vwap_relationship, volume_spike):
    return SetupEvaluationContext(history=[_rule_engine_output(vwap_relationship, volume_spike)])


def _evaluate(context):
    return evaluate_vwap_extension_with_volume_confirmation(
        context, DEFAULT_VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_DEFINITION,
    )


# --- 1-6: detection truth table ----------------------------------------------


class TestDetectionTruthTable:
    def test_extended_above_with_volume_spike_is_detected(self):
        outcome = _evaluate(_context(_vwap_relationship(value="extended_above"), _volume_spike(value=True)))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is True
        assert outcome.severity == Severity.NORMAL

    def test_extended_below_with_volume_spike_is_detected(self):
        outcome = _evaluate(_context(_vwap_relationship(value="extended_below"), _volume_spike(value=True)))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is True
        assert outcome.severity == Severity.NORMAL

    def test_within_band_with_volume_spike_is_not_detected(self):
        outcome = _evaluate(_context(_vwap_relationship(value="within_band"), _volume_spike(value=True)))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is False
        assert outcome.severity is None

    def test_extended_above_without_volume_spike_is_not_detected(self):
        outcome = _evaluate(_context(_vwap_relationship(value="extended_above"), _volume_spike(value=False)))
        assert outcome.detected is False
        assert outcome.severity is None

    def test_extended_below_without_volume_spike_is_not_detected(self):
        outcome = _evaluate(_context(_vwap_relationship(value="extended_below"), _volume_spike(value=False)))
        assert outcome.detected is False
        assert outcome.severity is None

    def test_within_band_without_volume_spike_is_not_detected(self):
        outcome = _evaluate(_context(_vwap_relationship(value="within_band"), _volume_spike(value=False)))
        assert outcome.detected is False
        assert outcome.severity is None


# --- 7-9: insufficient data ---------------------------------------------------


class TestInsufficientData:
    def test_insufficient_vwap_relationship_propagates_its_reason(self):
        outcome = _evaluate(_context(_vwap_relationship_insufficient(), _volume_spike(value=True)))
        assert isinstance(outcome, InsufficientData)
        assert "vwap_relationship is insufficient_data" in outcome.reason
        assert "atr is zero" in outcome.reason

    def test_insufficient_volume_spike_propagates_its_reason(self):
        outcome = _evaluate(_context(_vwap_relationship(), _volume_spike_insufficient()))
        assert isinstance(outcome, InsufficientData)
        assert "volume_spike is insufficient_data" in outcome.reason
        assert "volume_ratio is not present" in outcome.reason

    def test_both_insufficient_uses_deterministic_vwap_relationship_first_ordering(self):
        outcome = _evaluate(_context(
            _vwap_relationship_insufficient(reason="vwap reason"),
            _volume_spike_insufficient(reason="volume reason"),
        ))
        assert isinstance(outcome, InsufficientData)
        assert outcome.reason == "vwap_relationship is insufficient_data: vwap reason"
        assert "volume reason" not in outcome.reason

    def test_insufficient_data_is_never_reported_as_detected_false(self):
        # InsufficientData is a distinct type from SetupResult(detected=False)
        # - a caller must not be able to mistake "could not evaluate" for
        # "evaluated and did not fire".
        outcome = _evaluate(_context(_vwap_relationship_insufficient(), _volume_spike(value=True)))
        assert not isinstance(outcome, SetupResult)


# --- 10: exact evidence shape -------------------------------------------------


class TestEvidence:
    def test_exact_evidence_shape_when_detected(self):
        outcome = _evaluate(_context(_vwap_relationship(value="extended_above"), _volume_spike(value=True, ratio=2.5, threshold=1.5)))
        vwap_fact, volume_fact = outcome.evidence.supporting_facts

        assert vwap_fact.fact_name == "vwap_relationship"
        assert vwap_fact.value == "extended_above"
        assert dict(vwap_fact.detail) == {
            "vwap_relationship_value": "extended_above",
            "is_vwap_extended": True,
            "extension_side": "extended_above",
        }

        assert volume_fact.fact_name == "volume_spike"
        assert volume_fact.value is True
        assert dict(volume_fact.detail) == {"volume_spike_value": True}

    def test_extension_side_absent_when_within_band(self):
        outcome = _evaluate(_context(_vwap_relationship(value="within_band"), _volume_spike(value=True)))
        vwap_fact, _ = outcome.evidence.supporting_facts
        assert dict(vwap_fact.detail) == {"vwap_relationship_value": "within_band", "is_vwap_extended": False}
        assert "extension_side" not in vwap_fact.detail

    def test_extension_side_matches_extended_below(self):
        outcome = _evaluate(_context(_vwap_relationship(value="extended_below"), _volume_spike(value=True)))
        vwap_fact, _ = outcome.evidence.supporting_facts
        assert dict(vwap_fact.detail)["extension_side"] == "extended_below"

    def test_both_supporting_facts_always_present_regardless_of_outcome(self):
        outcome = _evaluate(_context(_vwap_relationship(value="within_band"), _volume_spike(value=False)))
        names = [f.fact_name for f in outcome.evidence.supporting_facts]
        assert names == ["vwap_relationship", "volume_spike"]

    def test_no_rule_engine_evidence_fields_leak_into_setup_evidence(self):
        # Setup Engine must not re-derive or copy ATR/VWAP distance/volume
        # ratio - only the fact value contract.
        outcome = _evaluate(_context(_vwap_relationship(value="extended_above"), _volume_spike(value=True)))
        vwap_fact, volume_fact = outcome.evidence.supporting_facts
        assert "distance_from_vwap_points" not in vwap_fact.detail
        assert "atr" not in vwap_fact.detail
        assert "normalized_distance" not in vwap_fact.detail
        assert "volume_ratio" not in volume_fact.detail

    def test_evidence_occurred_at_matches_context_current(self):
        context = _context(_vwap_relationship(), _volume_spike())
        outcome = _evaluate(context)
        for fact in outcome.evidence.supporting_facts:
            assert fact.occurred_at == context.current.occurred_at


# --- 11: determinism -----------------------------------------------------------


class TestDeterminism:
    def test_same_context_same_output(self):
        context = _context(_vwap_relationship(value="extended_above"), _volume_spike(value=True))
        assert _evaluate(context) == _evaluate(context)

    def test_deterministic_across_repeated_evaluation(self):
        context = _context(_vwap_relationship(value="extended_below"), _volume_spike(value=True))
        results = [_evaluate(context) for _ in range(3)]
        assert results[0] == results[1] == results[2]


# --- 12: SetupDefinition metadata ----------------------------------------------


class TestSetupDefinitionMetadata:
    def test_name(self):
        assert DEFAULT_VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_DEFINITION.name == "vwap_extension_with_volume_confirmation"

    def test_family_is_confluence(self):
        assert DEFAULT_VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_DEFINITION.family == SetupFamily.CONFLUENCE

    def test_required_facts_are_vwap_relationship_and_volume_spike(self):
        assert VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION.required_facts == ("vwap_relationship", "volume_spike")

    def test_required_history_is_one(self):
        assert VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION.required_history == 1

    def test_no_params_needed(self):
        assert dict(DEFAULT_VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_DEFINITION.params) == {}


# --- 13-15: registry inclusion, order, and required_history -------------------


class TestRegistryIntegration:
    def test_registered_in_the_real_registry(self):
        assert VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION in REGISTRY

    def test_registry_holds_all_four_setups_in_deterministic_order(self):
        assert [r.name for r in REGISTRY] == [
            "displacement_with_volume_confirmation",
            "liquidity_sweep_with_volume_confirmation",
            "sustained_displacement_streak",
            "vwap_extension_with_volume_confirmation",
        ]

    def test_appended_last_not_inserted(self):
        assert REGISTRY[-1] is VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION

    def test_real_registry_passes_validation(self):
        validate_registry(REGISTRY)  # must not raise

    def test_required_history_remains_two(self):
        # sustained_displacement_streak (2) remains the registry-wide
        # maximum - this setup only needs 1 and must not raise it.
        assert required_history(REGISTRY) == 2


# --- 16: serialization / output orchestration ----------------------------------


class TestSerialization:
    def test_detected_outcome_is_json_dumps_safe(self):
        context = _context(_vwap_relationship(value="extended_above"), _volume_spike(value=True))
        output = build_setup_engine_output(context, registry=(VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION,))
        as_dict = setup_engine_output_to_dict(output)
        json.dumps(as_dict)  # must not raise
        entry = as_dict["setups"][0]
        assert entry["name"] == "vwap_extension_with_volume_confirmation"
        assert entry["status"] == "computed"
        assert entry["detected"] is True
        assert entry["severity"] == "normal"

    def test_insufficient_data_serializes_cleanly(self):
        context = _context(_vwap_relationship_insufficient(), _volume_spike(value=True))
        output = build_setup_engine_output(context, registry=(VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION,))
        as_dict = setup_engine_output_to_dict(output)
        entry = as_dict["setups"][0]
        assert entry["status"] == "insufficient_data"
        assert "vwap_relationship is insufficient_data" in entry["reason"]

    def test_not_detected_severity_serializes_as_null(self):
        context = _context(_vwap_relationship(value="within_band"), _volume_spike(value=True))
        output = build_setup_engine_output(context, registry=(VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION_REGISTRATION,))
        entry = setup_engine_output_to_dict(output)["setups"][0]
        assert entry["detected"] is False
        assert entry["severity"] is None


# --- 17: window-boundary / end-to-end behavior ----------------------------------


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


def _market_state_window(count, base_time="2026-07-18T13:00:00", **shared_overrides):
    base = datetime.fromisoformat(base_time)
    fields = dict(
        volume_ratio=2.0, high=Price(20140.00, 0.25), low=Price(20120.00, 0.25), atr=10.0,
        open=Price(20126.00, 0.25), close=Price(20125.00, 0.25), distance_from_vwap_points=15.0,
    )
    fields.update(shared_overrides)
    return [
        _state(event_id=f"e{i}", occurred_at=(base + timedelta(minutes=5 * i)).isoformat(), **fields)
        for i in range(count)
    ]


class TestEndToEndWindowOrchestration:
    def test_end_to_end_using_the_real_registry(self):
        # distance_from_vwap_points=15.0, atr=10.0 -> normalized=1.5 > 1.0 ->
        # extended_above; volume_ratio=2.0 > 1.5 -> volume_spike=True.
        window = _market_state_window(3)
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)

        by_name = {s.setup_name: s for s in output.setups}
        result = by_name["vwap_extension_with_volume_confirmation"]
        assert isinstance(result, SetupResult)
        assert result.detected is True
        assert result.severity == Severity.NORMAL
        assert [f.fact_name for f in result.evidence.supporting_facts] == ["vwap_relationship", "volume_spike"]

    def test_early_bar_with_only_one_bar_of_history_still_resolves(self):
        # required_history=1 - a single-bar window must be sufficient, same
        # as every other single-bar setup.
        window = _market_state_window(1)
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)
        by_name = {s.setup_name: s for s in output.setups}
        assert isinstance(by_name["vwap_extension_with_volume_confirmation"], SetupResult)

    def test_no_vwap_distance_on_the_window_produces_insufficient_data(self):
        window = _market_state_window(3, distance_from_vwap_points=None)
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)
        by_name = {s.setup_name: s for s in output.setups}
        assert isinstance(by_name["vwap_extension_with_volume_confirmation"], InsufficientData)


# --- 18: existing setup regression coverage -------------------------------------


class TestExistingSetupRegression:
    def test_all_four_setups_coexist_independently(self):
        window = _market_state_window(3, low=Price(20115.00, 0.25), previous_day_low=Price(20120.00, 0.25))
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)

        assert len(output.setups) == 4
        by_name = {s.setup_name: s for s in output.setups}

        # displacement_with_volume_confirmation: unaffected by this Sprint
        assert isinstance(by_name["displacement_with_volume_confirmation"], SetupResult)
        assert by_name["displacement_with_volume_confirmation"].detected is True

        # liquidity_sweep_with_volume_confirmation: unaffected by this Sprint
        assert isinstance(by_name["liquidity_sweep_with_volume_confirmation"], SetupResult)
        assert by_name["liquidity_sweep_with_volume_confirmation"].detected is True

        # sustained_displacement_streak: unaffected by this Sprint
        assert isinstance(by_name["sustained_displacement_streak"], SetupResult)
        assert by_name["sustained_displacement_streak"].detected is True

        # the new setup, coexisting with the other three
        assert isinstance(by_name["vwap_extension_with_volume_confirmation"], SetupResult)
        assert by_name["vwap_extension_with_volume_confirmation"].detected is True

    def test_evidence_isolated_from_the_other_three_setups(self):
        window = _market_state_window(3, low=Price(20115.00, 0.25), previous_day_low=Price(20120.00, 0.25))
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)
        by_name = {s.setup_name: s for s in output.setups}

        vwap_setup_facts = {f.fact_name for f in by_name["vwap_extension_with_volume_confirmation"].evidence.supporting_facts}
        displacement_setup_facts = {f.fact_name for f in by_name["displacement_with_volume_confirmation"].evidence.supporting_facts}
        assert vwap_setup_facts == {"vwap_relationship", "volume_spike"}
        assert displacement_setup_facts == {"displacement", "volume_spike"}
