"""
Phase N4 Sprint 4. The one, fixed, reviewed evaluator for every Candidate
feature, plus the pure function that promotes an evaluated Candidate to
the Registered tier.

evaluate_candidate_feature() interprets a CandidateFeatureSpec's closed
vocabulary (models.py's CandidateOperation/CandidateSourceField enums)
only - it never eval()s a string, never imports or invokes caller-supplied
code, and never resolves a field name via getattr(state, spec.source_field)
(an unchecked getattr would let a spec name ANY MarketState attribute, or
worse, a dunder - exactly the arbitrary-code-adjacent surface Design
Principle VIII.1's feature-generation-safety extension forbids). Every
dispatch below is a closed if/elif over enum values that cannot themselves
be constructed outside the closed vocabulary - CandidateOperation("eval")
or CandidateSourceField("__class__") both raise ValueError at spec
construction, before this function is ever reached.

promote_candidate_to_registered() is pure with respect to persistence -
it returns a new Feature value, it never writes to the Ledger
(atlas.research.stores). The caller decides whether/where to record the
result, the same "orchestration decides persistence, not the pure core"
split atlas.research.service.run_experiment already established.

Promotion mints a NEW feature_id, never reusing the candidate's own id:
Features are immutable/append-only (the same discipline
atlas.research.stores.FeatureRegistry.register() already enforces via its
idempotent-or-reject check - re-registering the candidate's own id with a
different tier/status/fingerprint would correctly raise
RecordConflictError), so promotion is a forward link to a new record,
never an in-place edit. Sprint 1's frozen Feature model has no
"promoted_from" lineage field, so this new record does not structurally
point back to the candidate it came from - a disclosed, minor limitation
of this sprint's minimal scope, not a defect; nothing in the frozen
Blueprint or Design Principles requires that lineage to be queryable, and
adding a field for it now would be exactly the kind of speculative model
change Sprint 1 being frozen forbids.
"""
from atlas.market_engine.models import MarketState
from atlas.research.features.models import (
    CandidateFeatureSpec,
    CandidateOperation,
    CandidateSourceField,
    FeatureComputed,
    FeatureInsufficientData,
    FeatureOutcome,
    compute_feature_semantic_fingerprint,
)
from atlas.research.models import Feature, FeatureStatus, FeatureTier


def _read_source_field(state: MarketState, field: CandidateSourceField):
    """The ONLY place a CandidateFeatureSpec's source_field ever touches a
    MarketState attribute - a closed if/elif dispatch, never
    getattr(state, field)."""
    if field == CandidateSourceField.ATR:
        return state.atr
    if field == CandidateSourceField.VOLUME:
        return state.volume
    if field == CandidateSourceField.VWAP:
        return state.vwap
    if field == CandidateSourceField.VOLUME_RATIO:
        return state.volume_ratio
    if field == CandidateSourceField.DISTANCE_FROM_VWAP_POINTS:
        return state.distance_from_vwap_points
    raise ValueError(f"unhandled CandidateSourceField: {field!r}")  # unreachable - closed enum


def evaluate_candidate_feature(spec: CandidateFeatureSpec, window: list[MarketState]) -> FeatureOutcome:
    label = f"candidate:{spec.operation.value}:{spec.source_field.value}"
    if len(window) < spec.window:
        return FeatureInsufficientData(
            feature_name=label, feature_version="candidate",
            reason=f"requires {spec.window} bars, got {len(window)}",
        )
    trailing = window[-spec.window:]
    raw_values = [_read_source_field(state, spec.source_field) for state in trailing]
    values = [v for v in raw_values if v is not None]
    if len(values) != spec.window:
        return FeatureInsufficientData(
            feature_name=label, feature_version="candidate",
            reason=f"{spec.source_field.value} is missing on {spec.window - len(values)} of the {spec.window} trailing bars",
        )

    if spec.operation == CandidateOperation.ROLLING_MEAN:
        result = sum(values) / len(values)
    elif spec.operation == CandidateOperation.ROLLING_MAX:
        result = max(values)
    elif spec.operation == CandidateOperation.ROLLING_MIN:
        result = min(values)
    else:
        raise ValueError(f"unhandled CandidateOperation: {spec.operation!r}")  # unreachable - closed enum

    return FeatureComputed(feature_name=label, feature_version="candidate", value=result)


def promote_candidate_to_registered(candidate: Feature, new_feature_id: str, promoted_at: str) -> Feature:
    """Only an EVALUATED Candidate may be promoted (blueprint §2.2's own
    Feature lifecycle: PROPOSED -> EVALUATED -> PROMOTED). Returns a new,
    Registered-tier Feature sharing the candidate's own name/version/
    definition/provenance. Its fingerprint is recomputed via the same
    compute_feature_semantic_fingerprint() the candidate's own fingerprint
    should already have used - since tier plays no part in that
    projection, an unchanged name/version/definition correctly produces
    the SAME fingerprint as the candidate had: promotion changes review/
    trust status, never what is computed."""
    if candidate.tier != FeatureTier.CANDIDATE:
        raise ValueError(f"{candidate.feature_id}: only a CANDIDATE-tier feature may be promoted, got {candidate.tier.value}")
    if candidate.status != FeatureStatus.EVALUATED:
        raise ValueError(f"{candidate.feature_id}: only an EVALUATED candidate may be promoted, got {candidate.status.value}")

    fingerprint = compute_feature_semantic_fingerprint(candidate.name, candidate.version, candidate.definition)
    return Feature(
        feature_id=new_feature_id,
        name=candidate.name,
        tier=FeatureTier.REGISTERED,
        version=candidate.version,
        description=candidate.description,
        definition=candidate.definition,
        status=FeatureStatus.PROMOTED,
        provenance=candidate.provenance,
        created_at=promoted_at,
        fingerprint=fingerprint,
    )
