import json
from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.models import FactResult
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.evidence import supporting_fact_from_rule_engine_output
from atlas.setup_engine.models import (
    InsufficientData,
    SetupDefinition,
    SetupEngineOutput,
    SetupEvaluationContext,
    SetupEvidence,
    SetupFamily,
    SetupResult,
    Severity,
    SupportingFact,
)
from atlas.setup_engine.registry import REGISTRY, SetupRegistration
from atlas.setup_engine.registry import required_history as setup_required_history
from atlas.setup_engine.service import (
    build_setup_engine_output,
    build_setup_engine_output_window,
    evaluate_registration,
    setup_engine_output_to_dict,
)


def _rule_engine_output(occurred_at="2026-07-18T13:35:00", symbol="MNQU6", timeframe="5m", facts=None):
    return RuleEngineOutput(
        schema_version="1.0", symbol=symbol, timeframe=timeframe, occurred_at=occurred_at,
        facts=facts if facts is not None else {},
    )


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
    fields = dict(volume_ratio=2.0, high=Price(20140.00, 0.25), low=Price(20120.00, 0.25), atr=10.0,
                  open=Price(20126.00, 0.25), close=Price(20125.00, 0.25))
    fields.update(shared_overrides)
    return [
        _state(event_id=f"e{i}", occurred_at=(base + timedelta(minutes=5 * i)).isoformat(), **fields)
        for i in range(count)
    ]


class TestSetupEvaluationContext:
    def test_rejects_empty_history(self):
        with pytest.raises(ValueError, match="must not be empty"):
            SetupEvaluationContext(history=[])

    def test_current_is_the_last_history_entry(self):
        older = _rule_engine_output(occurred_at="2026-07-18T13:00:00")
        newest = _rule_engine_output(occurred_at="2026-07-18T13:05:00")
        context = SetupEvaluationContext(history=[older, newest])
        assert context.current is newest

    def test_current_cannot_drift_from_history(self):
        # current is a derived property, not a second stored field - there is
        # no way to construct a context where current disagrees with
        # history[-1].
        only = _rule_engine_output()
        context = SetupEvaluationContext(history=[only])
        assert context.current is context.history[-1]


class TestSupportingFactAndSetupDefinition:
    def test_supporting_fact_detail_is_immutable(self):
        source = {"threshold": 1.5}
        fact = SupportingFact(fact_name="volume_spike", occurred_at="2026-07-18T13:35:00", value=True, detail=source)
        source["threshold"] = 999.0
        assert fact.detail["threshold"] == 1.5
        with pytest.raises(TypeError):
            fact.detail["threshold"] = 2.0

    def test_setup_definition_params_is_immutable(self):
        source = {"lookback": 10}
        definition = SetupDefinition(name="x", version="1.0", family=SetupFamily.ICT, params=source)
        source["lookback"] = 999
        assert definition.params["lookback"] == 10
        with pytest.raises(TypeError):
            definition.params["lookback"] = 2


class TestSetupFamily:
    def test_closed_membership_is_exactly_the_documented_set(self):
        # A deliberate, loud-failure taxonomy test: this must be updated by
        # hand whenever SetupFamily is extended (Sprint 18's MOMENTUM,
        # Sprint 23A's CONFLUENCE) - the same "closed enum, deliberate
        # extension" discipline atlas.core.primitives.Timeframe established,
        # made concrete as a test rather than only a docstring claim.
        assert {f.value for f in SetupFamily} == {
            "ict", "wyckoff", "order_flow", "auction_market_theory", "momentum", "confluence",
        }

    def test_confluence_value_is_json_safe(self):
        assert SetupFamily.CONFLUENCE.value == "confluence"
        json.dumps(SetupFamily.CONFLUENCE.value)  # must not raise

    def test_confluence_is_a_str_subclass_like_every_member(self):
        # SetupFamily(str, Enum) - equality with the raw string must hold for
        # every member, not just the pre-Sprint-23A ones, since this is what
        # lets a family value round-trip through JSON without special-casing.
        assert SetupFamily.CONFLUENCE == "confluence"

    def test_confluence_constructs_a_setup_definition_cleanly(self):
        definition = SetupDefinition(name="x", version="1.0", family=SetupFamily.CONFLUENCE, params={})
        assert definition.family == SetupFamily.CONFLUENCE


