"""
Replay Engine domain model - Phase N2, Sprint 1; widened Sprint 5 (Setup
Interpretation integration architecture review) to a fifth field.
ReplayFrame is the one type this module defines: an immutable, aligned
bundle of the five objects that already exist to describe one historical
bar - MarketState, RuleEngineOutput, SetupEngineOutput, MarketContext,
and (as of Sprint 5) the dense tuple of SetupInterpretation entries for
that same bar - produced by Market Engine, Rule Engine, Setup Engine,
Market Context, and Setup Interpretation respectively. ReplayFrame does
not compute anything and does not own any of its five fields' types; it
only asserts that, for one bar, these five already-independently-produced
objects describe the same moment.

No cross-field validation is added here. The five fields are opaque,
independently-typed domain objects whose "same bar" identifiers are not
even shaped the same way (MarketState.symbol and MarketContext.symbol are
each a Symbol; RuleEngineOutput.symbol and SetupEngineOutput.symbol are
each a plain str - already differently typed even where they express the
same concept; SetupInterpretation carries no symbol/timeframe at all, by
its own package's design - see atlas.setup_interpretation.models's own
docstring), so a generic equality check across them here would not be a
meaningful invariant to enforce on this type. Establishing alignment is
the caller's responsibility - the same "construction path guarantees the
invariant, the type itself does not re-derive it" posture
atlas.setup_engine.models.SetupEvaluationContext.current already
establishes one layer down. build_replay_output_window() (Sprint 2,
extended Sprint 5) is the actual construction path that guarantees
alignment by construction.

setup_interpretations is required, never Optional and never defaulted -
the same dense-tuple discipline atlas.setup_interpretation.service
.interpret_setups() itself already enforces one layer down (one entry per
SetupOutcome in setup_engine_output.setups, never a shorter or omitted
list). No ReplayFrame may exist with a missing or partial fifth field.

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
from atlas.setup_interpretation.models import SetupInterpretation


@dataclass(frozen=True)
class ReplayFrame:
    """One historical bar's five already-independently-computed
    descriptions, bundled together unchanged - never re-derived, never
    re-validated, never re-typed."""

    market_state: MarketState
    rule_engine_output: RuleEngineOutput
    setup_engine_output: SetupEngineOutput
    market_context: MarketContext
    setup_interpretations: tuple[SetupInterpretation, ...]
