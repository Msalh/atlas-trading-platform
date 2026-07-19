"""
Sprint 11 introduced volume_spike/displacement; Sprint 12 retrofitted both to
take a FactDefinition and added rejection; Sprint 13 adds trend_5m,
liquidity_sweep, and reclaim - see docs/market_engine/rule-fact-inventory.md
for why these six specifically and why trend_1m/trend_15m/trend_1h and the
session-status facts remain deferred.

Every function here remains pure and synchronous - no I/O, no repository, no
async. volume_spike/displacement/rejection take a single MarketState (no
history needed); trend_5m/liquidity_sweep/reclaim take a WINDOW -
list[MarketState], chronologically ASCENDING, current/latest bar LAST - the
same ordering convention atlas.market_engine.service's get_range and
replay_market_state already use, reused here rather than inventing a second
convention. Nothing here can behave differently depending on how the window's
MarketStates arrived (live get_history vs. Sprint 10's replay_market_state) or
on anything other than the definition each function is explicitly given.
"""
from atlas.market_engine.models import MarketState
from atlas.rule_engine.models import FactDefinition, FactOutcome, FactResult, InsufficientData

# Shared by rejection, liquidity_sweep, and reclaim - all three evaluate
# against the same four reference levels this MarketState carries.
_REFERENCE_LEVELS = (
    ("previous_day_high", "high"),
    ("overnight_high", "high"),
    ("previous_day_low", "low"),
    ("overnight_low", "low"),
)


def evaluate_volume_spike(state: MarketState, definition: FactDefinition) -> FactOutcome:
    """volume_spike = volume_ratio > definition.params["threshold"]. No
    history window required - a pure threshold on a value already present on
    the current MarketState (the Fact Inventory's simplest fact: volume_ratio
    is sent raw by TradingView, not a placeholder). Behavior-preserving
    retrofit of Sprint 11's version - same threshold value (1.5, via
    DEFAULT_VOLUME_SPIKE_DEFINITION), same evidence shape, only the source of
    the threshold changed."""
    if state.volume_ratio is None:
        return InsufficientData(
            fact_name="volume_spike",
            definition_version=definition.version,
            reason="volume_ratio is not present on this MarketState",
        )
    threshold = definition.params["threshold"]
    return FactResult(
        fact_name="volume_spike",
        definition_version=definition.version,
        value=state.volume_ratio > threshold,
        evidence={"volume_ratio": state.volume_ratio, "threshold": threshold},
    )


def evaluate_displacement(state: MarketState, definition: FactDefinition) -> FactOutcome:
    """displacement = (high - low) / atr > definition.params["threshold"] -
    the current bar's range relative to its ATR. Range (high - low), not body
    (open - close), remains this fact's definition (Sprint 11's disclosed
    choice, unchanged). Behavior-preserving retrofit - same threshold value
    (1.5), same evidence shape, only the source of the threshold changed."""
    if state.atr is None:
        return InsufficientData(
            fact_name="displacement", definition_version=definition.version,
            reason="atr is not present on this MarketState",
        )
    if state.high is None or state.low is None:
        return InsufficientData(
            fact_name="displacement", definition_version=definition.version,
            reason="high/low is not present on this MarketState",
        )
    if state.atr == 0:
        return InsufficientData(
            fact_name="displacement", definition_version=definition.version,
            reason="atr is zero - a range/atr ratio is undefined",
        )

    threshold = definition.params["threshold"]
    ratio = (state.high.value - state.low.value) / state.atr
    return FactResult(
        fact_name="displacement",
        definition_version=definition.version,
        value=ratio > threshold,
        evidence={"range_atr_ratio": ratio, "threshold": threshold},
    )