class TestSetupResultSeverityInvariant:
    def test_detected_true_with_severity_is_allowed(self):
        SetupResult(
            setup_name="x", definition_version="1.0", detected=True, severity=Severity.STRONG,
            evidence=SetupEvidence(supporting_facts=()),
        )  # must not raise

    def test_detected_true_with_no_severity_is_allowed(self):
        SetupResult(
            setup_name="x", definition_version="1.0", detected=True, severity=None,
            evidence=SetupEvidence(supporting_facts=()),
        )  # must not raise

    def test_detected_false_with_no_severity_is_allowed(self):
        SetupResult(
            setup_name="x", definition_version="1.0", detected=False, severity=None,
            evidence=SetupEvidence(supporting_facts=()),
        )  # must not raise

    def test_detected_false_with_severity_is_structurally_impossible(self):
        with pytest.raises(ValueError, match="severity must be None"):
            SetupResult(
                setup_name="x", definition_version="1.0", detected=False, severity=Severity.WEAK,
                evidence=SetupEvidence(supporting_facts=()),
            )


class TestSupportingFactFromRuleEngineOutput:
    def test_copies_fields_from_a_computed_fact(self):
        output = _rule_engine_output(
            occurred_at="2026-07-18T13:35:00",
            facts={"volume_spike": FactResult(fact_name="volume_spike", definition_version="1.0", value=True, evidence={"ratio": 2.0})},
        )
        fact = supporting_fact_from_rule_engine_output(output, "volume_spike", detail={"ratio": 2.0})
        assert fact.fact_name == "volume_spike"
        assert fact.occurred_at == "2026-07-18T13:35:00"
        assert fact.value is True
        assert fact.detail == {"ratio": 2.0}

    def test_defaults_to_empty_detail(self):
        output = _rule_engine_output(
            facts={"volume_spike": FactResult(fact_name="volume_spike", definition_version="1.0", value=True, evidence={})},
        )
        fact = supporting_fact_from_rule_engine_output(output, "volume_spike")
        assert dict(fact.detail) == {}

    def test_raises_on_missing_fact_name(self):
        output = _rule_engine_output(facts={})
        with pytest.raises(ValueError, match="not present"):
            supporting_fact_from_rule_engine_output(output, "volume_spike")

    def test_raises_on_insufficient_data_fact(self):
        output = _rule_engine_output(
            facts={"volume_spike": FactInsufficientData(fact_name="volume_spike", definition_version="1.0", reason="missing data")},
        )
        with pytest.raises(ValueError, match="insufficient_data"):
            supporting_fact_from_rule_engine_output(output, "volume_spike")


def _detecting_evaluator(context, definition):
    fact = supporting_fact_from_rule_engine_output(context.current, "volume_spike", detail={"source": "test"})
    return SetupResult(
        setup_name=definition.name, definition_version=definition.version, detected=True,
        severity=Severity.STRONG, evidence=SetupEvidence(supporting_facts=(fact,)),
    )


def _insufficient_evaluator(context, definition):
    return InsufficientData(setup_name=definition.name, definition_version=definition.version, reason="not enough history")


