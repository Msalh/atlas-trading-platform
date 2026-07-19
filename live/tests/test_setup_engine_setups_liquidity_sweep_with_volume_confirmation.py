from atlas.rule_engine.models import FactResult
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import InsufficientData, SetupEvaluationContext, SetupFamily, SetupResult, Severity
from atlas.setup_engine.registry import REGISTRY, required_history, validate_registry
from atlas.setup_engine.setups.liquidity_sweep_with_volume_confirmation import (
    DEFAULT_LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_DEFINITION,
    LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_REGISTRATION,
    evaluate_liquidity_sweep_with_volume_confirmation,
)


def _rule_engine_output(liquidity_sweep, volume_spike, occurred_at="2026-07-18T13:35:00"):
    return RuleEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at,
        facts={"liquidity_sweep": liquidity_sweep, "volume_spike": volume_spike},
    )


def _qualifying_level(name="previous_day_low", side="low", level=20120.0, excursion=20115.0, close=20125.0):
    return {
        "reference_level": name, "side": side, "level": level, "excursion": excursion,
        "excursion_occurred_at": "2026-07-18T13:30:00", "close": close,
    }


def _liquidity_sweep(value=True, qualifying_levels=None, window_size=3):
    if qualifying_levels is None:
        qualifying_levels = [_qualifying_level()] if value else []
    return FactResult(
        fact_name="liquidity_sweep", definition_version="1.0", value=value,
        evidence={"window_size": window_size, "qualifying_levels": qualifying_levels},
    )


def _volume_spike(value=True, ratio=2.0, threshold=1.5):
    return FactResult(
        fact_name="volume_spike", definition_version="1.0", value=value,
        evidence={"volume_ratio": ratio, "threshold": threshold},
    )


def _context(liquidity_sweep, volume_spike):
    return SetupEvaluationContext(history=[_rule_engine_output(liquidity_sweep, volume_spike)])


def _evaluate(context):
    return evaluate_liquidity_sweep_with_volume_confirmation(
        context, DEFAULT_LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_DEFINITION,
    )


class TestRegistration:
    def test_registered_in_the_real_registry(self):
        assert LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_REGISTRATION in REGISTRY

    def test_definition_family_is_ict(self):
        assert DEFAULT_LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_DEFINITION.family == SetupFamily.ICT

    def test_required_facts_are_liquidity_sweep_and_volume_spike(self):
        assert LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_REGISTRATION.required_facts == ("liquidity_sweep", "volume_spike")

    def test_required_history_is_one(self):
        assert LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION_REGISTRATION.required_history == 1

    def test_real_registry_passes_validation(self):
        validate_registry(REGISTRY)  # must not raise

    def test_real_registry_required_history_reflects_the_registry_wide_maximum(self):
        # This setup's own required_history is 1 (see test_required_history_is_one
        # above); the registry-wide aggregate is 2 because
        # sustained_displacement_streak (Sprint 21) needs 2 - not this setup.
        assert required_history(REGISTRY) == 2


class TestInsufficientDataPropagation:
    def test_liquidity_sweep_insufficient_propagates_its_reason(self):
        insufficient = FactInsufficientData(
            fact_name="liquidity_sweep", definition_version="1.0",
            reason="fewer than 3 bars available in the window (got 1)",
        )
        outcome = _evaluate(_context(insufficient, _volume_spike()))
        assert isinstance(outcome, InsufficientData)
        assert "liquidity_sweep is insufficient_data" in outcome.reason
        assert "fewer than 3 bars" in outcome.reason

    def test_volume_spike_insufficient_propagates_its_reason(self):
        insufficient = FactInsufficientData(
            fact_name="volume_spike", definition_version="1.0", reason="volume_ratio is not present",
        )
        outcome = _evaluate(_context(_liquidity_sweep(), insufficient))
        assert isinstance(outcome, InsufficientData)
        assert "volume_spike is insufficient_data" in outcome.reason
        assert "volume_ratio is not present" in outcome.reason

    def test_liquidity_sweep_insufficient_is_checked_before_volume_spike(self):
        ls_insufficient = FactInsufficientData(fact_name="liquidity_sweep", definition_version="1.0", reason="ls reason")
        vs_insufficient = FactInsufficientData(fact_name="volume_spike", definition_version="1.0", reason="vs reason")
        outcome = _evaluate(_context(ls_insufficient, vs_insufficient))
        assert isinstance(outcome, InsufficientData)
        assert "liquidity_sweep is insufficient_data" in outcome.reason