def evaluate_rejection(state: MarketState, definition: FactDefinition) -> FactOutcome:
    """Single current bar, no history window (Sprint 12's approved
    definition). For each of the four reference levels this MarketState
    carries (previous_day_high/low, overnight_high/low):

      high-side: high reaches or breaches the level (high >= level) AND the
      close finishes below it (close < level). upper_wick = high -
      max(open, close).

      low-side: low reaches or breaches the level (low <= level) AND the
      close finishes above it (close > level). lower_wick =
      min(open, close) - low.

    effective_body = max(abs(close - open), tick_size) - floors the
    denominator at one tick so a near-zero-body bar never produces a
    division-by-a-tiny-number ratio blowup; tick_size comes from
    definition.params (sourced from atlas.market_engine.constants.TICK_SIZE
    in definitions.py - explicit metadata, never an unexplained constant
    here).

    rejection fires (value=True) if ANY qualifying level's
    wick_length / effective_body > definition.params["wick_body_ratio_threshold"]
    (strictly greater than, matching every other fact's boundary convention).
    ALL qualifying levels are preserved in evidence, not just the first or
    strongest - a bar can reject against more than one reference level at
    once if they sit close together."""
    if state.open is None or state.high is None or state.low is None or state.close is None:
        return InsufficientData(
            fact_name="rejection", definition_version=definition.version,
            reason="open/high/low/close is not present on this MarketState",
        )

    reference_levels = [
        (name, side, getattr(state, name)) for name, side in _REFERENCE_LEVELS
    ]
    if all(level is None for _, _, level in reference_levels):
        return InsufficientData(
            fact_name="rejection", definition_version=definition.version,
            reason="no reference levels (previous_day_high/low, overnight_high/low) are present on this MarketState",
        )

    tick_size = definition.params["tick_size"]
    threshold = definition.params["wick_body_ratio_threshold"]

    open_, high, low, close = state.open.value, state.high.value, state.low.value, state.close.value
    raw_body_length = abs(close - open_)
    effective_body = max(raw_body_length, tick_size)

    qualifying_levels = []
    for name, side, level in reference_levels:
        if level is None:
            continue
        level_value = level.value

        if side == "high":
            if high < level_value or close >= level_value:
                continue
            wick_length = high - max(open_, close)
            close_distance_from_level = level_value - close
        else:
            if low > level_value or close <= level_value:
                continue
            wick_length = min(open_, close) - low
            close_distance_from_level = close - level_value

        wick_body_ratio = wick_length / effective_body
        if wick_body_ratio <= threshold:
            continue

        qualifying_levels.append({
            "reference_level": name,
            "side": side,
            "level": level_value,
            "wick_length": wick_length,
            "raw_body_length": raw_body_length,
            "effective_body": effective_body,
            "wick_body_ratio": wick_body_ratio,
            "close_distance_from_level": close_distance_from_level,
        })

    return FactResult(
        fact_name="rejection",
        definition_version=definition.version,
        value=len(qualifying_levels) > 0,
        evidence={
            "tick_size": tick_size,
            "threshold": threshold,
            "qualifying_levels": qualifying_levels,
        },
    )


def _ols_slope(values: list[float]) -> float:
    """Ordinary least squares slope of `values` against evenly spaced x =
    0..n-1 (bar index within the window). Pure math, no numpy/scipy
    dependency - a closed-form OLS slope over evenly spaced x is a handful of
    sums, not worth a new third-party dependency for."""
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator


def evaluate_trend_5m(window: list[MarketState], definition: FactDefinition) -> FactOutcome:
    """Sprint 13's exact approved definition: a `window` (params["window"],
    default 20) bar OLS slope over all closes, converted to a projected move
    across the window (slope * (window_size - 1)), normalized by the CURRENT
    (latest) bar's atr - not an average atr across the window, per the
    approved spec's "latest ATR" wording. Classified up/down/flat against
    definition.params' up_threshold/down_threshold.

    `window` must already be chronologically ascending with the current bar
    last - this function does not sort it; sorting is the orchestration
    layer's job (build_rule_engine_output), matching how every other windowed
    fact here is written."""
    window_size = definition.params["window"]
    if len(window) < window_size:
        return InsufficientData(
            fact_name="trend_5m", definition_version=definition.version,
            reason=f"fewer than {window_size} bars available in the window (got {len(window)})",
        )
    relevant = window[-window_size:]

    if any(bar.close is None for bar in relevant):
        return InsufficientData(
            fact_name="trend_5m", definition_version=definition.version,
            reason="close is not present on one or more bars in the window",
        )
    current = relevant[-1]
    if current.atr is None:
        return InsufficientData(
            fact_name="trend_5m", definition_version=definition.version,
            reason="atr is not present on the current bar",
        )
    if current.atr == 0:
        return InsufficientData(
            fact_name="trend_5m", definition_version=definition.version,
            reason="atr is zero - a normalized move is undefined",
        )

    closes = [bar.close.value for bar in relevant]
    slope = _ols_slope(closes)
    projected_move = slope * (window_size - 1)
    normalized_move = projected_move / current.atr

    up_threshold = definition.params["up_threshold"]
    down_threshold = definition.params["down_threshold"]
    if normalized_move > up_threshold:
        value = "up"
    elif normalized_move < down_threshold:
        value = "down"
    else:
        value = "flat"

    return FactResult(
        fact_name="trend_5m",
        definition_version=definition.version,
        value=value,
        evidence={
            "window_size": window_size,
            "slope": slope,
            "projected_move": projected_move,
            "atr": current.atr,
            "normalized_move": normalized_move,
            "up_threshold": up_threshold,
            "down_threshold": down_threshold,
        },
    )