class TestBuildSetupEngineOutput:
    def _definition(self, name="probe"):
        return SetupDefinition(name=name, version="1.0", family=SetupFamily.ICT, params={})

    def test_empty_registry_produces_no_setups(self):
        context = SetupEvaluationContext(history=[_rule_engine_output()])
        output = build_setup_engine_output(context, registry=())
        assert output.setups == ()

    def test_symbol_timeframe_occurred_at_copied_from_current(self):
        context = SetupEvaluationContext(
            history=[_rule_engine_output(symbol="MNQU6", timeframe="5m", occurred_at="2026-07-18T13:35:00")],
        )
        output = build_setup_engine_output(context, registry=())
        assert output.schema_version == "1.0"
        assert output.symbol == "MNQU6"
        assert output.timeframe == "5m"
        assert output.occurred_at == "2026-07-18T13:35:00"

    def test_setups_is_an_ordered_tuple_in_registry_order(self):
        r1 = SetupRegistration("first", _detecting_evaluator, self._definition("first"), required_facts=("volume_spike",))
        r2 = SetupRegistration("second", _insufficient_evaluator, self._definition("second"))
        context = SetupEvaluationContext(
            history=[_rule_engine_output(facts={
                "volume_spike": FactResult(fact_name="volume_spike", definition_version="1.0", value=True, evidence={}),
            })],
        )
        output = build_setup_engine_output(context, registry=(r1, r2))
        assert isinstance(output.setups, tuple)
        assert [o.setup_name for o in output.setups] == ["first", "second"]
        assert isinstance(output.setups[0], SetupResult)
        assert isinstance(output.setups[1], InsufficientData)

    def test_evaluate_registration_matches_registration_evaluate(self):
        r = SetupRegistration("probe", _insufficient_evaluator, self._definition("probe"))
        context = SetupEvaluationContext(history=[_rule_engine_output()])
        assert evaluate_registration(context, r) == r.evaluate(context, r.definition)

    def test_deterministic_same_input_same_output(self):
        r = SetupRegistration("first", _detecting_evaluator, self._definition("first"), required_facts=("volume_spike",))
        context = SetupEvaluationContext(
            history=[_rule_engine_output(facts={
                "volume_spike": FactResult(fact_name="volume_spike", definition_version="1.0", value=True, evidence={}),
            })],
        )
        assert build_setup_engine_output(context, registry=(r,)) == build_setup_engine_output(context, registry=(r,))


class TestSetupEngineOutputToDict:
    def test_computed_setup_serializes_with_detected_severity_and_evidence(self):
        fact = SupportingFact(fact_name="volume_spike", occurred_at="2026-07-18T13:35:00", value=True, detail={"ratio": 2.0})
        output = SetupEngineOutput(
            schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at="2026-07-18T13:35:00",
            setups=(
                SetupResult(
                    setup_name="probe", definition_version="1.0", detected=True, severity=Severity.STRONG,
                    evidence=SetupEvidence(supporting_facts=(fact,)),
                ),
            ),
        )
        as_dict = setup_engine_output_to_dict(output)
        assert as_dict["setups"] == [{
            "name": "probe", "status": "computed", "detected": True, "severity": "strong",
            "definition_version": "1.0",
            "evidence": {"supporting_facts": [
                {"fact_name": "volume_spike", "occurred_at": "2026-07-18T13:35:00", "value": True, "detail": {"ratio": 2.0}},
            ]},
        }]

    def test_insufficient_data_setup_serializes_with_reason(self):
        output = SetupEngineOutput(
            schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at="2026-07-18T13:35:00",
            setups=(InsufficientData(setup_name="probe", definition_version="1.0", reason="not enough history"),),
        )
        as_dict = setup_engine_output_to_dict(output)
        assert as_dict["setups"] == [{
            "name": "probe", "status": "insufficient_data", "definition_version": "1.0", "reason": "not enough history",
        }]

    def test_setups_is_a_list_not_an_object(self):
        output = SetupEngineOutput(
            schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at="2026-07-18T13:35:00",
            setups=(InsufficientData(setup_name="probe", definition_version="1.0", reason="x"),),
        )
        assert isinstance(setup_engine_output_to_dict(output)["setups"], list)

    def test_severity_none_serializes_as_json_null(self):
        output = SetupEngineOutput(
            schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at="2026-07-18T13:35:00",
            setups=(
                SetupResult(
                    setup_name="probe", definition_version="1.0", detected=False, severity=None,
                    evidence=SetupEvidence(supporting_facts=()),
                ),
            ),
        )
        as_dict = setup_engine_output_to_dict(output)
        assert as_dict["setups"][0]["severity"] is None

    def test_complete_output_is_json_dumps_safe(self):
        fact = SupportingFact(fact_name="volume_spike", occurred_at="2026-07-18T13:35:00", value=True, detail={"ratio": 2.0})
        output = SetupEngineOutput(
            schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at="2026-07-18T13:35:00",
            setups=(
                SetupResult(
                    setup_name="probe", definition_version="1.0", detected=True, severity=Severity.STRONG,
                    evidence=SetupEvidence(supporting_facts=(fact,)),
                ),
                InsufficientData(setup_name="other", definition_version="1.0", reason="not enough history"),
            ),
        )
        json.dumps(setup_engine_output_to_dict(output))  # must not raise


