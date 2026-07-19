"""
Sprint 17B (Setup Engine Foundation). Setup Engine's own domain model - a
structural clone of atlas.rule_engine.models, one layer up: it consumes
RuleEngineOutput (never MarketState directly - checked by this Sprint's own
Dependency Rule grep) and produces its own separately-owned output type, the
same "never mutate or extend what you consume" discipline Rule Engine
already applies to MarketState.

No real setup (ICT, Wyckoff, Order Flow, Auction Market Theory) is defined
here or anywhere yet - this module only defines the shapes a future setup
will be expressed in. See docs/market_engine/roadmap.md's Phase 3 entry.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Optional, Union

from atlas.rule_engine.models import RuleEngineOutput


class SetupFamily(str, Enum):
    """Closed, deliberately - the same discipline atlas.core.primitives.Timeframe
    already established ("extend this enum, don't parameterize it with an
    arbitrary string"). A setup with an ambiguous family should force a
    deliberate enum extension, not fall into a catch-all - MOMENTUM was added
    exactly that way (Sprint 18): the first real setup (range/ATR expansion
    confirmed by volume) uses no bid/ask, delta, footprint, imbalance, or
    absorption data, so ORDER_FLOW would have diluted that family's meaning
    before any real order-flow setup exists. A future setup with an equally
    genuine mismatch should extend this enum the same way, not be forced into
    the nearest imperfect fit.

    CONFLUENCE (Sprint 23A) was added the same way, for the opposite failure
    mode MOMENTUM's addition prevented: instead of one fact's structure being
    forced into the wrong family, CONFLUENCE exists for setups where NO fact
    has legitimate semantic primacy at all - composing two or more
    independently-computed facts whose co-occurrence is reported without
    asserting any directional, continuation, reversal, momentum, or
    mean-reversion thesis (nor ICT/Wyckoff/auction-market/order-flow
    interpretation). `vwap_extension_with_volume_confirmation` is the
    motivating case: VWAP extension plus a volume spike is deliberately
    neutral - unlike `displacement_with_volume_confirmation` (MOMENTUM,
    because displacement genuinely defines the primary structure and volume
    only confirms it) or `liquidity_sweep_with_volume_confirmation` (ICT, same
    reasoning with liquidity_sweep as the primary structure).

    Classification precedence, checked in this order for every setup, present
    and future: (1) if one fact clearly defines the setup's primary structure
    and the others merely confirm it, use THAT fact's domain family - CONFLUENCE
    is never the answer when a real primary structure exists. (2) CONFLUENCE
    applies only when no fact or structure has legitimate semantic primacy -
    the co-occurrence itself is the entire content of what's being reported.

    CONFLUENCE must NOT become a generic fallback category - a setup only
    belongs here when it genuinely composes 2+ independent facts, its
    detected result means only that those conditions coexist, and it
    affirmatively asserts none of the interpretations named above. A setup
    that's merely hard to classify at first glance is a sign the classifier
    hasn't found the primary-structure fact yet, not evidence it belongs in
    CONFLUENCE - re-examine for primacy before reaching for this member."""

    ICT = "ict"
    WYCKOFF = "wyckoff"
    ORDER_FLOW = "order_flow"
    AUCTION_MARKET_THEORY = "auction_market_theory"
    MOMENTUM = "momentum"
    CONFLUENCE = "confluence"


class Severity(str, Enum):
    """A deterministic, categorical summary of a detected setup's underlying
    evidence - deliberately NOT a float in [0, 1] and deliberately not named
    "confidence": an enum cannot be averaged, thresholded with `>`, or
    mistaken for a statistical score by a future consumer skimming the type
    signature. The raw numbers behind this categorization remain visible in
    SetupResult.evidence - this is a coarse summary layered on top of them,
    never a replacement."""

    WEAK = "weak"
    NORMAL = "normal"
    STRONG = "strong"


@dataclass(frozen=True)
class SupportingFact:
    """One Rule Engine fact's contribution to a setup's evidence. `detail` is
    bounded to the same Mapping[str, int|float|str|bool] constraint already
    established for FactDefinition.params (Sprint 12/14) - reused
    deliberately, not a new typing discipline invented here, and not a
    fully-open dict[str, Any] either: every setup's evidence has this exact
    shape, a consistent contract for whatever eventually consumes it (a
    future LLM, first). Immutable in fact, not just by type hint - same
    MappingProxyType normalization FactDefinition.params already
    established."""

    fact_name: str
    occurred_at: str
    value: Union[bool, str]
    detail: Mapping[str, Union[int, float, str, bool]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


@dataclass(frozen=True)
class SetupEvidence:
    """Every fact that contributed to one SetupResult, in the order the
    setup's own logic consulted them - not registry order, not sorted."""

    supporting_facts: tuple[SupportingFact, ...]


@dataclass(frozen=True)
class SetupDefinition:
    """Setup Engine's analog of FactDefinition - separates a setup's tunable
    parameters from the evaluation logic that reads them. `family` is a
    SetupFamily, not a free string (see that enum's own docstring for why).
    Immutable in fact, not just by type hint - same MappingProxyType
    normalization FactDefinition already established."""

    name: str
    version: str
    family: SetupFamily
    params: Mapping[str, Union[int, float, str, bool]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


@dataclass(frozen=True)
class SetupResult:
    """A setup that was successfully evaluated - `detected` states whether it
    fired, independent of whether it COULD be evaluated at all (see
    InsufficientData below for that distinct case, the same EmptyResult/
    InvalidRange-style split Rule Engine already applies).

    `severity` is meaningful only when detected=True - enforced structurally,
    not just documented: a non-detected result asserting a severity would be
    a contradiction (how strong is a setup that wasn't found?), so that
    state is made unconstructable rather than merely discouraged."""

    setup_name: str
    definition_version: str
    detected: bool
    severity: Optional[Severity]
    evidence: SetupEvidence

    def __post_init__(self) -> None:
        if not self.detected and self.severity is not None:
            raise ValueError(
                f"{self.setup_name}: severity must be None when detected=False, "
                f"got {self.severity!r}"
            )


@dataclass(frozen=True)
class InsufficientData:
    """A setup that could NOT be evaluated - distinct from SetupResult, and
    distinct from atlas.rule_engine.models.InsufficientData: this type's
    identifier field is setup_name, not fact_name. Reusing Rule Engine's type
    would leave that field misleadingly named for what it actually
    identifies here - the same domain-separation reasoning that already
    keeps MarketState separate from the TradingView wire model."""

    setup_name: str
    definition_version: str
    reason: str


SetupOutcome = Union[SetupResult, InsufficientData]


@dataclass(frozen=True)
class SetupEngineOutput:
    """Setup Engine's versioned, top-level output for one moment in the
    series - symbol/timeframe/occurred_at copied from the
    SetupEvaluationContext it was built from (context.current), never
    re-derived independently.

    `setups` is an ORDERED TUPLE, not a dict keyed by name - unlike
    RuleEngineOutput.facts. Every SetupOutcome already carries its own
    setup_name (see above), so a dict key would only duplicate that value;
    keeping the canonical container ordered end-to-end (construction through
    serialization) instead avoids that redundancy and means the in-memory
    contract and the JSON contract are identical in shape, not just in
    content - no dict-to-list transformation step is needed at
    serialization time. Order is registry order (Sprint 14's own
    established "registry tuple order provides deterministic output
    ordering" rule, reused here)."""

    schema_version: str
    symbol: str
    timeframe: str
    occurred_at: str
    setups: tuple[SetupOutcome, ...]


@dataclass(frozen=True)
class SetupEvaluationContext:
    """What a setup's evaluate() function receives - the current
    RuleEngineOutput plus however much preceding history the caller
    assembled, in the same ascending-with-current-last convention every
    window in this codebase already uses. `current` is a derived property,
    never a second independently-set field, so it can never disagree with
    history[-1] - the same discipline FactRegistration.required_window
    already established for avoiding a second, driftable copy of a
    derivable value.

    Rejects an empty history in __post_init__ - defense in depth, not the
    primary guard: the intended construction path (Sprint 17A's
    build_rule_engine_output_window) already refuses an empty input and
    therefore can never produce an empty output either."""

    history: list[RuleEngineOutput]

    def __post_init__(self) -> None:
        if not self.history:
            raise ValueError("SetupEvaluationContext.history must not be empty")

    @property
    def current(self) -> RuleEngineOutput:
        return self.history[-1]