class TestIndependentBlocking:
    def test_liquidity_sweep_false_blocks_detection_even_if_volume_spike_true(self):
        outcome = _evaluate(_context(_liquidity_sweep(value=False), _volume_spike(value=True)))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is False
        assert outcome.severity is None

    def test_volume_spike_false_blocks_detection_even_if_liquidity_sweep_true(self):
        outcome = _evaluate(_context(_liquidity_sweep(value=True), _volume_spike(value=False)))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is False
        assert outcome.severity is None

    def test_both_false(self):
        outcome = _evaluate(_context(_liquidity_sweep(value=False), _volume_spike(value=False)))
        assert outcome.detected is False
        assert outcome.severity is None


class TestPositiveDetection:
    def test_both_true_detects_with_fixed_normal_severity(self):
        outcome = _evaluate(_context(_liquidity_sweep(value=True), _volume_spike(value=True)))
        assert isinstance(outcome, SetupResult)
        assert outcome.detected is True
        assert outcome.severity == Severity.NORMAL

    def test_severity_is_never_weak_or_strong(self):
        outcome = _evaluate(_context(
            _liquidity_sweep(value=True, qualifying_levels=[_qualifying_level(), _qualifying_level("overnight_low", excursion=20114.0)]),
            _volume_spike(value=True, ratio=99.0),
        ))
        assert outcome.severity == Severity.NORMAL


class TestEvidence:
    def test_both_supporting_facts_always_present(self):
        outcome = _evaluate(_context(_liquidity_sweep(value=False), _volume_spike(value=False)))
        names = [f.fact_name for f in outcome.evidence.supporting_facts]
        assert names == ["liquidity_sweep", "volume_spike"]

    def test_liquidity_sweep_detail_summarizes_qualifying_levels(self):
        levels = [_qualifying_level("previous_day_low"), _qualifying_level("overnight_low", excursion=20114.0)]
        outcome = _evaluate(_context(_liquidity_sweep(value=True, qualifying_levels=levels), _volume_spike(value=True)))
        ls_fact, vs_fact = outcome.evidence.supporting_facts
        assert dict(ls_fact.detail) == {"qualifying_level_count": 2, "qualifying_levels": "overnight_low,previous_day_low"}
        assert ls_fact.value is True

    def test_qualifying_level_names_are_in_stable_sorted_order_regardless_of_input_order(self):
        # Same two levels, reversed input order - output string must be identical.
        order_a = [_qualifying_level("previous_day_low"), _qualifying_level("overnight_low", excursion=20114.0)]
        order_b = [_qualifying_level("overnight_low", excursion=20114.0), _qualifying_level("previous_day_low")]
        outcome_a = _evaluate(_context(_liquidity_sweep(value=True, qualifying_levels=order_a), _volume_spike(value=True)))
        outcome_b = _evaluate(_context(_liquidity_sweep(value=True, qualifying_levels=order_b), _volume_spike(value=True)))
        detail_a = dict(outcome_a.evidence.supporting_facts[0].detail)
        detail_b = dict(outcome_b.evidence.supporting_facts[0].detail)
        assert detail_a["qualifying_levels"] == detail_b["qualifying_levels"] == "overnight_low,previous_day_low"

    def test_coincident_reference_levels_do_not_inflate_the_count_incorrectly(self):
        # Two DIFFERENT level names qualifying at the same price is still two
        # distinct entries in qualifying_levels (liquidity_sweep evaluates
        # each reference level independently) - the count reflects that
        # honestly; this setup does not attempt to deduplicate by price.
        levels = [
            _qualifying_level("previous_day_high", side="high", level=20140.0, excursion=20145.0),
            _qualifying_level("overnight_high", side="high", level=20140.0, excursion=20145.0),
        ]
        outcome = _evaluate(_context(_liquidity_sweep(value=True, qualifying_levels=levels), _volume_spike(value=True)))
        detail = dict(outcome.evidence.supporting_facts[0].detail)
        assert detail["qualifying_level_count"] == 2
        assert detail["qualifying_levels"] == "overnight_high,previous_day_high"

    def test_volume_spike_detail_matches_its_own_evidence_unchanged(self):
        outcome = _evaluate(_context(_liquidity_sweep(value=True), _volume_spike(value=True, ratio=3.5, threshold=1.5)))
        _, vs_fact = outcome.evidence.supporting_facts
        assert dict(vs_fact.detail) == {"volume_ratio": 3.5, "threshold": 1.5}

    def test_evidence_occurred_at_matches_context_current(self):
        context = _context(_liquidity_sweep(), _volume_spike())
        outcome = _evaluate(context)
        for fact in outcome.evidence.supporting_facts:
            assert fact.occurred_at == context.current.occurred_at


class TestDeterminism:
    def test_same_context_same_output(self):
        context = _context(_liquidity_sweep(value=True), _volume_spike(value=True))
        first = _evaluate(context)
        second = _evaluate(context)
        assert first == second
