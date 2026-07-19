"""
Rule Engine domain model - Sprint 11 (Phase 3, foundation), extended Sprint 12
(FactDefinition, per-fact versioning). A separately-owned output type, never a
mutation of MarketState - market_state_events rows are immutable once stored
(Immutability Rules); this module's types are the Rule Engine's own domain
objects, computed fresh from stored data, never written back into Market
Engine. See docs/market_engine/rule-engine-architecture.md's Outputs section
for the full reasoning.

FactResult / InsufficientData are the explicit insufficient-data
representation introduced in Sprint 11 - applying the EmptyResult/InvalidRange
distinction raised for Replay to Rule Engine facts too: a fact that was
computed and found nothing notable (FactResult(value=False, ...)) must never
be confused with a fact that could NOT be computed at all (InsufficientData) -
collapsing the two would hide a data problem behind what looks like a market
observation.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Union


@dataclass(frozen=True)
class FactDefinition:
    """Sprint 12: separates a rule's tunable parameters (thresholds, window
    sizes, method choices) from the evaluation logic that reads them - so a
    heuristic can be retuned, or an alternate definition swapped in, without
    touching (or re-reviewing) the function that implements the rule's
    structure. `params` deliberately is NOT dict[str, float]: window sizes are
    integers, some future rule's method choice may be a string, and some may
    be booleans - a real, disclosed reason to widen beyond float, not
    speculative generality. `version` is per-fact, independent of
    RuleEngineOutput.schema_version below (which versions the OUTPUT
    envelope's shape) - two different things that should be free to change on
    different schedules once individual rules start evolving independently.

    Immutable in fact, not just by type hint: __post_init__ wraps `params` in
    a MappingProxyType over a copy, so holding a FactDefinition never risks
    the underlying dict being mutated out from under a caller - the same
    frozen-dataclass-plus-__post_init__-normalization pattern
    atlas.core.primitives.Symbol already established."""

    name: str
    version: str
    params: Mapping[str, Union[int, float, str, bool]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


@dataclass(frozen=True)
class FactResult:
    """A fact that was successfully computed. `evidence` preserves the
    numerical/structural inputs and threshold(s) behind `value` - per
    standing guidance, a deterministic fact's "confidence" is not a
    fabricated probability (that would blur the deterministic/probabilistic
    boundary docs/market_engine/rule-engine-architecture.md exists to
    protect); it is the evidence itself, so the result stays auditable
    without inventing a score. `evidence` is dict[str, Any] (widened Sprint 12
    from Sprint 11's dict[str, float]) because `rejection` needs to preserve a
    list of per-reference-level evidence records, not just flat numbers.
    `value` is Union[bool, str] (widened Sprint 13 from Sprint 11/12's plain
    bool) because `trend_5m` is a three-way classification ("up"/"down"/
    "flat"), not a boolean - every other fact so far remains a bool; this
    widening is additive, not a change to any existing fact's value type.
    `definition_version` names exactly which FactDefinition version produced
    this result - independent of the fact's own value, so a later heuristic
    change is traceable per-result, not just per-Sprint."""

    fact_name: str
    definition_version: str
    value: Union[bool, str]
    evidence: dict[str, Any]


@dataclass(frozen=True)
class InsufficientData:
    """A fact that could NOT be computed - distinct from a fact that was
    computed and evaluated to False. `reason` names exactly what was missing,
    so this is diagnosable, not just a silent gap."""

    fact_name: str
    definition_version: str
    reason: str


FactOutcome = Union[FactResult, InsufficientData]


@dataclass(frozen=True)
class RuleEngineOutput:
    """The Rule Engine's versioned, top-level output for one MarketState.
    symbol/timeframe/occurred_at identify WHICH market moment this describes -
    occurred_at, not received_at, the same market-meaningful-timestamp
    convention MarketState itself uses. `facts` maps fact name to its
    outcome - deliberately a dict, not named fields, so a later slice adding
    a new fact never requires changing this type's shape, only adding a key.
    `schema_version` versions this OUTPUT ENVELOPE's shape - distinct from
    each fact's own `definition_version` above, which versions that fact's
    specific rule."""

    schema_version: str
    symbol: str
    timeframe: str
    occurred_at: str
    facts: dict[str, FactOutcome]