def evaluate_liquidity_sweep(window: list[MarketState], definition: FactDefinition) -> FactOutcome:
    """Sprint 13's exact approved definition, three-bar resolution window
    (params["window"], default 3): for each of the four reference levels
    (read from the CURRENT/last bar - levels are session-context, not
    per-bar), does ANY bar in the window breach it (high >= level for a
    high-side level, low <= level for a low-side level) AND is the current
    bar's close back on the origin side (below for high-side, above for
    low-side)? Every triggering level's excursion (the most extreme
    breaching high/low in the window, and which bar produced it) is
    preserved - a bar can sweep more than one level at once."""
    window_size = definition.params["window"]
    if len(window) < window_size:
        return InsufficientData(
            fact_name="liquidity_sweep", definition_version=definition.version,
            reason=f"fewer than {window_size} bars available in the window (got {len(window)})",
        )
    relevant = window[-window_size:]
    current = relevant[-1]

    if current.close is None:
        return InsufficientData(
            fact_name="liquidity_sweep", definition_version=definition.version,
            reason="close is not present on the current bar",
        )
    if any(bar.high is None or bar.low is None for bar in relevant):
        return InsufficientData(
            fact_name="liquidity_sweep", definition_version=definition.version,
            reason="high/low is not present on one or more bars in the window",
        )

    reference_levels = [(name, side, getattr(current, name)) for name, side in _REFERENCE_LEVELS]
    if all(level is None for _, _, level in reference_levels):
        return InsufficientData(
            fact_name="liquidity_sweep", definition_version=definition.version,
            reason="no reference levels (previous_day_high/low, overnight_high/low) are present on the current bar",
        )

    close = current.close.value
    qualifying_levels = []
    for name, side, level in reference_levels:
        if level is None:
            continue
        level_value = level.value

        if side == "high":
            breaching_bars = [bar for bar in relevant if bar.high.value >= level_value]
            if not breaching_bars or close >= level_value:
                continue
            excursion_bar = max(breaching_bars, key=lambda bar: bar.high.value)
            excursion = excursion_bar.high.value
        else:
            breaching_bars = [bar for bar in relevant if bar.low.value <= level_value]
            if not breaching_bars or close <= level_value:
                continue
            excursion_bar = min(breaching_bars, key=lambda bar: bar.low.value)
            excursion = excursion_bar.low.value

        qualifying_levels.append({
            "reference_level": name,
            "side": side,
            "level": level_value,
            "excursion": excursion,
            "excursion_occurred_at": excursion_bar.envelope.occurred_at.isoformat(),
            "close": close,
        })

    return FactResult(
        fact_name="liquidity_sweep",
        definition_version=definition.version,
        value=len(qualifying_levels) > 0,
        evidence={"window_size": window_size, "qualifying_levels": qualifying_levels},
    )


