"""
Phase N4 Sprint 8. Package-local supporting types - never a new blueprint
entity (the roadmap's own Sprint 8 text: "Data models introduced: none
new"), mirroring atlas.research.ranking.models.RankingPolicy's own
precedent of a package-owned type referenced only by ID/field from the
shared model. ResearchDecision is the return value of one
ResearchStrategyPlugin.decide() call; a full decision sequence
(tuple[ResearchDecision, ...], one per input ReplayFrame) is what
execute_realization() produces and what gets serialized to the file
Evidence.decision_sequence_path (Sprint 1, already frozen) points at.

Deliberately carries no price/stop/target: this package computes zero
statistics, and Statistics's own Sprint 8 extension computes realized
outcomes by matching this sequence against the original ReplayFrame price
data, not from fields duplicated here - mirroring how
atlas.strategy_engine.models.StrategyDecision doesn't carry realized P&L
either.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ResearchDispositionKind(str, Enum):
    """Closed set of what a ResearchStrategyPlugin may decide at one bar."""

    NO_ACTION = "no_action"
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT = "exit"


@dataclass(frozen=True)
class ResearchDecision:
    """occurred_at/context_fingerprint are copied from the originating
    ReplayFrame's own market_context - never recomputed - the same
    composition-only discipline
    atlas.strategy_engine.models.StrategyDecision already established
    relative to ReplayFrame."""

    occurred_at: datetime
    realization_id: str
    disposition: ResearchDispositionKind
    reason_codes: tuple[str, ...]
    context_fingerprint: str
