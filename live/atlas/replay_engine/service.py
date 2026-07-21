"""
Replay Engine composition core - Phase N2. build_replay_output_window()
(Sprint 2) is the pure synchronous core: given a single, already-contiguous
window of MarketState (Sprint 1's segment_replay_window is the caller's own
responsibility for producing one - this function does not re-segment or
re-validate contiguity itself), it composes Rule Engine, Setup Engine, and
Market Context's existing public functions - unchanged, unduplicated - into
one ReplayFrame per input bar. replay() (Sprint 3) is the thin async
orchestration boundary on top of it - see that function's own docstring
below for its contract.

Pure and synchronous throughout: no repository, no async, no database, no
event bus, no logging, no wall-clock read, no randomness, no global mutable
state, no caching. Given the same market_state_window (and the same
calendar/classifier), this function always returns the same list[ReplayFrame] -
the same "same input, same output" guarantee every other windowed composer in
this codebase (build_rule_engine_output_window, build_setup_engine_output_window,
build_market_context) already provides one layer down.

--- Composition, not reimplementation ---

Three existing functions do all the real work, exactly as already certified:

    build_rule_engine_output_window(market_state_window)  -> list[RuleEngineOutput]
    build_setup_engine_output_window(rule_engine_outputs)  -> list[SetupEngineOutput]
    build_market_context(...)  (called once per position)  -> MarketContext

Nothing in this module recomputes a fact, a setup, a session phase, or a
volatility regime - it only calls these three, in this order, and zips their
outputs into ReplayFrame. If market_state_window is not actually contiguous,
build_rule_engine_output_window's own validate_market_state_window call raises
a WindowIntegrityError - propagated uncaught, exactly as it already would for
any other caller; this module adds no try/except around it (a caller violating
Sprint 1's "pass one already-segmented window" contract is a programming
error, not a condition to hide).

--- Market Context's per-position window ---

Unlike Rule/Setup Engine (which have a registry-driven required_history()
depth), Market Context has no such registry - REGIME_CLASSIFIER_V1's own
`lookback_bars` is the only meaningful trailing-window bound. For position i,
this module passes market_state_window[max(0, i - lookback_bars + 1) : i + 1]
to build_market_context - the same truncate-to-bounded-trailing-window shape
build_rule_engine_output_window/build_setup_engine_output_window already use
with their own registries' required_history(). Passing the entire growing
prefix instead (unbounded) would make every position's call re-scan an
ever-larger window inside classify_volatility_regime's own
validate_market_state_window - O(n^2) for no benefit, since
classify_volatility_regime already caps itself to lookback_bars internally.
This is a windowing/bounding decision only, not a change to Market Context's
own algorithm: a truncated suffix of an already-contiguous window is itself
still contiguous, so build_market_context's own INSUFFICIENT_HISTORY/
ContextQuality.UNKNOWN behavior for early, not-yet-warmed-up positions is
unaffected - identical to what a caller passing that same bounded window
directly would already get.

upstream_session_name/upstream_is_rth per position come directly from that
position's own MarketState.session_name/is_rth fields (whatever an upstream
adapter already tagged the bar with) - never invented, never left as a fixed
constant across the whole window.

--- Alignment ---

ReplayFrame[i] must describe exactly the same historical bar across all four
of its fields. This is guaranteed by construction (each of the three composed
functions already promises "exactly one output per input, same order," and
market_context is built directly from market_state_window[i]'s own
symbol/timeframe/occurred_at) - _assert_aligned re-checks it anyway, the same
defense-in-depth posture atlas.profiling.service.segment_by_gap already takes
toward invariants a caller "should" already guarantee (re-checking symbol/
timeframe even though its own docstring says the input is assumed already
filtered). A violation here would mean one of the three composed functions'
own contract broke - a real bug, not an expected condition - so it is raised,
never silently truncated, padded, or fabricated around.
"""
from collections.abc import AsyncIterator
from datetime import datetime

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import CME_RTH_V1, REGIME_CLASSIFIER_V1, RegimeClassifierDefinition, SessionCalendarDefinition
from atlas.market_context.models import MarketContext
from atlas.market_context.service import build_market_context
from atlas.market_engine.models import MarketState
from atlas.market_engine.ports import MarketStateRepository
from atlas.market_engine.service import replay_market_state
from atlas.replay_engine.models import ReplayFrame
from atlas.replay_engine.segmentation import segment_replay_window
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.models import SetupEngineOutput
from atlas.setup_engine.service import build_setup_engine_output_window


