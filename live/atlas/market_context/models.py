"""
Market Context domain model - Phase N1, Sprint 1. Every type here is frozen:
a MarketContext is Atlas's own interpretation of a bar's situation (session
phase, volatility regime), computed once and never mutated afterward - the
same "immutable in fact, not just by type hint" discipline
atlas.core.primitives already established for Symbol/Price.

Reuses Symbol/Timeframe from atlas.core.primitives exactly as MarketState
does - no duplicate primitives. MarketContext is joined to a MarketState by
(symbol, timeframe, occurred_at) only; it is never a field on MarketState
itself, and nothing in this module imports atlas.market_engine.models.

DriftStatus and ContextQuality exist because a plain bool can't represent
"there was nothing to compare against" (session_name/is_rth are Optional on
the wire) without silently conflating that with agreement - see the
approved Phase N1 architecture amendments for the full reasoning. Both are
str Enum, matching every other closed classification in this codebase
(SessionPhase, VolatilityRegime, atlas.market_engine.models.BarStatus).
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from atlas.core.primitives import Symbol, Timeframe


class SessionPhase(str, Enum):
    PRE_OPEN = "pre_open"
    OPENING_RANGE = "opening_range"
    MID_SESSION = "mid_session"
    CLOSING_RANGE = "closing_range"
    OVERNIGHT = "overnight"


class VolatilityRegime(str, Enum):
    """INSUFFICIENT_HISTORY is a real classification, not a missing-data
    placeholder - a bar with too little trailing history to rank must never
    silently fall back to NORMAL, the same "an honest unknown beats a
    guessed default" posture Rule Engine's InsufficientData and RE-2's
    insufficient_reason_counts already established elsewhere."""

    INSUFFICIENT_HISTORY = "insufficient_history"
    COMPRESSED = "compressed"
    NORMAL = "normal"
    EXPANDED = "expanded"


class DriftStatus(str, Enum):
    """UPSTREAM_MISSING is distinct from AGREEMENT on purpose: upstream
    session_name/is_rth are Optional on the wire
    (TradingViewMarketStatePayload), so "nothing to compare" is a real,
    distinct case from "compared and they matched" - collapsing the two
    into one bool would misreport an unverifiable bar as a verified-clean
    one."""

    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    UPSTREAM_MISSING = "upstream_missing"


class ContextQuality(str, Enum):
    """A pure aggregation of DriftStatus and VolatilityRegime - never an
    independent judgment call. Computed in service.py (not part of Sprint
    1), by this precedence: DEGRADED (session DISAGREEMENT or regime
    INSUFFICIENT_HISTORY - a confirmed, specific issue) outranks UNKNOWN
    (session UPSTREAM_MISSING - nothing confirmed wrong, but nothing
    confirmed either), which outranks TRUSTED."""

    TRUSTED = "trusted"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SessionProgress:
    """Populated only while phase is RTH-anchored (OPENING_RANGE,
    MID_SESSION, CLOSING_RANGE) - all four fields are None during OVERNIGHT
    and, deliberately, during PRE_OPEN too (PRE_OPEN is defined as
    not-yet-RTH-anchored for Phase N1 - no countdown-to-open variant)."""

    session_open_at: Optional[datetime]
    session_close_at: Optional[datetime]
    minutes_since_session_open: Optional[int]
    minutes_until_session_close: Optional[int]


@dataclass(frozen=True)
class SessionClassification:
    """upstream_session_name/upstream_is_rth are Pine's own values,
    preserved for comparison/drift diagnostics only - never read by the
    classifier that produces `phase`, and never corrected to match them."""

    phase: SessionPhase
    progress: SessionProgress
    upstream_session_name: Optional[str]
    upstream_is_rth: Optional[bool]
    drift_status: DriftStatus


@dataclass(frozen=True)
class VolatilityClassification:
    """atr_percentile_rank is None exactly when regime is
    INSUFFICIENT_HISTORY - never a stale or fabricated number.
    lookback_bars_used is the actual bar count the rank was computed over,
    which may be less than a RegimeClassifierDefinition's configured
    lookback_bars during warm-up (relevant for `regime`, which reflects
    whether that count met min_bars_required)."""

    regime: VolatilityRegime
    atr_percentile_rank: Optional[float]
    lookback_bars_used: int


@dataclass(frozen=True)
class MarketContext:
    """The package's one public output type. classifier_version/
    calendar_version name exactly which immutable definitions.py constant
    produced this (e.g. "CME_RTH_V1") - never an anonymous computation.
    context_fingerprint is the machine-verifiable proof underneath that
    label - see fingerprint.py."""

    symbol: Symbol
    timeframe: Timeframe
    occurred_at: datetime
    session: SessionClassification
    volatility: VolatilityClassification
    quality: ContextQuality
    classifier_version: str
    calendar_version: str
    context_fingerprint: str
