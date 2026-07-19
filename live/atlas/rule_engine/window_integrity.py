"""
Sprint 17A (Rule Engine Window Orchestration). Pure integrity validation for a
window of MarketState intended to become a list[RuleEngineOutput] via
atlas.rule_engine.service.build_rule_engine_output_window.

Deliberately instrument-agnostic and calendar-agnostic: this module does NOT
consult atlas.monitoring.is_market_hours_expected or any other session/holiday
awareness, and does NOT reuse atlas.market_engine.service.find_gaps' jittered
tolerance. A Rule Engine output window must represent one strictly contiguous
analytical segment - every consecutive pair of bars must be exactly one
timeframe cadence apart. A gap caused by a weekend, exchange closure, holiday,
or early close is NOT accepted as part of one window, the same as any other
gap; splitting a raw series into contiguous segments is an explicit caller
responsibility (Replay, Dataset Builder, a future live-window builder),
upstream of this module. This was a deliberate architecture decision: making
this module's correctness depend on is_market_hours_expected - itself already
disclosed as not holiday-aware - would let a limitation in an unrelated module
become a correctness bug here, and would tie Rule Engine's window contract to
one instrument's (MNQ-like, CME) calendar. See
docs/market_engine/rule-engine-architecture.md's Interface section.

Every check runs against the window in the order the caller supplied it -
this module never sorts or otherwise corrects its input. Silently re-ordering
or de-duplicating would hide a real caller bug behind output that looks
correct.
"""
from atlas.market_engine.models import MarketState


class WindowIntegrityError(Exception):
    """Base type for every window-contiguity violation raised by
    validate_market_state_window. Catch this specifically to handle "the
    input window violated a precondition" without also swallowing unrelated
    bugs - the same AtlasDomainError-style split atlas.core.errors already
    established, kept local to this module since these are Rule Engine
    window preconditions, not general domain primitives."""


class EmptyWindowError(WindowIntegrityError):
    """Raised when market_state_window is empty - there is no current bar,
    so there is nothing to build a RuleEngineOutput for."""


class MixedSymbolError(WindowIntegrityError):
    """Raised when market_state_window contains MarketState for more than
    one symbol. A window is one series for one instrument."""


class MixedTimeframeError(WindowIntegrityError):
    """Raised when market_state_window contains MarketState for more than
    one timeframe. A window is one series at one cadence."""


class NonMonotonicTimestampError(WindowIntegrityError):
    """Raised when occurred_at does not strictly increase from one bar to
    the next, in the order the caller supplied. Never silently re-sorted -
    see this module's docstring."""


class DuplicateTimestampError(WindowIntegrityError):
    """Raised when two consecutive bars share the same occurred_at."""


class WindowGapError(WindowIntegrityError):
    """Raised when two consecutive bars are not exactly one timeframe
    cadence apart - whether the actual interval is larger (a missing bar,
    a session boundary) or smaller (bars too close together). No tolerance
    is applied; see this module's docstring for why."""


def validate_market_state_window(market_state_window: list[MarketState]) -> None:
    """Pure. Raises the first WindowIntegrityError found, in this order:
    empty window; mixed symbol; mixed timeframe; then, walking consecutive
    pairs in caller-supplied order: duplicate timestamp; non-monotonic
    timestamp; non-cadence gap. Returns None (no exception) when
    market_state_window is a valid, strictly contiguous single-symbol,
    single-timeframe series."""
    if not market_state_window:
        raise EmptyWindowError("market_state_window must not be empty")

    symbols = {state.symbol.ticker for state in market_state_window}
    if len(symbols) > 1:
        raise MixedSymbolError(f"window contains more than one symbol: {sorted(symbols)}")

    timeframes = {state.timeframe for state in market_state_window}
    if len(timeframes) > 1:
        raise MixedTimeframeError(
            f"window contains more than one timeframe: {sorted(tf.value for tf in timeframes)}"
        )

    expected_minutes = market_state_window[0].timeframe.duration_minutes

    for index, (previous, current) in enumerate(zip(market_state_window, market_state_window[1:])):
        previous_at = previous.envelope.occurred_at
        current_at = current.envelope.occurred_at

        if current_at == previous_at:
            raise DuplicateTimestampError(
                f"duplicate occurred_at at index {index + 1}: {current_at.isoformat()}"
            )
        if current_at < previous_at:
            raise NonMonotonicTimestampError(
                f"occurred_at is not strictly increasing at index {index + 1}: "
                f"{previous_at.isoformat()} followed by {current_at.isoformat()}"
            )

        actual_minutes = (current_at - previous_at).total_seconds() / 60
        if actual_minutes != expected_minutes:
            raise WindowGapError(
                f"bars are not contiguous at index {index + 1}: expected exactly "
                f"{expected_minutes} minutes between {previous_at.isoformat()} and "
                f"{current_at.isoformat()}, got {actual_minutes} minutes"
            )
