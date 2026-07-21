"""
Strategy Engine domain model - Phase N3, Sprint 1. StrategyDirection,
StrategyDisposition, and StrategyDecision are the only types this module
defines - the immutable, auditable evaluation result a strategy plugin
produces from one ReplayFrame. No behavior lives here beyond the
structural invariants below; a plugin's actual decision LOGIC belongs to
the plugin itself (a future Sprint), never to this model.

--- Why disposition, not a boolean ---

should_trade: bool would collapse three genuinely different situations
into one bit: "a recognizable setup fired and passed acceptance"
(CANDIDATE), "a recognizable setup fired but failed acceptance"
(REJECTED), and "nothing relevant was even present to evaluate"
(NO_SIGNAL). REJECTED and NO_SIGNAL both mean "no trade," but they are not
the same fact, and collapsing them would hide a real distinction an
auditor needs: did this strategy see something and say no, or did it see
nothing at all?

--- Why reason_codes/setup_ids are open string tuples, not closed enums ---

atlas.research.setup_profiling.models.TerminationReason and
atlas.live_view.models.LiveTerminationReason are this codebase's existing
precedent for a machine-readable reason catalog - but both are CLOSED,
framework-owned catalogs describing a fixed, small set of situations this
package itself defines. A strategy plugin's reason codes are the opposite
shape: each plugin owns its own vocabulary (a momentum strategy's reasons
are not a mean-reversion strategy's reasons), and Strategy Engine cannot
know that vocabulary in advance without becoming a registry of every
strategy that will ever exist. The precedent for THIS shape is
atlas.rule_engine.models.RuleEngineOutput.facts: dict[str, FactOutcome] -
a closed, typed CONTAINER around an open set of caller-defined string
identifiers. reason_codes/setup_ids follow that pattern: a tuple (ordered,
deterministic - never a set) of short, stable, machine-readable tokens
(e.g. "insufficient_volume_confirmation"), never a free-text sentence -
satisfying "machine-readable and deterministic" without requiring a
closed enum no plugin outside this package could ever extend.

--- Why confidence is deliberately narrow ---

Optional[float], bounds-checked to [0.0, 1.0] when present, with a
contract enforced only by documentation (not computable/checkable at
construction time): it must be a deterministic function of the strategy's
own disclosed evidence, never a fabricated or learned probability. This
mirrors atlas.setup_engine.models.Severity's own explicit stance
("deliberately NOT a float in [0, 1]... an enum cannot be... mistaken for
a statistical score") - confidence exists here as an explicit *escape
hatch* for a plugin that genuinely has a disclosed deterministic scalar to
report, not an invitation to invent one. A plugin with nothing real to
report here must leave it None, not fill it with a guess.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from atlas.core.primitives import Price


class StrategyDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class StrategyDisposition(str, Enum):
    """CANDIDATE: a recognizable setup was evaluated and passed this
    strategy's acceptance criteria - direction is LONG or SHORT.
    REJECTED: a recognizable setup was evaluated but failed
    strategy-specific acceptance criteria - direction is FLAT.
    NO_SIGNAL: no relevant strategy trigger existed at all - nothing was
    even evaluated - direction is FLAT."""

    CANDIDATE = "candidate"
    REJECTED = "rejected"
    NO_SIGNAL = "no_signal"


_DIRECTIONAL = (StrategyDirection.LONG, StrategyDirection.SHORT)


@dataclass(frozen=True)
class StrategyDecision:
    """One strategy plugin's evaluation of one ReplayFrame - an evaluation
    result, never an order. No broker order ID, fill price, PnL, mutable
    lifecycle state, repository metadata, or API transport field belongs
    here; those all describe what happens to a decision AFTER it is made,
    which is not this package's concern.

    occurred_at/context_fingerprint are copied from the originating
    ReplayFrame's own market_context - never recomputed - the same
    "composition only, never re-derive what an upstream layer already
    computed" discipline every layer of this pipeline already follows.
    symbol/timeframe are deliberately NOT carried here: they are
    recoverable by joining back to the originating ReplayFrame at the same
    occurred_at, the same (symbol, timeframe, occurred_at)-join posture
    atlas.market_context.MarketContext already established relative to
    MarketState - not a second, independently-set copy of an identity
    this object doesn't itself need to act on.

    Invariants (unconstructable invalid states, not merely documented
    ones - the same posture atlas.setup_engine.models.SetupResult already
    established for its own detected/severity pairing):

        - direction in (LONG, SHORT) if and only if disposition == CANDIDATE.
        - CANDIDATE requires at least one setup_id.
        - REJECTED requires at least one setup_id (something recognizable
          was evaluated) and at least one reason_code (why it failed).
        - NO_SIGNAL requires setup_ids to be empty (nothing relevant was
          found to evaluate at all).
        - confidence, if present, is within [0.0, 1.0]."""

    occurred_at: datetime
    strategy_id: str
    strategy_version: str
    disposition: StrategyDisposition
    direction: StrategyDirection
    setup_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    context_fingerprint: str
    invalidation: Optional[Price] = None
    stop: Optional[Price] = None
    target: Optional[Price] = None
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.strategy_id.strip():
            raise ValueError("strategy_id must not be blank")
        if not self.strategy_version or not self.strategy_version.strip():
            raise ValueError("strategy_version must not be blank")
        if not self.context_fingerprint or not self.context_fingerprint.strip():
            raise ValueError("context_fingerprint must not be blank")

        is_directional = self.direction in _DIRECTIONAL
        is_candidate = self.disposition == StrategyDisposition.CANDIDATE
        if is_directional and not is_candidate:
            raise ValueError(
                f"direction={self.direction.value} is only valid when disposition=CANDIDATE, "
                f"got disposition={self.disposition.value}"
            )
        if is_candidate and not is_directional:
            raise ValueError(
                f"disposition=CANDIDATE requires direction to be LONG or SHORT, got {self.direction.value}"
            )

        if is_candidate and not self.setup_ids:
            raise ValueError("disposition=CANDIDATE requires at least one setup_id")

        if self.disposition == StrategyDisposition.REJECTED:
            if not self.setup_ids:
                raise ValueError(
                    "disposition=REJECTED requires at least one setup_id "
                    "(a recognizable setup must have been evaluated)"
                )
            if not self.reason_codes:
                raise ValueError("disposition=REJECTED requires at least one reason_code")

        if self.disposition == StrategyDisposition.NO_SIGNAL and self.setup_ids:
            raise ValueError(
                "disposition=NO_SIGNAL requires setup_ids to be empty "
                "(no relevant strategy trigger existed)"
            )

        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be within [0.0, 1.0] if present, got {self.confidence!r}")
