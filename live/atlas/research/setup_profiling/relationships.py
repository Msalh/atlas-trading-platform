"""
Sprint RE-2, amendment 5. Centralized, typed relationship metadata for every
pair of currently-registered setups - consumed by reports.py and
service.py's overlap builder, never hand-labeled inside Markdown rendering.

Each entry's category is derived by direct inspection of the setup's own
evaluate() logic (atlas/setup_engine/setups/*.py), the same "prove it from
the definitions" discipline atlas/rule_engine/facts.py's own fact-hierarchy
docstrings already established for rejection/reclaim implying
liquidity_sweep at the FACT level. LOGICALLY_IMPLIED requires a proof that
one setup's detected=True forces the other's detected=True for every
computable input, under the CURRENT definition/params - sharing an input
fact is explicitly insufficient on its own (see the
displacement_with_volume_confirmation / sustained_displacement_streak
rationale below, the case amendment 5 named directly).

As of the four currently-registered setups, none of the 6 pairs is
LOGICALLY_IMPLIED - each setup was deliberately built from facts
"independent by construction" (every setup module's own docstring states
this), and no two setups' detection predicates are a subset of one another.
This is a real finding, not an unfinished analysis - the category exists in
SetupRelationshipCategory for a genuinely different, future setup (e.g. one
built directly from rejection or reclaim, which DO structurally imply
liquidity_sweep at the fact level) to use if one is ever registered.
"""
from atlas.research.setup_profiling.models import SetupRelationshipCategory, SetupRelationshipMetadata
from atlas.setup_engine.registry import REGISTRY

_LOGICALLY_IMPLIED = SetupRelationshipCategory.LOGICALLY_IMPLIED
_SHARED_INPUTS_ONLY = SetupRelationshipCategory.SHARED_INPUTS_ONLY
_EMPIRICAL = SetupRelationshipCategory.EMPIRICAL

DISPLACEMENT_WITH_VOLUME_CONFIRMATION = "displacement_with_volume_confirmation"
LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION = "liquidity_sweep_with_volume_confirmation"
SUSTAINED_DISPLACEMENT_STREAK = "sustained_displacement_streak"
VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION = "vwap_extension_with_volume_confirmation"

SETUP_RELATIONSHIPS: tuple[SetupRelationshipMetadata, ...] = (
    SetupRelationshipMetadata(
        setup_a=DISPLACEMENT_WITH_VOLUME_CONFIRMATION,
        setup_b=LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION,
        category=_SHARED_INPUTS_ONLY,
        rationale=(
            "Both require volume_spike=True (shared input), but their primary facts - displacement "
            "(range/ATR-based, single bar) and liquidity_sweep (reference-level breach across its own "
            "window) - have no established implication relationship in either direction at the fact "
            "level (only rejection/reclaim => liquidity_sweep is proven, per rule-fact-inventory.md's "
            "'Fact hierarchy within this family'; displacement is unrelated to that family). Neither "
            "setup's detected=True forces the other's."
        ),
    ),
    SetupRelationshipMetadata(
        setup_a=DISPLACEMENT_WITH_VOLUME_CONFIRMATION,
        setup_b=SUSTAINED_DISPLACEMENT_STREAK,
        category=_SHARED_INPUTS_ONLY,
        rationale=(
            "Both read displacement (shared input), but the predicates differ in two independent ways: "
            "displacement_with_volume_confirmation additionally requires volume_spike=True on the same "
            "bar, which sustained_displacement_streak never checks at all; sustained_displacement_streak "
            "additionally requires displacement=True on >=2 CONSECUTIVE bars ending at the current one, "
            "which displacement_with_volume_confirmation never checks (it looks at exactly one bar). "
            "displacement=True with volume_spike=True on an isolated bar (displacement=False the bar "
            "before) satisfies the first setup but not the second; a 2+ bar displacement streak with "
            "volume_spike=False throughout satisfies the second but not the first. Sharing an input fact "
            "does not make these logically related - the explicit case amendment 5 named."
        ),
    ),
    SetupRelationshipMetadata(
        setup_a=DISPLACEMENT_WITH_VOLUME_CONFIRMATION,
        setup_b=VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION,
        category=_SHARED_INPUTS_ONLY,
        rationale=(
            "Both require volume_spike=True (shared input); their other primary facts - displacement "
            "and vwap_relationship - are computed from unrelated MarketState fields with no known "
            "implication relationship. Neither setup's detected=True forces the other's."
        ),
    ),
    SetupRelationshipMetadata(
        setup_a=LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION,
        setup_b=SUSTAINED_DISPLACEMENT_STREAK,
        category=_EMPIRICAL,
        rationale=(
            "No shared input facts at all: liquidity_sweep_with_volume_confirmation reads "
            "liquidity_sweep and volume_spike; sustained_displacement_streak reads displacement only. "
            "Any co-occurrence found between these two is a genuine empirical finding, not implied by "
            "either setup's definition."
        ),
    ),
    SetupRelationshipMetadata(
        setup_a=LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION,
        setup_b=VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION,
        category=_SHARED_INPUTS_ONLY,
        rationale=(
            "Both require volume_spike=True (shared input); liquidity_sweep and vwap_relationship have "
            "no known implication relationship. Neither setup's detected=True forces the other's."
        ),
    ),
    SetupRelationshipMetadata(
        setup_a=SUSTAINED_DISPLACEMENT_STREAK,
        setup_b=VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION,
        category=_EMPIRICAL,
        rationale=(
            "No shared input facts at all: sustained_displacement_streak reads displacement only; "
            "vwap_extension_with_volume_confirmation reads vwap_relationship and volume_spike. Any "
            "co-occurrence found between these two is a genuine empirical finding, not implied by "
            "either setup's definition."
        ),
    ),
)


