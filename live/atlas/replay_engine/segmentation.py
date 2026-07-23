"""
Replay Engine segmentation - Phase N2, Sprint 1. segment_replay_window()
is a thin, explicit-contract wrapper around the one segmentation function
this project already has: atlas.profiling.service.segment_by_gap. No gap
detection logic is duplicated here - this module exists only to give
Replay Engine's own future callers an interface named and documented for
what THEY need it for (splitting a bounded historical MarketState series
into maximal contiguous runs before any window-based composition - Rule
Engine, Setup Engine, or Market Context - is attempted against it), not
to reimplement or extend segment_by_gap's own already-tested behavior.

Same contract as segment_by_gap, restated here for a Replay Engine caller
who should not need to go read atlas.profiling.service's own docstring to
know what this returns:

    - Pure, deterministic, side-effect free: no logging, no database, no
      environment access, no wall-clock access.
    - Gaps (weekends, holidays, exchange maintenance, any other missing
      interval) become segment boundaries, never exceptions.
    - A duplicate or non-monotonic occurred_at, or a mix of symbols/
      timeframes, still raises atlas.profiling.models.ProfilingInputError
      - propagated uncaught, not re-defined or aliased here, the same
      "the type a caller needs to catch lives with the function that
      raises it" posture atlas.market_context.regime already established
      for atlas.rule_engine.window_integrity.WindowIntegrityError one
      layer down.
    - Chronological order is preserved within and across segments; the
      input list itself is never mutated (segment_by_gap only ever reads
      from its input and appends the same object references into new
      lists - see its own implementation).
    - No interpolation or fabricated bar is ever produced - a gap is
      represented as an absence (a segment boundary), never filled in.

Composing Rule Engine, Setup Engine, or Market Context output over these
segments is explicitly out of scope for this sprint - see a future
build_replay_output_window(), not implemented here.
"""
from atlas.market_engine.models import MarketState
from atlas.profiling.service import segment_by_gap


def segment_replay_window(market_state_window: list[MarketState]) -> list[list[MarketState]]:
    """Splits `market_state_window` into maximal chronologically-contiguous
    segments - see this module's docstring for the full contract. A pure
    pass-through to atlas.profiling.service.segment_by_gap; this function
    adds no behavior of its own beyond naming and documenting that
    contract for a Replay Engine caller."""
    return segment_by_gap(market_state_window)
