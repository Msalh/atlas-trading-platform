"""
Phase N4 Sprint 4. Tests for atlas.research.features.candidate - the
Candidate evaluator's correctness, and the dedicated adversarial proof that
it cannot execute arbitrary code (only the fixed, closed spec vocabulary) -
a security property the roadmap's own test strategy calls out explicitly,
not just a correctness one.
"""
from datetime import datetime, timedelta, timezone

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.features.candidate import evaluate_candidate_feature, promote_candidate_to_registered
from atlas.research.features.models import (
    CandidateFeatureSpec,
    CandidateOperation,
    CandidateSourceField,
    FeatureComputed,
    FeatureInsufficientData,
    compute_feature_semantic_fingerprint,
)
from atlas.research.models import Feature, FeatureStatus, FeatureTier, ProvenanceKind

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)


def _state(event_id: str, occurred_at: datetime, volume) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=event_id),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        volume=volume,
    )


def _series(volumes: list, base: datetime = _BASE, cadence_minutes: int = 5) -> list[MarketState]:
    step = timedelta(minutes=cadence_minutes)
    return [_state(f"e{i}", base + step * i, v) for i, v in enumerate(volumes)]


# ---- evaluate_candidate_feature(): correctness ----

def test_rolling_mean_computes_correctly():
    spec = CandidateFeatureSpec(operation=CandidateOperation.ROLLING_MEAN, source_field=CandidateSourceField.VOLUME, window=3)
    window = _series([10.0, 20.0, 30.0])
    result = evaluate_candidate_feature(spec, window)
    assert isinstance(result, FeatureComputed)
    assert result.value == pytest.approx(20.0)
    assert result.feature_version == "candidate"


def test_rolling_max_computes_correctly():
    spec = CandidateFeatureSpec(operation=CandidateOperation.ROLLING_MAX, source_field=CandidateSourceField.VOLUME, window=3)
    result = evaluate_candidate_feature(spec, _series([10.0, 50.0, 30.0]))
    assert isinstance(result, FeatureComputed)
    assert result.value == 50.0


def test_rolling_min_computes_correctly():
    spec = CandidateFeatureSpec(operation=CandidateOperation.ROLLING_MIN, source_field=CandidateSourceField.VOLUME, window=3)
    result = evaluate_candidate_feature(spec, _series([10.0, 50.0, 30.0]))
    assert isinstance(result, FeatureComputed)
    assert result.value == 10.0


def test_candidate_uses_only_the_trailing_window():
    spec = CandidateFeatureSpec(operation=CandidateOperation.ROLLING_MEAN, source_field=CandidateSourceField.VOLUME, window=2)
    result = evaluate_candidate_feature(spec, _series([1000.0, 1000.0, 10.0, 20.0]))
    assert isinstance(result, FeatureComputed)
    assert result.value == pytest.approx(15.0)


def test_candidate_insufficient_when_window_shorter_than_required():
    spec = CandidateFeatureSpec(operation=CandidateOperation.ROLLING_MEAN, source_field=CandidateSourceField.VOLUME, window=5)
    result = evaluate_candidate_feature(spec, _series([1.0, 2.0]))
    assert isinstance(result, FeatureInsufficientData)


def test_candidate_insufficient_when_source_field_missing_within_window():
    spec = CandidateFeatureSpec(operation=CandidateOperation.ROLLING_MEAN, source_field=CandidateSourceField.VOLUME, window=3)
    result = evaluate_candidate_feature(spec, _series([1.0, None, 3.0]))
    assert isinstance(result, FeatureInsufficientData)


def test_candidate_spec_rejects_non_positive_window_at_construction():
    with pytest.raises(ValueError, match="window must be >= 1"):
        CandidateFeatureSpec(operation=CandidateOperation.ROLLING_MEAN, source_field=CandidateSourceField.VOLUME, window=0)


# ---- adversarial: no arbitrary code execution is possible ----

def test_an_unrecognized_operation_string_cannot_even_be_constructed():
    """The closed-vocabulary guarantee is enforced at spec construction,
    before evaluate_candidate_feature is ever reached - an adversarial
    operation string is rejected by the enum itself."""
    with pytest.raises(ValueError):
        CandidateOperation("eval")


def test_an_unrecognized_source_field_string_cannot_even_be_constructed():
    with pytest.raises(ValueError):
        CandidateSourceField("__class__")


def test_a_python_expression_string_cannot_be_used_as_an_operation():
    with pytest.raises(ValueError):
        CandidateOperation("__import__('os').system('echo pwned')")


