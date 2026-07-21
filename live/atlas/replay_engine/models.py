"""
Replay Engine domain model - Phase N2, Sprint 1. ReplayFrame is the one
type this module defines: an immutable, aligned bundle of the four
objects that already exist to describe one historical bar - MarketState,
RuleEngineOutput, SetupEngineOutput, MarketContext - produced by Market
Engine, Rule Engine, Setup Engine, and Market Context respectively.
ReplayFrame does not compute anything and does not own any of its four
fields' types; it only asserts that, for one bar, these four
already-independently-produced objects describe the same moment.

No cross-field validation is added here. The four fields are opaque,
independently-typed domain objects whose "same bar" identifiers are not
even shaped the same way (MarketState.symbol and MarketContext.symbol are
each a Symbol; RuleEngineOutput.symbol and SetupEngineOutput.symbol are
each a plain str - already differently typed even where they express the
same concept), so a generic equality check across them here would not be
a meaningful invariant to enforce on this type. Establishing alignment is
the caller's responsibility - the same "construction path guarantees the
invariant, the type itself does not re-derive it" posture
atlas.setup_engine.models.SetupEvaluationContext.current already
establishes one layer down. A future build_replay_output_window() (not
this sprint) is the actual construction path that will guarantee
alignment by construction.

Deliberately minimal, per the approved Phase N2 architecture proposal and
its Sprint 1 scope reduction: no ReplaySession here. A stateful or
configuration-wrapper session object is explicitly deferred until a real
consumer needs pause/resume/step/checkpoint behavior.

No strategy output, trade decision, execution state, mutable lifecycle
state, persistence metadata, or API serialization helper belongs here -
ReplayFrame is only an immutable aligned bundle describing one historical
bar, nothing about what a future consumer might do with it.
"""
from dataclasses import dataclass

from atlas.market_context.models import MarketContext
from atlas.market_engine.models import MarketState
from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import SetupEngineOutput


@dataclass(frozen=True)
class ReplayFrame:
    """One historical bar's four already-independently-computed
    descriptions, bundled together unchanged - never re-derived, never
    re-validated, never re-typed."""

    market_state: MarketState
    rule_engine_output: RuleEngineOutput
    setup_engine_output: SetupEngineOutput
    market_context: MarketContext
