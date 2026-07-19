"""
Sprint 20. Setup Engine independence tests - proving properties the design
has always claimed (Sprint 17B's own docstrings: "no current setup depends
on another's output"; Sprint 15's registry-ordering rule, reused for Setup
Engine's own registry) but which no test had exercised with more than one
real, differently-behaved setup evaluated together until now.

Two levels of proof:
- TestSyntheticIndependence uses three locally-constructed, fully-controlled
  registrations (a detector, a non-detector, an insufficient one) to prove
  order-independence and evidence isolation mechanically, with no dependency
  on real Rule Engine fact behavior.
- TestRealRegistryCoexistence uses the two actually-registered setups
  (displacement_with_volume_confirmation, liquidity_sweep_with_volume_confirmation)
  over one real MarketState window, proving the same properties hold for the
  genuine production registry, not just a synthetic stand-in.
"""
from datetime import datetime, timedelta, timezone
from itertools import permutations

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.models import (
    InsufficientData,
    SetupDefinition,
    SetupEvaluationContext,
    SetupEvidence,
    SetupFamily,
    SetupResult,
    Severity,
    SupportingFact,
)
from atlas.setup_engine.registration import SetupRegistration
from atlas.setup_engine.registry import REGISTRY
from atlas.setup_engine.service import build_setup_engine_output

# --- Synthetic, fully-controlled registrations ------------------------------


def _definition(name):
    return SetupDefinition(name=name, version="1.0", family=SetupFamily.ICT, params={})


def _alpha_evaluate(context, definition):
    return SetupResult(
        setup_name=definition.name, definition_version=definition.version, detected=True,
        severity=Severity.STRONG,
        evidence=SetupEvidence(supporting_facts=(
            SupportingFact(fact_name="synthetic_alpha", occurred_at=context.current.occurred_at, value=True, detail={"marker": "alpha"}),
        )),
    )


def _beta_evaluate(context, definition):
    return SetupResult(
        setup_name=definition.name, definition_version=definition.version, detected=False, severity=None,
        evidence=SetupEvidence(supporting_facts=(
            SupportingFact(fact_name="synthetic_beta", occurred_at=context.current.occurred_at, value=False, detail={"marker": "beta"}),
        )),
    )


def _gamma_evaluate(context, definition):
    return InsufficientData(setup_name=definition.name, definition_version=definition.version, reason="synthetic gamma insufficiency")


ALPHA = SetupRegistration("alpha", _alpha_evaluate, _definition("alpha"))
BETA = SetupRegistration("beta", _beta_evaluate, _definition("beta"))
GAMMA = SetupRegistration("gamma", _gamma_evaluate, _definition("gamma"))


def _rule_engine_output_stub(occurred_at="2026-07-18T13:35:00"):
    return RuleEngineOutput(schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at, facts={})


def _synthetic_context():
    return SetupEvaluationContext(history=[_rule_engine_output_stub()])


class TestSyntheticIndependence:
    def test_each_setup_evaluated_independently_of_the_others(self):
        # A setup's own outcome, evaluated alongside two others, must be
        # identical to its outcome evaluated completely alone.
        context = _synthetic_context()
        combined = build_setup_engine_output(context, registry=(ALPHA, BETA, GAMMA))
        alone_alpha = build_setup_engine_output(context, registry=(ALPHA,))
        alone_beta = build_setup_engine_output(context, registry=(BETA,))
        alone_gamma = build_setup_engine_output(context, registry=(GAMMA,))

        by_name = {s.setup_name: s for s in combined.setups}
        assert by_name["alpha"] == alone_alpha.setups[0]
        assert by_name["beta"] == alone_beta.setups[0]
        assert by_name["gamma"] == alone_gamma.setups[0]

    def test_registry_order_determines_output_order(self):
        context = _synthetic_context()
        for registry in permutations((ALPHA, BETA, GAMMA)):
            output = build_setup_engine_output(context, registry=registry)
            assert [s.setup_name for s in output.setups] == [r.name for r in registry]

    def test_registry_order_has_no_effect_on_each_setups_own_content(self):
        # Every permutation of the same three registrations must produce the
        # exact same per-setup outcomes - only the CONTAINER order changes,
        # never a value inside it.
        context = _synthetic_context()
        results_by_permutation = []
        for registry in permutations((ALPHA, BETA, GAMMA)):
            output = build_setup_engine_output(context, registry=registry)
            results_by_permutation.append({s.setup_name: s for s in output.setups})

        first = results_by_permutation[0]
        for other in results_by_permutation[1:]:
            assert other == first

    def test_multiple_setups_coexist_with_distinct_outcomes_in_one_output(self):
        context = _synthetic_context()
        output = build_setup_engine_output(context, registry=(ALPHA, BETA, GAMMA))
        assert len(output.setups) == 3
        by_name = {s.setup_name: s for s in output.setups}
        assert isinstance(by_name["alpha"], SetupResult) and by_name["alpha"].detected is True
        assert isinstance(by_name["beta"], SetupResult) and by_name["beta"].detected is False
        assert isinstance(by_name["gamma"], InsufficientData)

    def test_evidence_does_not_leak_between_setups(self):
        context = _synthetic_context()
        output = build_setup_engine_output(context, registry=(ALPHA, BETA, GAMMA))
        by_name = {s.setup_name: s for s in output.setups}

        alpha_facts = by_name["alpha"].evidence.supporting_facts
        beta_facts = by_name["beta"].evidence.supporting_facts
        assert [f.fact_name for f in alpha_facts] == ["synthetic_alpha"]
        assert [f.fact_name for f in beta_facts] == ["synthetic_beta"]
        assert dict(alpha_facts[0].detail) == {"marker": "alpha"}
        assert dict(beta_facts[0].detail) == {"marker": "beta"}
        # gamma is InsufficientData - it has no evidence at all, and its
        # presence must not have altered alpha's or beta's own evidence.
        assert not hasattr(by_name["gamma"], "evidence")