def test_a_python_expression_string_cannot_be_used_as_a_source_field():
    with pytest.raises(ValueError):
        CandidateSourceField("__import__('os').system('echo pwned')")


def test_candidate_feature_spec_has_no_free_form_expression_field():
    """Every field on CandidateFeatureSpec is a closed enum or a bounded
    int - confirmed directly against the dataclass's own field types, so
    this test fails loudly if a future edit ever adds a free-form string
    field to the spec."""
    import dataclasses
    allowed_types = (CandidateOperation, CandidateSourceField, int)
    for f in dataclasses.fields(CandidateFeatureSpec):
        assert f.type in allowed_types, (
            f"CandidateFeatureSpec.{f.name} has type {f.type!r} - only closed enums and int are permitted"
        )


# ---- promote_candidate_to_registered() ----

def _candidate_feature(**overrides) -> Feature:
    name = overrides.get("name", "mean_volume")
    version = overrides.get("version", "0.1")
    definition = overrides.get("definition", {"window": 3})
    fields = dict(
        feature_id="c1", name=name, tier=FeatureTier.CANDIDATE, version=version,
        description="candidate", definition=definition, status=FeatureStatus.EVALUATED,
        provenance=ProvenanceKind.DISCOVERY_ENGINE, created_at="2026-07-22T00:00:00+00:00",
        fingerprint=compute_feature_semantic_fingerprint(name, version, definition),
    )
    fields.update(overrides)
    return Feature(**fields)


def test_promotion_produces_a_new_registered_feature():
    candidate = _candidate_feature()
    promoted = promote_candidate_to_registered(candidate, new_feature_id="mean_volume", promoted_at="2026-07-22T01:00:00+00:00")
    assert promoted.feature_id == "mean_volume"
    assert promoted.tier == FeatureTier.REGISTERED
    assert promoted.status == FeatureStatus.PROMOTED
    assert promoted.name == candidate.name
    assert promoted.version == candidate.version
    assert dict(promoted.definition) == dict(candidate.definition)
    assert promoted.provenance == candidate.provenance


def test_promotion_preserves_the_semantic_fingerprint():
    """The core proof this correction exists for: promotion changes
    review/trust status (tier CANDIDATE -> REGISTERED, status EVALUATED ->
    PROMOTED, a new feature_id), but the underlying computation
    (name/version/definition) is unchanged, so the semantic fingerprint
    must be IDENTICAL before and after - computation identity and
    lifecycle identity are independent axes."""
    candidate = _candidate_feature()
    promoted = promote_candidate_to_registered(candidate, new_feature_id="mean_volume", promoted_at="2026-07-22T01:00:00+00:00")
    assert promoted.fingerprint == candidate.fingerprint
    # And explicitly independent of tier/status/feature_id, which DID change:
    assert promoted.tier != candidate.tier
    assert promoted.status != candidate.status
    assert promoted.feature_id != candidate.feature_id


def test_two_features_with_identical_computation_but_different_tier_share_a_fingerprint():
    """Directly against compute_feature_semantic_fingerprint(), independent
    of the promotion function - tier is not even a parameter, so there is
    nothing for it to influence."""
    fp = compute_feature_semantic_fingerprint("mean_volume", "0.1", {"window": 3})
    candidate = _candidate_feature(fingerprint=fp)
    registered = _candidate_feature(feature_id="r1", tier=FeatureTier.REGISTERED, status=FeatureStatus.PROMOTED, fingerprint=fp)
    assert candidate.fingerprint == registered.fingerprint == fp


def test_promotion_does_not_mutate_or_touch_the_original_candidate():
    candidate = _candidate_feature()
    promote_candidate_to_registered(candidate, new_feature_id="mean_volume", promoted_at="2026-07-22T01:00:00+00:00")
    assert candidate.tier == FeatureTier.CANDIDATE
    assert candidate.status == FeatureStatus.EVALUATED


def test_promotion_rejects_a_feature_that_is_already_registered_tier():
    already_registered = _candidate_feature(tier=FeatureTier.REGISTERED)
    with pytest.raises(ValueError, match="only a CANDIDATE-tier"):
        promote_candidate_to_registered(already_registered, new_feature_id="x", promoted_at="2026-07-22T01:00:00+00:00")


def test_promotion_rejects_a_candidate_not_yet_evaluated():
    not_evaluated = _candidate_feature(status=FeatureStatus.PROPOSED)
    with pytest.raises(ValueError, match="only an EVALUATED candidate"):
        promote_candidate_to_registered(not_evaluated, new_feature_id="x", promoted_at="2026-07-22T01:00:00+00:00")