class ReplayAlignmentError(Exception):
    """Base type for every ReplayFrame alignment violation raised by
    build_replay_output_window. Catch this specifically to handle "the
    composed outputs did not line up" without also swallowing an unrelated
    bug - the same WindowIntegrityError-style split
    atlas.rule_engine.window_integrity already established."""


class ReplayLengthMismatchError(ReplayAlignmentError):
    """Raised when the derived RuleEngineOutput/SetupEngineOutput/
    MarketContext lists do not each have exactly one entry per input
    MarketState."""


class ReplayOccurredAtMismatchError(ReplayAlignmentError):
    """Raised when position i's MarketState/RuleEngineOutput/SetupEngineOutput/
    MarketContext do not all describe the same occurred_at. A positional
    swap (an "unexpected ordering issue") is a special case of this: any
    departure from the expected per-position identity, not only a value
    that matches nothing at all in the window, is caught by the same
    per-position equality check."""


def _market_context_for_position(
    market_state_window: list[MarketState], index: int,
    calendar: SessionCalendarDefinition, classifier: RegimeClassifierDefinition,
) -> MarketContext:
    current = market_state_window[index]
    depth = classifier.params.lookback_bars
    window = market_state_window[max(0, index - depth + 1) : index + 1]
    upstream_session_name = current.session_name.value if current.session_name is not None else None
    return build_market_context(
        symbol=current.symbol,
        timeframe=current.timeframe,
        occurred_at=current.envelope.occurred_at,
        window=window,
        upstream_session_name=upstream_session_name,
        upstream_is_rth=current.is_rth,
        calendar=calendar,
        classifier=classifier,
    )


def _assert_aligned(
    market_state_window: list[MarketState],
    rule_engine_outputs: list[RuleEngineOutput],
    setup_engine_outputs: list[SetupEngineOutput],
    market_contexts: list[MarketContext],
) -> None:
    expected_length = len(market_state_window)
    lengths = {
        "rule_engine_outputs": len(rule_engine_outputs),
        "setup_engine_outputs": len(setup_engine_outputs),
        "market_contexts": len(market_contexts),
    }
    mismatched = {name: n for name, n in lengths.items() if n != expected_length}
    if mismatched:
        raise ReplayLengthMismatchError(
            f"expected {expected_length} entries (one per input MarketState), got {mismatched}"
        )

    for index, state in enumerate(market_state_window):
        expected_at = state.envelope.occurred_at
        expected_iso = expected_at.isoformat()

        if rule_engine_outputs[index].occurred_at != expected_iso:
            raise ReplayOccurredAtMismatchError(
                f"position {index}: rule_engine_output.occurred_at="
                f"{rule_engine_outputs[index].occurred_at!r} does not match "
                f"market_state.envelope.occurred_at={expected_iso!r}"
            )
        if setup_engine_outputs[index].occurred_at != expected_iso:
            raise ReplayOccurredAtMismatchError(
                f"position {index}: setup_engine_output.occurred_at="
                f"{setup_engine_outputs[index].occurred_at!r} does not match "
                f"market_state.envelope.occurred_at={expected_iso!r}"
            )
        if market_contexts[index].occurred_at != expected_at:
            raise ReplayOccurredAtMismatchError(
                f"position {index}: market_context.occurred_at="
                f"{market_contexts[index].occurred_at!r} does not match "
                f"market_state.envelope.occurred_at={expected_at!r}"
            )


