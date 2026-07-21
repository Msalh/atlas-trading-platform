"""
Strategy Engine plugin contract - Phase N3, Sprint 1. StrategyPlugin is
the one Protocol this module defines: the interface every deterministic
strategy plugin must satisfy.

Protocol, not ABC: this codebase has zero abc.ABC/abstractmethod usage
anywhere (grepped) - its one existing "family of interchangeable
implementations conforming to one interface" pattern is
atlas.market_engine.ports.MarketStateRepository, a Protocol. Rule Engine's
and Setup Engine's own "plugin" shapes (FactRegistration/SetupRegistration)
are a different, deliberately closed thing - a static, in-package
Callable registry, explicitly NOT a pluggable API by that module's own
docstring. Strategy Engine is the pluggable case, so it follows
MarketStateRepository's precedent, not Rule/Setup Engine's.

evaluate() takes exactly ONE ReplayFrame, not a bounded window/sequence -
the same "single-bar first, widen only once a real need is demonstrated"
discipline every other evaluator in this codebase already follows (Rule
Engine's own single_bar_adapter default; Setup Engine's registry defaults
required_history to 1, only raised once a specific setup's real logic
needed more). No concrete strategy exists yet (Sprint 1's scope
deliberately excludes one) to justify windowing - a future strategy that
genuinely needs trailing history is the trigger to widen this contract,
not a guess made speculatively here.

Recomputing MarketState, Rule Engine facts, Setup Engine setups, or Market
Context from inside a plugin is never permitted - a conforming plugin
reads ReplayFrame's own already-computed fields only, never re-derives
them. No plugin may depend on an LLM.
"""
from typing import Protocol

from atlas.replay_engine.models import ReplayFrame
from atlas.strategy_engine.models import StrategyDecision


class StrategyPlugin(Protocol):
    """A conforming implementation is any object exposing this shape -
    structural typing, the same duck-typed conformance
    MarketStateRepository's own implementations (InMemoryMarketStateRepository,
    a future Postgres one) already rely on. No registration mechanism, no
    base class to inherit from, and no import of atlas.replay_engine.service
    is required to conform - a plugin depends only on
    atlas.replay_engine.models.ReplayFrame and atlas.strategy_engine.models.StrategyDecision."""

    @property
    def strategy_id(self) -> str:
        """Stable identity - never changes across versions of the same
        strategy. The same identity/version split
        atlas.rule_engine.models.FactDefinition already established: two
        independent things, free to change on different schedules."""
        ...

    @property
    def strategy_version(self) -> str:
        """This specific version's tunable decision logic/parameters -
        bumped whenever those change, independent of strategy_id."""
        ...

    def evaluate(self, frame: ReplayFrame) -> StrategyDecision:
        """Pure. Given one ReplayFrame, returns exactly one
        StrategyDecision - never raises for an ordinary "no signal" or
        "rejected" outcome (those are expected StrategyDecision values,
        not exceptions); never mutates frame; performs no I/O, reads no
        clock, and depends on no state from any prior call."""
        ...