class TestConstructionFromRuleEngineWindow:
    def test_setup_evaluation_context_builds_directly_from_build_rule_engine_output_window(self):
        window = _market_state_window(3)
        history = build_rule_engine_output_window(window)
        context = SetupEvaluationContext(history=history)
        assert context.history == history
        assert context.current == history[-1]

    def test_end_to_end_from_market_state_to_setup_engine_output(self):
        window = _market_state_window(3)
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        r = SetupRegistration("first", _detecting_evaluator, TestBuildSetupEngineOutput()._definition("first"), required_facts=("volume_spike",))
        output = build_setup_engine_output(context, registry=(r,))
        assert output.symbol == "MNQU6"
        assert output.timeframe == "5m"
        assert output.occurred_at == window[-1].envelope.occurred_at.isoformat()
        assert output.setups[0].setup_name == "first"
        assert isinstance(output.setups[0], SetupResult)
        assert output.setups[0].detected is True

    def test_end_to_end_using_the_real_registry(self):
        # Sprint 18/20/21/23B: proves all four actually-registered setups,
        # not local stand-ins, run correctly through the full pipeline, in
        # registry order. _market_state_window's defaults already produce
        # displacement=True ((high-low)/atr = 20/10 = 2.0 > 1.5) and
        # volume_spike=True (volume_ratio = 2.0 > 1.5) on every bar, but set
        # no reference levels - liquidity_sweep_with_volume_confirmation is
        # therefore correctly InsufficientData here (no reference levels
        # present) - and no distance_from_vwap_points, so
        # vwap_extension_with_volume_confirmation is correctly
        # InsufficientData too (no VWAP distance present). displacement=True
        # on all 3 bars also means sustained_displacement_streak genuinely
        # detects a real 3-bar streak here, not a stand-in.
        window = _market_state_window(3)
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)
        assert [s.setup_name for s in output.setups] == [
            "displacement_with_volume_confirmation",
            "liquidity_sweep_with_volume_confirmation",
            "sustained_displacement_streak",
            "vwap_extension_with_volume_confirmation",
        ]
        displacement_result, liquidity_sweep_result, streak_result, vwap_result = output.setups
        assert isinstance(displacement_result, SetupResult)
        assert displacement_result.detected is True
        assert displacement_result.severity == Severity.NORMAL
        assert [f.fact_name for f in displacement_result.evidence.supporting_facts] == ["displacement", "volume_spike"]
        assert isinstance(liquidity_sweep_result, InsufficientData)
        assert isinstance(streak_result, SetupResult)
        assert streak_result.detected is True
        assert len(streak_result.evidence.supporting_facts) == 3
        assert isinstance(vwap_result, InsufficientData)

    def test_end_to_end_liquidity_sweep_with_volume_confirmation_using_the_real_registry(self):
        # A window engineered so liquidity_sweep genuinely fires: low dips
        # below previous_day_low on every bar, close finishes back above it.
        window = _market_state_window(
            3, low=Price(20115.00, 0.25), previous_day_low=Price(20120.00, 0.25),
        )
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)
        by_name = {s.setup_name: s for s in output.setups}
        result = by_name["liquidity_sweep_with_volume_confirmation"]
        assert isinstance(result, SetupResult)
        assert result.detected is True
        assert result.severity == Severity.NORMAL
        ls_fact, vs_fact = result.evidence.supporting_facts
        assert ls_fact.fact_name == "liquidity_sweep"
        assert dict(ls_fact.detail) == {"qualifying_level_count": 1, "qualifying_levels": "previous_day_low"}
        assert vs_fact.fact_name == "volume_spike"


