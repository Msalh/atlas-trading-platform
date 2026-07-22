"""
Phase N4 Sprint 4. A static, ordered registry of every active Registered
feature - the research-only analogue of atlas.rule_engine.registry's
REGISTRY/FactRegistration/validate_registry/required_history shape,
mirrored here without importing anything from atlas.rule_engine (see this
package's own __init__.py docstring for why). REGISTRY is internal,
in-package, static code - not a dynamic/pluggable registration API, the
same scope boundary Rule Engine's own registry.py already drew.

Every entry's Feature record is constructed here, at module load, already
fingerprinted via atlas.research.features.models.compute_feature_semantic_fingerprint()
- the first real computation of Feature.fingerprint since Sprint 1 left it
required-but-unpopulated (nothing existed yet to fingerprint). See that
function's own docstring for exactly which fields participate (and why
tier does not).

validate_registry() runs once, at the bottom of this module (import
time) - a failure here is a programming error, not a runtime condition,
the same "refuse to start unsafely, fail fast and loud" posture
atlas.rule_engine.registry's own validate_registry() already established.

feature_id vs. name vs. version (corrected after the Sprint 4->5 boundary
review found the original identity model incoherent): `name` is the
STABLE lineage identity of a Feature family - "mean_atr" for every
revision. `version` distinguishes revisions within that lineage - a logic
or default-param change is a brand-new, additively-registered
FeatureRegistration (new feature_id, new version, SAME name) - never an
edit to an existing entry, the same append-only discipline Rule Engine's
own REGISTRY already follows. `feature_id` is the unique PER-REVISION
storage/reference key a future Sprint 5 resolves feature_refs against -
it must stay per-revision-unique, never lineage-stable, because
reproducibility (Design Principles VII.1) needs an exact pin, not a
family reference. The original version of this module wrongly forced
feature_id == name and treated `name` as if it, too, had to be globally
unique - which made two coexisting versions of the same feature
structurally impossible. Fixed below: feature_id uniqueness and
(name, version) uniqueness are now the two real invariants; the same name
with a different version is explicitly permitted.
"""
from dataclasses import dataclass
from typing import Callable, Mapping, Union

from atlas.market_engine.models import MarketState
from atlas.research.features.evaluators import evaluate_mean_atr
from atlas.research.features.models import FeatureOutcome, compute_feature_semantic_fingerprint
from atlas.research.models import Feature, FeatureStatus, FeatureTier, ProvenanceKind

WindowedFeatureEvaluator = Callable[[list[MarketState], Feature], FeatureOutcome]


@dataclass(frozen=True)
class FeatureRegistration:
    """One entry in REGISTRY. `evaluate` always takes the uniform
    (list[MarketState], Feature) -> FeatureOutcome signature, reading
    required window size/name/version directly off `feature` - never a
    second, independently-set copy of any of those values."""

    feature: Feature
    evaluate: WindowedFeatureEvaluator


_MEAN_ATR_NAME = "mean_atr"
_MEAN_ATR_VERSION = "1.0"
_MEAN_ATR_DEFINITION: Mapping[str, Union[int, float, str, bool]] = {"window": 14}

_MEAN_ATR_FEATURE = Feature(
    feature_id=_MEAN_ATR_NAME,
    name=_MEAN_ATR_NAME,
    tier=FeatureTier.REGISTERED,
    version=_MEAN_ATR_VERSION,
    description="Rolling mean of MarketState.atr over the trailing definition['window'] bars.",
    definition=_MEAN_ATR_DEFINITION,
    status=FeatureStatus.PROMOTED,
    provenance=ProvenanceKind.HUMAN,
    created_at="2026-07-22T00:00:00+00:00",
    fingerprint=compute_feature_semantic_fingerprint(_MEAN_ATR_NAME, _MEAN_ATR_VERSION, _MEAN_ATR_DEFINITION),
)


REGISTRY: tuple[FeatureRegistration, ...] = (
    FeatureRegistration(feature=_MEAN_ATR_FEATURE, evaluate=evaluate_mean_atr),
)


def validate_registry(registry: tuple[FeatureRegistration, ...]) -> None:
    """Fail-fast validation, checked in order: non-empty; every
    feature_id is unique (the real referential-integrity concern - this
    is the key a future Sprint 5 resolves feature_refs against); every
    (name, version) pair is unique (no re-registering the same revision
    twice) - the SAME name with a DIFFERENT version is explicitly
    permitted, this is what makes additive feature versioning possible at
    all; every entry is REGISTERED tier (Candidate features are never
    part of this static registry - see candidate.py); and every entry
    declares a positive int 'window' param - explicitly rejecting bool (a
    bool is an int subclass in Python, so `type(value) is int` is used
    rather than isinstance, the same guard rule_engine's own validator
    already uses)."""
    if not registry:
        raise ValueError("REGISTRY must not be empty")

    feature_ids = [r.feature.feature_id for r in registry]
    duplicate_ids = sorted({fid for fid in feature_ids if feature_ids.count(fid) > 1})
    if duplicate_ids:
        raise ValueError(f"REGISTRY contains duplicate feature_ids: {duplicate_ids}")

    lineage_versions = [(r.feature.name, r.feature.version) for r in registry]
    duplicate_revisions = sorted({lv for lv in lineage_versions if lineage_versions.count(lv) > 1})
    if duplicate_revisions:
        raise ValueError(f"REGISTRY contains duplicate (name, version) revisions: {duplicate_revisions}")

    for r in registry:
        if r.feature.tier != FeatureTier.REGISTERED:
            raise ValueError(
                f"{r.feature.name}: REGISTRY may only contain REGISTERED-tier features, got {r.feature.tier.value}"
            )
        if "window" not in r.feature.definition:
            raise ValueError(f"{r.feature.name}: definition must declare a 'window' param")
        value = r.feature.definition["window"]
        if type(value) is not int:
            raise ValueError(f"{r.feature.name}: definition['window'] must be an int, got {type(value).__name__} ({value!r})")
        if value < 1:
            raise ValueError(f"{r.feature.name}: definition['window'] must be >= 1, got {value}")


def required_history(registry: tuple[FeatureRegistration, ...] = REGISTRY) -> int:
    """The history depth a caller must supply to satisfy every active
    Registered feature - the maximum required window across the
    registry, the same computed-not-hardcoded convention
    atlas.rule_engine.registry.required_history() already established."""
    return max(r.feature.definition["window"] for r in registry)


validate_registry(REGISTRY)