def _pair_key(setup_a: str, setup_b: str) -> frozenset[str]:
    return frozenset({setup_a, setup_b})


_BY_PAIR: dict[frozenset[str], SetupRelationshipMetadata] = {
    _pair_key(m.setup_a, m.setup_b): m for m in SETUP_RELATIONSHIPS
}


def relationship_for(setup_a: str, setup_b: str) -> SetupRelationshipMetadata:
    """Order-independent lookup. Raises KeyError with a clear message for
    any pair not present in SETUP_RELATIONSHIPS - never silently defaults
    to UNKNOWN, so a newly-registered setup without a reviewed relationship
    entry fails loudly (validate_relationship_metadata below also catches
    this at import time)."""
    key = _pair_key(setup_a, setup_b)
    if key not in _BY_PAIR:
        raise KeyError(f"no relationship metadata for pair ({setup_a!r}, {setup_b!r}) - add an entry to SETUP_RELATIONSHIPS")
    return _BY_PAIR[key]


def validate_relationship_metadata() -> None:
    """Fail-fast, run once at module-import time below: every unordered
    pair of currently-registered setups must have exactly one
    SetupRelationshipMetadata entry - catches a newly-added setup that
    hasn't had its relationships to the existing three reviewed yet."""
    registered_names = sorted(r.name for r in REGISTRY)
    expected_pairs = {
        _pair_key(a, b)
        for i, a in enumerate(registered_names)
        for b in registered_names[i + 1:]
    }

    missing = expected_pairs - set(_BY_PAIR)
    if missing:
        raise ValueError(
            f"SETUP_RELATIONSHIPS is missing {len(missing)} pair(s) for currently-registered setups: "
            f"{sorted(tuple(sorted(pair)) for pair in missing)}"
        )

    stale = set(_BY_PAIR) - expected_pairs
    if stale:
        raise ValueError(
            f"SETUP_RELATIONSHIPS contains {len(stale)} pair(s) naming a setup no longer in REGISTRY: "
            f"{sorted(tuple(sorted(pair)) for pair in stale)}"
        )

    for m in SETUP_RELATIONSHIPS:
        if m.setup_a not in registered_names or m.setup_b not in registered_names:
            raise ValueError(f"relationship entry ({m.setup_a!r}, {m.setup_b!r}) names an unregistered setup")
        if not m.rationale or not m.rationale.strip():
            raise ValueError(f"relationship entry ({m.setup_a!r}, {m.setup_b!r}) has a blank rationale")


validate_relationship_metadata()