class TestBuildSetupEngineOutputWindow:
    """Sprint 24C. build_setup_engine_output_window is the direct,
    one-layer-up generalization of build_rule_engine_output_window - these
    tests mirror TestBuildRuleEngineOutputWindow's own structure in
    test_rule_engine.py exactly, over SetupEngineOutput instead of
    RuleEngineOutput."""

    def test_empty_input_produces_empty_output(self):
        assert build_setup_engine_output_window([]) == []

    def test_one_rule_engine_output_produces_one_setup_engine_output(self):
        window = _market_state_window(1)
        rule_history = build_rule_engine_output_window(window)
        outputs = build_setup_engine_output_window(rule_history, registry=REGISTRY)
        assert len(outputs) == 1
        assert outputs[0] == build_setup_engine_output(SetupEvaluationContext(history=rule_history), REGISTRY)

    def test_exactly_required_history_outputs_shows_natural_warm_up(self):
        # required_history(REGISTRY) == 2, driven by sustained_displacement_streak.
        # Position 0 has only itself as history (1 < 2) - that setup must be
        # InsufficientData there. Position 1 has both entries (2 == 2) - the
        # same 2-bar streak displacement_with_volume_confirmation and
        # sustained_displacement_streak both need is genuinely available.
        assert setup_required_history(REGISTRY) == 2
        window = _market_state_window(2)
        rule_history = build_rule_engine_output_window(window)
        outputs = build_setup_engine_output_window(rule_history, registry=REGISTRY)
        assert len(outputs) == 2

        first_by_name = {s.setup_name: s for s in outputs[0].setups}
        assert isinstance(first_by_name["sustained_displacement_streak"], InsufficientData)

        second_by_name = {s.setup_name: s for s in outputs[1].setups}
        streak_result = second_by_name["sustained_displacement_streak"]
        assert isinstance(streak_result, SetupResult)
        assert streak_result.detected is True
        assert len(streak_result.evidence.supporting_facts) == 2

    def test_required_history_plus_one_preserves_chronological_order_and_registry_order(self):
        window = _market_state_window(3)
        rule_history = build_rule_engine_output_window(window)
        outputs = build_setup_engine_output_window(rule_history, registry=REGISTRY)
        assert len(outputs) == 3
        assert [o.occurred_at for o in outputs] == [ro.occurred_at for ro in rule_history]
        for output in outputs:
            assert [s.setup_name for s in output.setups] == [
                "displacement_with_volume_confirmation",
                "liquidity_sweep_with_volume_confirmation",
                "sustained_displacement_streak",
                "vwap_extension_with_volume_confirmation",
            ]

    def test_matches_build_setup_engine_output_called_per_position(self):
        window = _market_state_window(3)
        rule_history = build_rule_engine_output_window(window)
        outputs = build_setup_engine_output_window(rule_history, registry=REGISTRY)
        depth = setup_required_history(REGISTRY)
        for i, output in enumerate(outputs):
            context = SetupEvaluationContext(history=rule_history[max(0, i - depth + 1): i + 1])
            assert output == build_setup_engine_output(context, registry=REGISTRY)

    def test_deterministic_same_input_same_output(self):
        window = _market_state_window(3)
        rule_history = build_rule_engine_output_window(window)
        assert build_setup_engine_output_window(rule_history, registry=REGISTRY) == build_setup_engine_output_window(
            rule_history, registry=REGISTRY,
        )

    def test_does_not_mutate_or_reorder_input(self):
        window = _market_state_window(3)
        rule_history = build_rule_engine_output_window(window)
        original = list(rule_history)
        build_setup_engine_output_window(rule_history, registry=REGISTRY)
        assert rule_history == original