def evaluate_reclaim(window: list[MarketState], definition: FactDefinition) -> FactOutcome:
    """Sprint 13's approved definition, applied with ONE disclosed
    interpretation the approved spec left implicit: "origin side". For a
    LOW-side level (previous_day_low, overnight_low) the origin side is
    ABOVE the level (price's ordinary side of a support level); "beyond"
    means an earlier close below it. For a HIGH-side level
    (previous_day_high, overnight_high) the origin side is BELOW the level;
    "beyond" means an earlier close above it. reclaim(level) = some bar
    earlier in the window closed beyond the level, AND the current (last)
    bar's close is back on the origin side. Deliberately does NOT depend on
    liquidity_sweep (per the approved spec) - this looks at CLOSES only,
    liquidity_sweep looks at wicks (high/low) only; the two facts can
    disagree on the same bar.

    Evidence preserves the EARLIEST qualifying break bar per level (the
    first close that went "beyond"), not every bar that was ever beyond -
    the earliest is the most defensible single reference point for "a prior
    close beyond the level"."""
    window_size = definition.params["window"]
    if len(window) < window_size:
        return InsufficientData(
            fact_name="reclaim", definition_version=definition.version,
            reason=f"fewer than {window_size} bars available in the window (got {len(window)})",
        )
    relevant = window[-window_size:]

    if any(bar.close is None for bar in relevant):
        return InsufficientData(
            fact_name="reclaim", definition_version=definition.version,
            reason="close is not present on one or more bars in the window",
        )
    current = relevant[-1]
    earlier_bars = relevant[:-1]
    if not earlier_bars:
        return InsufficientData(
            fact_name="reclaim", definition_version=definition.version,
            reason="window has no bars earlier than the current one - a reclaim needs a prior close to reclaim from",
        )

    reference_levels = [(name, side, getattr(current, name)) for name, side in _REFERENCE_LEVELS]
    if all(level is None for _, _, level in reference_levels):
        return InsufficientData(
            fact_name="reclaim", definition_version=definition.version,
            reason="no reference levels (previous_day_high/low, overnight_high/low) are present on the current bar",
        )

    current_close = current.close.value
    qualifying_levels = []
    for name, side, level in reference_levels:
        if level is None:
            continue
        level_value = level.value

        if side == "low":
            break_bars = [bar for bar in earlier_bars if bar.close.value < level_value]
            if not break_bars or current_close <= level_value:
                continue
        else:
            break_bars = [bar for bar in earlier_bars if bar.close.value > level_value]
            if not break_bars or current_close >= level_value:
                continue

        break_bar = break_bars[0]  # earliest qualifying break in the window
        qualifying_levels.append({
            "reference_level": name,
            "side": side,
            "level": level_value,
            "break_close": break_bar.close.value,
            "break_occurred_at": break_bar.envelope.occurred_at.isoformat(),
            "current_close": current_close,
        })

    return FactResult(
        fact_name="reclaim",
        definition_version=definition.version,
        value=len(qualifying_levels) > 0,
        evidence={"window_size": window_size, "qualifying_levels": qualifying_levels},
    )


def evaluate_vwap_relationship(state: MarketState, definition: FactDefinition) -> FactOutcome:
    """Sprint 22B. Single current bar, no history window - placed after the
    windowed facts above only because it was added later; it belongs with
    volume_spike/displacement/rejection in shape (current-bar-only, no
    window). Classifies distance_from_vwap_points, ATR-normalized, into a
    three-way state relative to a symmetric threshold band:
    extended_above (normalized_distance > threshold), extended_below
    (< -threshold), or within_band (otherwise) - strictly greater/less than,
    matching every other fact's boundary convention (a value sitting exactly
    on the threshold is within_band, not extended).

    distance_from_vwap_points is already signed (close - vwap, computed and
    sent raw by TradingView - see pine/MNQU6_market_state_v1.pine's own
    `distanceFromVwapPoints = close - vwapValue`) and already in points; this
    fact trusts it directly rather than recomputing from close/vwap
    separately - the same "trust the wire's own already-computed field"
    convention atr and volume_ratio already established, and it avoids a new
    failure mode (the two independently-sent fields disagreeing) recomputing
    would introduce.

    All three values deliberately describe the SAME question (where does
    this bar sit relative to the threshold band) - a naming choice from
    Sprint 22A's design review, replacing an earlier-considered
    above/below/near vocabulary that mixed direction language ("above") with
    magnitude language ("near") inside one enum. threshold=1.0 (see
    DEFAULT_VWAP_RELATIONSHIP_DEFINITION) is a provisional, explicitly
    unvalidated heuristic, borrowed from trend_5m's own threshold shape (the
    closest existing precedent - ATR-normalized distance, symmetric
    threshold, three-way classification) rather than displacement's
    single-boolean threshold, which is a structurally different
    classification."""
    if state.distance_from_vwap_points is None:
        return InsufficientData(
            fact_name="vwap_relationship", definition_version=definition.version,
            reason="distance_from_vwap_points is not present on this MarketState",
        )
    if state.atr is None:
        return InsufficientData(
            fact_name="vwap_relationship", definition_version=definition.version,
            reason="atr is not present on this MarketState",
        )
    if state.atr == 0:
        return InsufficientData(
            fact_name="vwap_relationship", definition_version=definition.version,
            reason="atr is zero - a normalized distance is undefined",
        )

    threshold = definition.params["threshold"]
    normalized_distance = state.distance_from_vwap_points / state.atr
    if normalized_distance > threshold:
        value = "extended_above"
    elif normalized_distance < -threshold:
        value = "extended_below"
    else:
        value = "within_band"

    return FactResult(
        fact_name="vwap_relationship",
        definition_version=definition.version,
        value=value,
        evidence={
            "distance_from_vwap_points": state.distance_from_vwap_points,
            "atr": state.atr,
            "normalized_distance": normalized_distance,
            "threshold": threshold,
        },
    )
