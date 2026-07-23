"""
Phase N4 Sprint 8. ResearchStrategyPlugin - the Research Engine's own
decision-per-frame contract, structurally distinct from
atlas.strategy_engine.ports.StrategyPlugin per Research Engine Design
Principles VIII.4 ("research objects are never structurally interchangeable
with production objects, even when their shapes rhyme"). Deliberately
different property/method names (realization_id/realization_version/
decide()), not merely a different return-type annotation: @runtime_checkable
Protocol isinstance() checks only verify name/signature presence, never
return-type annotations - a plugin sharing StrategyPlugin's own method
names (strategy_id/strategy_version/evaluate()) would satisfy
isinstance(x, StrategyPlugin) regardless of what it actually returns. See
test_research_backtesting.py's own structural-separation test for the
mechanical proof, both directions.

decide() takes exactly ONE ReplayFrame, mirroring StrategyPlugin.evaluate()'s
own "single-bar first" discipline. A concrete implementation may hold its
own internal state across sequential calls on the same instance (e.g. a
small bounded rolling buffer) as long as it depends on no *external* state
(no I/O, no clock, no config, no environment); ResearchStrategyFactory
constructs one fresh instance per execute_realization() call, so this state
is bounded to a single run and never leaks across runs - see factory.py's
own purity contract.
"""
from typing import Protocol, runtime_checkable

from atlas.research.backtesting.models import ResearchDecision
from atlas.research.replay_bridge import ReplayFrame


@runtime_checkable
class ResearchStrategyPlugin(Protocol):
    """A conforming implementation is any object exposing this shape -
    structural typing, no registration mechanism, no base class."""

    @property
    def realization_id(self) -> str:
        """Which Realization this plugin instance was constructed for."""
        ...

    @property
    def realization_version(self) -> str:
        """Realization.version at construction time - also the version
        half of the (template_kind, version) pair the factory dispatched
        on to select this plugin's own class."""
        ...

    def decide(self, frame: ReplayFrame) -> ResearchDecision:
        """Given one ReplayFrame, returns exactly one ResearchDecision -
        never raises for an ordinary "no action" outcome (that's an
        expected ResearchDecision value, not an exception); never mutates
        frame; performs no I/O and reads no clock."""
        ...