def build_replay_output_window(
    market_state_window: list[MarketState],
    calendar: SessionCalendarDefinition = CME_RTH_V1,
    classifier: RegimeClassifierDefinition = REGIME_CLASSIFIER_V1,
) -> list[ReplayFrame]:
    """Pure. `market_state_window` must already be one contiguous segment
    (Sprint 1's segment_replay_window, not this function, is where that
    comes from) - not re-validated here beyond what
    build_rule_engine_output_window already checks internally. Returns
    exactly one ReplayFrame per input MarketState, in the same order -
    never a shorter or reordered list; an empty input produces an empty
    output, the same "no position to build" posture
    build_setup_engine_output_window already uses one layer down."""
    if not market_state_window:
        return []

    rule_engine_outputs = build_rule_engine_output_window(market_state_window)
    setup_engine_outputs = build_setup_engine_output_window(rule_engine_outputs)
    market_contexts = [
        _market_context_for_position(market_state_window, index, calendar, classifier)
        for index in range(len(market_state_window))
    ]

    _assert_aligned(market_state_window, rule_engine_outputs, setup_engine_outputs, market_contexts)

    return [
        ReplayFrame(
            market_state=market_state_window[index],
            rule_engine_output=rule_engine_outputs[index],
            setup_engine_output=setup_engine_outputs[index],
            market_context=market_contexts[index],
        )
        for index in range(len(market_state_window))
    ]


async def replay(
    symbol: Symbol,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    repository: MarketStateRepository,
    limit: int = 10000,
    calendar: SessionCalendarDefinition = CME_RTH_V1,
    classifier: RegimeClassifierDefinition = REGIME_CLASSIFIER_V1,
) -> AsyncIterator[ReplayFrame]:
    """Phase N2, Sprint 3. The thin async orchestration boundary on top of
    build_replay_output_window: fetch, segment, compose per segment, yield -
    in that order, nothing more. This is the ONE place in Replay Engine
    that touches a repository or awaits anything.

    Fetches via atlas.market_engine.service.replay_market_state (unchanged,
    Sprint 10) - a single bounded repository.get_range call under the hood,
    consumed here into one list because segment_replay_window's own
    contract (Sprint 1, unchanged) is synchronous over list[MarketState],
    not an async stream; this is the only materialization this function
    performs; no ReplayFrame is built, and no segment is processed, before
    it completes.

    Segments via atlas.replay_engine.segmentation.segment_replay_window
    (unchanged, Sprint 1), then calls build_replay_output_window
    (unchanged, Sprint 2) once per segment, in the order segmentation
    returned them - never combining two segments' MarketState into one
    window, so a trailing window inside Market Context/Rule Engine/Setup
    Engine composition can never cross a segment boundary; each segment
    starts its own composition completely fresh, with no memory of any
    earlier segment. Because segments and their own internal frames are
    both already chronologically ordered, yielding segment-by-segment,
    frame-by-frame reproduces strict global chronological order without
    this function itself needing to sort anything.

    No ReplayFrame is ever constructed here directly - every one yielded
    came out of build_replay_output_window unchanged.

    An empty repository result (no bars in [start, end]) yields nothing -
    zero segments to iterate, not an error, the same "empty in, empty out"
    posture segment_replay_window/build_replay_output_window already both
    have. A repository failure (the awaited replay_market_state/get_range
    call raising) or a composition failure (build_replay_output_window
    raising, including the alignment errors above) both propagate
    completely unchanged - this function adds no try/except anywhere; a
    real repository or composition bug must surface as itself, never be
    hidden or reinterpreted here.

    Cancellation/early termination relies entirely on the standard async
    generator protocol (a consumer's `break` from `async for`, or garbage
    collection, closes this generator the normal Python way) - no custom
    lifecycle state, no ReplaySession, is introduced to support it."""
    states = [state async for state in replay_market_state(symbol, timeframe, start, end, limit, repository)]
    for segment in segment_replay_window(states):
        for frame in build_replay_output_window(segment, calendar, classifier):
            yield frame
