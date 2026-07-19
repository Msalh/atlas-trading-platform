from atlas.rule_engine.models import FactResult
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import InsufficientData, SetupEvaluationContext, SetupResult, Severity
from atlas.setup_engine.registry import REGISTRY, required_history, validate_registry
from atlas.setup_engine.setups.displacement_with_volume_confirmation import (
    DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION,
    DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION,
    evaluate_displacement_with_volume_confirmation,
)


def _rule_engine_output(displacement, volume_spike, occurred_at="2026-07-18T13:35:00"):
    return RuleEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at,
        facts={"displacement": displacement, "volume_spike": volume_spike},
    )


def _displacement(value=True, ratio=2.0, threshold=1.5):
    return FactResult(
        fact_name="displacement", definition_version="1.0", value=value,
        evidence={"range_atr_ratio": ratio, "threshold": threshold},
    )


def _volume_spike(value=True, ratio=2.0, threshold=1.5):
    return FactResult(
        fact_name="volume_spike", definition_version="1.0", value=value,
        evidence={"volume_ratio": ratio, "threshold": threshold},
    )


def _context(displacement, volume_spike):
    return SetupEvaluationContext(history=[_rule_engine_output(displacement, volume_spike)])


class TestRegistration:
    def test_registered_in_the_real_registry(self):
        assert DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION in REGISTRY

    def test_definition_family_is_momentum(self):
        from atlas.setup_engine.models import SetupFamily
        assert DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION.family == SetupFamily.MOMENTUM

    def test_required_facts_are_displacement_and_volume_spike(self):
        assert DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION.required_facts == ("displacement", "volume_spike")

    def test_required_history_is_one(self):
        assert DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION.required_history == 1

    def test_real_registry_passes_validation(self):
        validate_registry(REGISTRY)  # must not raise

    def test_real_registry_required_history_reflects_the_registry_wide_maximum(self):
        # This setup's own required_history is 1 (see test_required_history_is_one
        # above); the registry-wide aggregate is 2 because
        # sustained_displacement_streak (Sprint 21) needs 2 - not this setup.
        assert required_history(REGISTRY) == 2


class TestInsufficientDataPropagation:
    def test_displacement_insufficient_propagates_its_reason(self):
        insufficient = FactInsufficientData(fact_name="displacement", definition_version="1.0", reason="atr is zero")
        context = _context(insufficient, _volume_spike())
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert isinstance(outcome, InsufficientData)
        assert "displacement is insufficient_data" in outcome.reason
        assert "atr is zero" in outcome.reason

    def test_volume_spike_insufficient_propagates_its_reason(self):
        insufficient = FactInsufficientData(fact_name="volume_spike", definition_version="1.0", reason="volume_ratio is not present")
        context = _context(_displacement(), insufficient)
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert isinstance(outcome, InsufficientData)
        assert "volume_spike is insufficient_data" in outcome.reason
        assert "volume_ratio is not present" in outcome.reason

    def test_displacement_insufficient_is_checked_before_volume_spike(self):
        # both insufficient - displacement's reason wins
        d_insufficient = FactInsufficientData(fact_name="displacement", definition_version="1.0", reason="atr is zero")
        v_insufficient = FactInsufficientData(fact_name="volume_spike", definition_version="1.0", reason="volume_ratio is not present")
        context = _context(d_insufficient, v_insufficient)
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert isinstance(outcome, InsufficientData)
        assert "displacement is insufficient_data" in outcome.reason


class TestIndependentBlocking:
    def test_displacement_false_blocks_detection_even_if_volume_spike_true(self):
        context = _context(_displacement(value=False), _volume_spike(value=True))
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is False
        assert outcome.severity is None

    def test_volume_spike_false_blocks_detection_even_if_displacement_true(self):
        context = _context(_displacement(value=True), _volume_spike(value=False))
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is False
        assert outcome.severity is None

    def test_both_false(self):
        context = _context(_displacement(value=False), _volume_spike(value=False))
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert outcome.detected is False
        assert outcome.severity is None


class TestPositiveDetection:
    def test_both_true_detects_with_fixed_normal_severity(self):
        context = _context(_displacement(value=True), _volume_spike(value=True))
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is True
        assert outcome.severity == Severity.NORMAL

    def test_severity_is_never_weak_or_strong(self):
        # No tiering was introduced - every detected result is exactly NORMAL,
        # regardless of how large the underlying ratios are.
        context = _context(_displacement(value=True, ratio=99.0), _volume_spike(value=True, ratio=99.0))
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert outcome.severity == Severity.NORMAL


class TestEvidence:
    def test_both_supporting_facts_always_present(self):
        context = _context(_displacement(value=False), _volume_spike(value=False))
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        names = [f.fact_name for f in outcome.evidence.supporting_facts]
        assert names == ["displacement", "volume_spike"]

    def test_evidence_detail_matches_the_underlying_fact_evidence(self):
        context = _context(_displacement(value=True, ratio=3.5, threshold=1.5), _volume_spike(value=True, ratio=4.2, threshold=1.5))
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        displacement_fact, volume_spike_fact = outcome.evidence.supporting_facts
        assert dict(displacement_fact.detail) == {"range_atr_ratio": 3.5, "threshold": 1.5}
        assert dict(volume_spike_fact.detail) == {"volume_ratio": 4.2, "threshold": 1.5}
        assert displacement_fact.value is True
        assert volume_spike_fact.value is True

    def test_evidence_occurred_at_matches_context_current(self):
        context = _context(_displacement(), _volume_spike(), )
        outcome = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        for fact in outcome.evidence.supporting_facts:
            assert fact.occurred_at == context.current.occurred_at


class TestDeterminism:
    def test_same_context_same_output(self):
        context = _context(_displacement(value=True), _volume_spike(value=True))
        first = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        second = evaluate_displacement_with_volume_confirmation(context, DEFAULT_DISPLACEMENT_WITH_VOLUME_CONFIRMATION_DEFINITION)
        assert first == second
