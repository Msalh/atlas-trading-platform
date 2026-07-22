"""
Phase N4 Sprint 4. A static, ordered registry of every active Registered
feature - the research-only analogue of atlas.rule_engine.registry's
REGISTRY/FactRegistration/validate_registry/required_history shape,
mirrored here without importing anything from atlas.rule_engine (see this
package's own __init__.py docstring for why). REGISTRY is internal,
in-package, static code - not a dynamic/pluggable registration API, the
same scope boundary Rule Engine's own registry.py already drew.

Every entry's Feature record is constructed here, at module load, already
fingerprinted - the first real computation of Feature.fingerprint since
Sprint 1 left it required-but-unpopulated (nothing existed yet to
fingerprint). The projection hashed is deliberately curated - {name, tier,
version, definition} only, excluding feature_id/description/status/
provenance/created_at/superseded_by/fingerprint itself - the same
discipline atlas.research.fingerprint's own module docstring requires:
description is documentation, not semantic identity, and must never
change a Feature's fingerprint; status/provenance/created_at are
lifecycle/audit metadata, not defining characteristics of what is being
computed.

validate_registry() runs once, at the bottom of this module (import
time) - a failure here is a programming error, not a runtime condition,
the same "refuse to start unsafely, fail fast and loud" posture
atlas.rule_engine.registry's own validate_registry() already established.
"""
from dataclasses import dataclass
from typing import Callable, Mapping, Union

from atlas.market_engine.models import MarketState
from atlas.research.features.evaluators import evaluate_mean_atr
from atlas.research.features.models import FeatureOutcome
from atlas.research.fingerprint import compute_fingerprint
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


def _feature_fingerprint(name: str, tier: FeatureTier, version: str, definition: Mapping) -> str:
    """The curated projection every Registered feature's fingerprint is
    computed from - see this module's own docstring for exactly which
    fields participate and why."""
    return compute_fingerprint({"name": name, "tier": tier.value, "version": version, "definition": dict(definition)})


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
    fingerprint=_feature_fingerprint(_MEAN_ATR_NAME, FeatureTier.REGISTERED, _MEAN_ATR_VERSION, _MEAN_ATR_DEFINITION),
)


REGISTRY: tuple[FeatureRegistration, ...] = (
    FeatureRegistration(feature=_MEAN_ATR_FEATURE, evaluate=evaluate_mean_atr),
)


def validate_registry(registry: tuple[FeatureRegistration, ...]) -> None:
    """Fail-fast validation, checked in order: non-empty; unique names;
    every entry is REGISTERED tier (Candidate features are never part of
    this static registry - see candidate.py); registration identity
    (feature_id == name) matches, the same invariant
    atlas.rule_engine.registry's own validate_registry() enforces for
    registration.name/definition.name; and every entry declares a
    positive int 'window' param - explicitly rejecting bool (a bool is an
    int subclass in Python, so `type(value) is int` is used rather than
    isinstance, the same guard rule_engine's own validator already uses)."""
    if not registry:
        raise ValueError("REGISTRY must not be empty")

    names = [r.feature.name for r in registry]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"REGISTRY contains duplicate feature names: {duplicates}")

    for r in registry:
        if r.feature.tier != FeatureTier.REGISTERED:
            raise ValueError(
                f"{r.feature.name}: REGISTRY may only contain REGISTERED-tier features, got {r.feature.tier.value}"
            )
        if r.feature.feature_id != r.feature.name:
            raise ValueError(
                f"registration feature_id {r.feature.feature_id!r} does not match feature.name {r.feature.name!r}"
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
