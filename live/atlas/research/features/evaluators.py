"""
Phase N4 Sprint 4. Registered-tier feature computation functions - the
research-only analogue of atlas.rule_engine.facts, mirroring its shape
exactly (pure, synchronous, no I/O; a window - list[MarketState],
chronologically ascending, current/latest bar last, the same convention
facts.py's own windowed functions already use) without importing anything
from atlas.rule_engine.

Sprint 4's one real, deliberately minimal example: mean_atr, the rolling
mean of MarketState.atr over the trailing `feature.definition["window"]`
bars. Chosen because it is a genuinely useful research quantity Rule
Engine deliberately does not produce (Rule Engine emits boolean/enum
FACTS for production rule evaluation; a continuous rolling statistic is
exactly the kind of thing Research Engine exists to compute instead,
without ever touching Rule Engine's own frozen registry) and because it
needs no Price-unwrapping (atr is already a plain float), keeping this
sprint's one example self-contained.
"""
from atlas.market_engine.models import MarketState
from atlas.research.features.models import FeatureComputed, FeatureInsufficientData, FeatureOutcome
from atlas.research.models import Feature


def evaluate_mean_atr(window: list[MarketState], feature: Feature) -> FeatureOutcome:
    """required window size and version both come from `feature` -
    definition.window/name/version - never a second, independently-set
    copy that could drift from the registered Feature record itself, the
    same discipline atlas.rule_engine.facts's own evaluate_* functions
    already follow via their FactDefinition parameter."""
    required = feature.definition["window"]
    if len(window) < required:
        return FeatureInsufficientData(
            feature_name=feature.name, feature_version=feature.version,
            reason=f"requires {required} bars, got {len(window)}",
        )
    trailing = window[-required:]
    values = [state.atr for state in trailing if state.atr is not None]
    if len(values) != required:
        return FeatureInsufficientData(
            feature_name=feature.name, feature_version=feature.version,
            reason=f"atr is missing on {required - len(values)} of the {required} trailing bars",
        )
    return FeatureComputed(feature_name=feature.name, feature_version=feature.version, value=sum(values) / required)
