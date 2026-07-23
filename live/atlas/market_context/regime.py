"""
Volatility regime classification - Phase N1, Sprint 3. classify_volatility_regime()
computes VolatilityClassification from a MarketState window's `atr` field alone.

Deliberately independent from every other Market Context concern: this
module does not import session.py, DriftStatus, SessionProgress,
ContextQuality, or fingerprint, and never will be asked to - its
responsibility is exactly:

    MarketState window -> ATR analysis -> VolatilityClassification

nothing more. A future service.py (not part of this sprint) is what
combines this with session.py's output; regime.py itself has no knowledge
that session.py exists.

Window validation is reused as-is from
atlas.rule_engine.window_integrity.validate_market_state_window() - the
one permitted Rule Engine import for this package (approved architecture
exception): it is a pure, side-effect-free contiguity check with no
knowledge of Rule Engine facts, registries, or definitions, and duplicating
it here would only risk a second, independently-drifting implementation of
the same check.

--- The percentile-rank algorithm, precisely ---

Given a window of up to `lookback_bars` trailing bars (the current bar is
the window's own last element, included as one of the ranked members - not
excluded and compared from outside), the percentile rank of the current
bar is:

    rank = (count of bars in the window whose atr <= current bar's atr) / (bars in the window)

This is a standard percentile-rank definition, not look-ahead: every bar in
the window has occurred_at <= the current bar's occurred_at (guaranteed by
the caller supplying a window that ends at the bar being classified - this
function never fetches data itself, so "no bar from the future" is a
property of what it's given, not something it re-checks). Ties resolve
toward the higher regime: a bar tied with everything else in its window
(rank = 1.0) reads as EXPANDED, not NORMAL - a direct, deliberate
consequence of using "<=" rather than a strict "<" comparison, most visible
with constant ATR data (see the tests).

Regime buckets, using RegimeClassifierParams.compressed_percentile/
expanded_percentile as plain fractions (25 -> 0.25, 75 -> 0.75):

    rank <= compressed_fraction  -> COMPRESSED
    rank >= expanded_fraction    -> EXPANDED
    otherwise                    -> NORMAL

Fewer than `min_bars_required` bars available (the caller-supplied window
is genuinely too short) -> VolatilityRegime.INSUFFICIENT_HISTORY,
atr_percentile_rank=None, lookback_bars_used=however many bars were
actually available. Never a silent fallback to NORMAL - the same "an
honest unknown beats a guessed default" posture Rule Engine's
InsufficientData already established.

Pure throughout: no I/O, no caching, no randomness, no fitted parameter -
every number above is a plain count/ratio computed directly from the
window's own `atr` values.
"""
from atlas.market_context.definitions import REGIME_CLASSIFIER_V1, RegimeClassifierDefinition
from atlas.market_context.models import VolatilityClassification, VolatilityRegime
from atlas.market_engine.models import MarketState
from atlas.rule_engine.window_integrity import validate_market_state_window


def _effective_window(window: list[MarketState], lookback_bars: int) -> list[MarketState]:
    """The last `lookback_bars` bars of `window`, or the whole window if it
    has fewer than that. Never more than `lookback_bars` bars, regardless
    of how many the caller supplied - "lookback_bars" names how far back to
    look, not a lower bound on what the caller happens to provide."""
    if len(window) <= lookback_bars:
        return window
    return window[-lookback_bars:]


def _percentile_rank(effective_window: list[MarketState]) -> float:
    current_atr = effective_window[-1].atr
    at_or_below = sum(1 for state in effective_window if state.atr <= current_atr)
    return at_or_below / len(effective_window)


def _bucket(rank: float, classifier: RegimeClassifierDefinition) -> VolatilityRegime:
    compressed_fraction = classifier.params.compressed_percentile / 100
    expanded_fraction = classifier.params.expanded_percentile / 100
    if rank <= compressed_fraction:
        return VolatilityRegime.COMPRESSED
    if rank >= expanded_fraction:
        return VolatilityRegime.EXPANDED
    return VolatilityRegime.NORMAL


def classify_volatility_regime(
    window: list[MarketState],
    classifier: RegimeClassifierDefinition = REGIME_CLASSIFIER_V1,
) -> VolatilityClassification:
    """window must be ascending, current bar last, and pass
    validate_market_state_window() (single symbol, single timeframe,
    strictly contiguous, no gaps) - any WindowIntegrityError subclass
    propagates uncaught to the caller, exactly as Rule Engine's own
    orchestration functions already let it. Every bar's `atr` must be set
    (non-None) - this function does not itself filter out or tolerate a
    None atr value; a caller supplying a window with unset ATR (e.g. the
    first few bars of a brand-new series, before Pine's own ATR indicator
    warms up) will raise a TypeError on comparison, not silently skip
    those bars."""
    validate_market_state_window(window)

    available_bars = len(window)
    if available_bars < classifier.params.min_bars_required:
        return VolatilityClassification(
            regime=VolatilityRegime.INSUFFICIENT_HISTORY,
            atr_percentile_rank=None,
            lookback_bars_used=available_bars,
        )

    effective_window = _effective_window(window, classifier.params.lookback_bars)
    rank = _percentile_rank(effective_window)
    regime = _bucket(rank, classifier)

    return VolatilityClassification(
        regime=regime,
        atr_percentile_rank=rank,
        lookback_bars_used=len(effective_window),
    )
