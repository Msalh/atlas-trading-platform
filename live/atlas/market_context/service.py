"""
Market Context composition - Phase N1, Sprint 4. build_market_context() is
the one place session.py, regime.py, and fingerprint.py get wired together
into a MarketContext - composition only, no new business logic: every
number in session/volatility comes from classify_session()/
classify_volatility_regime() unchanged, this module only decides how to
combine their outputs into one ContextQuality and one fingerprint.

--- Inputs ---

Unlike regime.py (which infers nothing beyond what its window contains),
this module accepts symbol/timeframe/occurred_at as explicit parameters
rather than reading them off window[-1]. Two reasons: (1) classify_session
already takes occurred_at as its own explicit parameter, so passing it
again here - rather than deriving it from the window - keeps this module's
signature a straightforward superset of session.py's plus regime.py's own
parameters, not a new inference rule; (2) an invalid window (see
ContextQuality below) may be too broken to safely read window[-1] from at
all (EmptyWindowError - there is no window[-1]) - identity must stay
available even when the window itself does not.

--- ContextQuality derivation ---

Exactly three states, decided by this precedence (first match wins):

1. window invalid (any WindowIntegrityError from
   validate_market_state_window, raised inside classify_volatility_regime
   and caught here) or regime == INSUFFICIENT_HISTORY -> UNKNOWN. A broken
   or too-short window means volatility genuinely cannot be trusted,
   regardless of what session/drift says.
2. drift_status == UPSTREAM_MISSING -> UNKNOWN. No upstream value was ever
   supplied to compare against - nothing to disagree with, but nothing
   confirmed either.
3. drift_status == DISAGREEMENT -> DEGRADED. Volatility is trustworthy, but
   Atlas's own session read and upstream's disagree on this bar.
4. Otherwise (window valid, sufficient history, drift_status == AGREEMENT)
   -> TRUSTED.

UNKNOWN takes precedence over DEGRADED when both conditions are true at
once (e.g. DISAGREEMENT plus INSUFFICIENT_HISTORY) - a data-quality problem
is treated as the stronger signal than a session-labeling disagreement. No
state beyond these three is ever produced.

--- Invalid-window fallback ---

When validate_market_state_window (called inside classify_volatility_regime)
raises, this module does not re-implement or bypass that check - it catches
the resulting WindowIntegrityError and builds a placeholder
VolatilityClassification(regime=INSUFFICIENT_HISTORY,
atr_percentile_rank=None, lookback_bars_used=len(window)) so a
MarketContext can still be returned - quality=UNKNOWN makes clear the
volatility field is not a real classification, not a new VolatilityRegime
value.

--- Fingerprint ---

Hashes only the two active definitions (calendar, classifier) - their
declared identity AND their actual serialized params, per fingerprint.py's
own "detect a params edit without a version bump" guarantee. Never hashes
occurred_at, the window, upstream values, or the MarketContext being built
itself - a self-referential fingerprint would be circular and would change
on every bar for reasons having nothing to do with configuration.
"""
from datetime import datetime
from typing import Optional

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import (
    CME_RTH_V1,
    REGIME_CLASSIFIER_V1,
    RegimeClassifierDefinition,
    SessionCalendarDefinition,
)
from atlas.market_context.fingerprint import compute_fingerprint
from atlas.market_context.models import (
    ContextQuality,
    DriftStatus,
    MarketContext,
    VolatilityClassification,
    VolatilityRegime,
)
from atlas.market_context.regime import classify_volatility_regime
from atlas.market_context.session import classify_session
from atlas.market_engine.models import MarketState
from atlas.rule_engine.window_integrity import WindowIntegrityError


def _derive_quality(
    drift_status: DriftStatus, volatility: VolatilityClassification, window_valid: bool,
) -> ContextQuality:
    if not window_valid or volatility.regime == VolatilityRegime.INSUFFICIENT_HISTORY:
        return ContextQuality.UNKNOWN
    if drift_status == DriftStatus.UPSTREAM_MISSING:
        return ContextQuality.UNKNOWN
    if drift_status == DriftStatus.DISAGREEMENT:
        return ContextQuality.DEGRADED
    return ContextQuality.TRUSTED


def build_market_context(
    symbol: Symbol,
    timeframe: Timeframe,
    occurred_at: datetime,
    window: list[MarketState],
    upstream_session_name: Optional[str],
    upstream_is_rth: Optional[bool],
    calendar: SessionCalendarDefinition = CME_RTH_V1,
    classifier: RegimeClassifierDefinition = REGIME_CLASSIFIER_V1,
) -> MarketContext:
    """Pure. Composes classify_session() + classify_volatility_regime() into
    one MarketContext; see the module docstring for ContextQuality
    precedence and the invalid-window fallback. `window` is passed through
    to classify_volatility_regime() unchanged - its own ascending,
    single-symbol, single-timeframe, strictly-contiguous contract applies
    here exactly as documented there; a violation is caught (not
    re-validated) and reflected as ContextQuality.UNKNOWN rather than
    propagated as an exception, so a caller building a MarketContext for
    display/audit purposes always gets one back."""
    session = classify_session(occurred_at, upstream_session_name, upstream_is_rth, calendar)

    try:
        volatility = classify_volatility_regime(window, classifier)
        window_valid = True
    except WindowIntegrityError:
        volatility = VolatilityClassification(
            regime=VolatilityRegime.INSUFFICIENT_HISTORY,
            atr_percentile_rank=None,
            lookback_bars_used=len(window),
        )
        window_valid = False

    quality = _derive_quality(session.drift_status, volatility, window_valid)

    context_fingerprint = compute_fingerprint(
        {"session_calendar": calendar, "regime_classifier": classifier},
    )

    return MarketContext(
        symbol=symbol,
        timeframe=timeframe,
        occurred_at=occurred_at,
        session=session,
        volatility=volatility,
        quality=quality,
        classifier_version=classifier.version,
        calendar_version=calendar.version,
        context_fingerprint=context_fingerprint,
    )
