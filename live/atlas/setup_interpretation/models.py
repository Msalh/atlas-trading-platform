"""
Setup Interpretation domain model - Sprint 1. SetupDirection,
DirectionSource, and SetupInterpretation are the only types this module
defines. No interpretation logic lives here - only the immutable shape an
interpretation takes, and the structural invariants that make an invalid
combination unconstructable rather than merely documented (the same
posture atlas.setup_engine.models.SetupResult already established for its
own detected/severity pairing).

SetupInterpretation deliberately does NOT carry symbol/timeframe: it is
always produced from a RuleEngineOutput/SetupEngineOutput pair the caller
already holds (both of which already carry that identity), so a copy here
would be directly redundant - not the same situation as MarketContext,
which is built from scattered individual parameters with no single
upstream container to recover identity from. occurred_at is kept, the
same "recoverable via join, but keep the one field genuinely needed to
know which bar this describes" choice atlas.strategy_engine.models
.StrategyDecision already made for the identical reason.

It also carries no raw evidence, no market price, no strategy identity, no
execution field, no repository metadata, and no transport/API field -
those all belong to a different layer's concern, or (for raw evidence) are
exactly the kind of re-derivable detail this layer's whole purpose is to
summarize into a stable, canonical answer instead of exposing.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SetupDirection(str, Enum):
    """The interpretation RESULT - what this layer concluded, not why.
    See DirectionSource for the "why"/"how" half of the answer; the two
    fields are read together, never direction alone."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class DirectionSource(str, Enum):
    """Where a SetupInterpretation's direction came from, or why it
    couldn't be produced. SETUP_EVIDENCE and RULE_FACT are both real,
    evidence-backed sources (a setup's own required_facts vs. a different,
    externally-referenced Rule Engine fact respectively) - either may
    legitimately produce BULLISH, BEARISH, or AMBIGUOUS. INTENTIONALLY_NEUTRAL
    and INSUFFICIENT_DATA are the two "no real direction was computed"
    cases, each paired with exactly one SetupDirection value (NEUTRAL and
    UNAVAILABLE respectively) - see SetupInterpretation's own invariants."""

    SETUP_EVIDENCE = "setup_evidence"
    RULE_FACT = "rule_fact"
    INTENTIONALLY_NEUTRAL = "intentionally_neutral"
    INSUFFICIENT_DATA = "insufficient_data"


_EVIDENCE_BACKED_SOURCES = (DirectionSource.SETUP_EVIDENCE, DirectionSource.RULE_FACT)


@dataclass(frozen=True)
class SetupInterpretation:
    """One canonical interpretation of one setup's outcome, for one bar.
    Never carries symbol/timeframe/raw evidence/market prices/strategy
    identity/execution or transport fields - see this module's own
    docstring for why.

    source_fact_ids/reason_codes are tuple[str, ...] - immutable by
    Python's own tuple semantics (never reassignable in any case, since
    this dataclass is frozen), and never sorted or de-duplicated as a set;
    order is caller-supplied and preserved, the same open-vocabulary,
    stable-ordering discipline atlas.strategy_engine.models.StrategyDecision
    already established for its own reason_codes/setup_ids.

    Invariants (unconstructable invalid states, not merely documented
    ones):

        - direction == UNAVAILABLE if and only if source == INSUFFICIENT_DATA.
        - source == INTENTIONALLY_NEUTRAL requires direction == NEUTRAL
          (not the converse - a future evidence-backed source may
          legitimately produce a genuine, data-dependent NEUTRAL reading
          too; only the intentionally-neutral case is pinned).
        - source in (SETUP_EVIDENCE, RULE_FACT) requires detected == True -
          an evidence-backed direction cannot exist for a setup that
          wasn't even detected.
        - detected == False forces direction == UNAVAILABLE and
          source == INSUFFICIENT_DATA - there is nothing else a
          non-detected setup's interpretation could honestly claim.

    "direction in (BULLISH, BEARISH) requires source in (SETUP_EVIDENCE,
    RULE_FACT)" is NOT separately coded below - it is already a logical
    consequence of the first two bullets' own contrapositives: if
    direction is BULLISH or BEARISH (so, not UNAVAILABLE and not NEUTRAL),
    the UNAVAILABLE<->INSUFFICIENT_DATA pairing already rules out
    source=INSUFFICIENT_DATA, and the INTENTIONALLY_NEUTRAL->NEUTRAL
    pairing already rules out source=INTENTIONALLY_NEUTRAL, leaving only
    SETUP_EVIDENCE or RULE_FACT possible. A separate, explicit check for
    this would be dead code - unreachable, since any state it would catch
    is already caught by one of the two checks above it.

    AMBIGUOUS is deliberately NOT restricted to one source: both
    SETUP_EVIDENCE (e.g. conflicting sides in a setup's own qualifying
    evidence) and RULE_FACT (e.g. a flat externally-referenced trend) may
    legitimately produce it - narrowing this further belongs to Sprint 2's
    interpretation logic, not to this model's own construction-time
    invariants."""

    occurred_at: datetime
    setup_id: str
    detected: bool
    direction: SetupDirection
    source: DirectionSource
    source_fact_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    interpretation_version: str
    interpretation_fingerprint: str

    def __post_init__(self) -> None:
        if not self.setup_id or not self.setup_id.strip():
            raise ValueError("setup_id must not be blank")
        if not self.interpretation_version or not self.interpretation_version.strip():
            raise ValueError("interpretation_version must not be blank")
        if not self.interpretation_fingerprint or not self.interpretation_fingerprint.strip():
            raise ValueError("interpretation_fingerprint must not be blank")

        if self.direction == SetupDirection.UNAVAILABLE and self.source != DirectionSource.INSUFFICIENT_DATA:
            raise ValueError(
                f"direction=UNAVAILABLE requires source=INSUFFICIENT_DATA, got source={self.source.value}"
            )
        if self.source == DirectionSource.INSUFFICIENT_DATA and self.direction != SetupDirection.UNAVAILABLE:
            raise ValueError(
                f"source=INSUFFICIENT_DATA requires direction=UNAVAILABLE, got direction={self.direction.value}"
            )
        if self.source == DirectionSource.INTENTIONALLY_NEUTRAL and self.direction != SetupDirection.NEUTRAL:
            raise ValueError(
                f"source=INTENTIONALLY_NEUTRAL requires direction=NEUTRAL, got direction={self.direction.value}"
            )
        if self.source in _EVIDENCE_BACKED_SOURCES and not self.detected:
            raise ValueError(f"source={self.source.value} requires detected=True")

        if not self.detected:
            if self.direction != SetupDirection.UNAVAILABLE or self.source != DirectionSource.INSUFFICIENT_DATA:
                raise ValueError(
                    "detected=False requires direction=UNAVAILABLE and source=INSUFFICIENT_DATA, "
                    f"got direction={self.direction.value}, source={self.source.value}"
                )