# --- Real registry coexistence -----------------------------------------------


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
        open=Price(20126.00, 0.25), close=Price(20125.00, 0.25),
    )
    fields.update(shared_overrides)
    return [
        _state(event_id=f"e{i}", occurred_at=(base + timedelta(minutes=5 * i)).isoformat(), **fields)
        for i in range(count)
    ]


class TestRealRegistryCoexistence:
    def test_all_four_real_setups_present_and_independently_evaluated(self):
        # displacement=True and volume_spike=True on every bar (defaults);
        # no reference levels set, so liquidity_sweep is InsufficientData -
        # a real, asymmetric outcome: one setup detects, another cannot even
        # be evaluated, a third (sustained_displacement_streak, Sprint 21)
        # detects a genuine 3-bar streak, a fourth
        # (vwap_extension_with_volume_confirmation, Sprint 23B) is
        # InsufficientData too (no distance_from_vwap_points set) - and none
        # of their states affect each other.
        window = _market_state_window(3)
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)

        assert len(output.setups) == 4
        by_name = {s.setup_name: s for s in output.setups}
        displacement_result = by_name["displacement_with_volume_confirmation"]
        liquidity_sweep_result = by_name["liquidity_sweep_with_volume_confirmation"]
        streak_result = by_name["sustained_displacement_streak"]
        vwap_result = by_name["vwap_extension_with_volume_confirmation"]

        assert isinstance(displacement_result, SetupResult)
        assert displacement_result.detected is True
        assert isinstance(liquidity_sweep_result, InsufficientData)
        assert isinstance(streak_result, SetupResult)
        assert streak_result.detected is True
        assert len(streak_result.evidence.supporting_facts) == 3
        assert isinstance(vwap_result, InsufficientData)

    def test_multiple_real_setups_can_detect_simultaneously(self):
        # A window where BOTH conditions genuinely hold: displacement/volume
        # via the defaults, plus a real low-side liquidity sweep against
        # previous_day_low.
        window = _market_state_window(3, low=Price(20115.00, 0.25), previous_day_low=Price(20120.00, 0.25))
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)

        by_name = {s.setup_name: s for s in output.setups}
        assert by_name["displacement_with_volume_confirmation"].detected is True
        assert by_name["liquidity_sweep_with_volume_confirmation"].detected is True

    def test_real_registry_order_has_no_effect_on_per_setup_content(self):
        window = _market_state_window(3, low=Price(20115.00, 0.25), previous_day_low=Price(20120.00, 0.25))
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))

        forward = build_setup_engine_output(context, registry=REGISTRY)
        reversed_registry = tuple(reversed(REGISTRY))
        backward = build_setup_engine_output(context, registry=reversed_registry)

        assert [s.setup_name for s in forward.setups] == [r.name for r in REGISTRY]
        assert [s.setup_name for s in backward.setups] == [r.name for r in reversed_registry]

        forward_by_name = {s.setup_name: s for s in forward.setups}
        backward_by_name = {s.setup_name: s for s in backward.setups}
        assert forward_by_name == backward_by_name

    def test_evidence_isolated_between_the_real_setups(self):
        window = _market_state_window(3, low=Price(20115.00, 0.25), previous_day_low=Price(20120.00, 0.25))
        context = SetupEvaluationContext(history=build_rule_engine_output_window(window))
        output = build_setup_engine_output(context, registry=REGISTRY)
        by_name = {s.setup_name: s for s in output.setups}

        displacement_fact_names = {f.fact_name for f in by_name["displacement_with_volume_confirmation"].evidence.supporting_facts}
        liquidity_sweep_fact_names = {f.fact_name for f in by_name["liquidity_sweep_with_volume_confirmation"].evidence.supporting_facts}
        streak_fact_names = {f.fact_name for f in by_name["sustained_displacement_streak"].evidence.supporting_facts}

        assert displacement_fact_names == {"displacement", "volume_spike"}
        assert liquidity_sweep_fact_names == {"liquidity_sweep", "volume_spike"}
        assert streak_fact_names == {"displacement"}
        # Both legitimately reference volume_spike (each setup calls the
        # shared construction helper independently) - but each setup's own
        # SupportingFact instance is its own, not a shared/mutated object.
        displacement_vs_fact = next(f for f in by_name["displacement_with_volume_confirmation"].evidence.supporting_facts if f.fact_name == "volume_spike")
        sweep_vs_fact = next(f for f in by_name["liquidity_sweep_with_volume_confirmation"].evidence.supporting_facts if f.fact_name == "volume_spike")
        assert displacement_vs_fact == sweep_vs_fact  # equal in value
        assert displacement_vs_fact is not sweep_vs_fact  # but independently constructed
