"""
The canonical MarketState model - the one internal shape every future adapter
(TradingView today; Tradovate/Databento/others later) translates into, and the
one shape the repository, API, and eventually AI Analyst all operate on. Built
entirely on atlas.core primitives - nothing here is TradingView-specific.

Design note on event_type vs. the boolean flags (a decision already made in this
project's architecture review, implemented here for the first time, not
re-opened): one MarketState is emitted per confirmed bar close. `event_type`
names the single most significant thing that happened (a fixed priority order -
see MarketEventType), defaulting to BAR_CLOSED when nothing notable did. The
boolean flags below remain present for CO-OCCURRING secondary conditions (e.g.
event_type="reclaim" with volume_spike=True) - they are not a second, competing
way to express the same information.

occurred_at/received_at live on the composed `envelope: Event` (Sprint 1) -
MarketState does not duplicate them as its own fields. This is genuine reuse:
Event's own validation (timezone-aware, non-blank type/source) runs for every
MarketState constructed, not re-implemented here.
"""
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_engine.errors import MarketEngineValidationError


class BarStatus(str, Enum):
    CLOSED = "closed"
    FORMING = "forming"


class MarketEventType(str, Enum):
    """The discriminated event types a MarketState's envelope.event_type may
    hold. Fixed and closed - a new event type is a deliberate model change, not
    an arbitrary string an adapter can introduce unilaterally."""

    BAR_CLOSED = "bar_closed"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    RECLAIM = "reclaim"
    BREAKOUT = "breakout"
    SESSION_OPEN = "session_open"
    SESSION_CLOSE = "session_close"
    VOLUME_SPIKE = "volume_spike"


@dataclass(frozen=True)
class MarketState:
    """The canonical market-state event. Every optional field is explicit -
    absent data is None, never a fabricated default. Price fields are Price
    instances (already tick-validated by atlas.core.primitives.Price at
    construction) - a caller can never end up holding an off-tick MarketState."""

    envelope: Event
    schema_version: str
    symbol: Symbol
    timeframe: Timeframe
    bar_status: BarStatus

    # Price
    open: Optional[Price] = None
    high: Optional[Price] = None
    low: Optional[Price] = None
    close: Optional[Price] = None
    volume: Optional[float] = None

    # Session
    session_name: Optional[Session] = None
    is_rth: Optional[bool] = None
    trading_date: Optional[date] = None
    rth_open: Optional[Price] = None
    previous_day_high: Optional[Price] = None
    previous_day_low: Optional[Price] = None
    overnight_high: Optional[Price] = None
    overnight_low: Optional[Price] = None

    # VWAP & volatility
    vwap: Optional[Price] = None
    distance_from_vwap_points: Optional[float] = None
    atr: Optional[float] = None
    volume_ratio: Optional[float] = None

    # Liquidity context
    nearest_liquidity_level: Optional[Price] = None
    nearest_liquidity_type: Optional[str] = None
    distance_to_liquidity_ticks: Optional[float] = None
    overnight_high_status: Optional[str] = None
    overnight_low_status: Optional[str] = None
    previous_day_high_status: Optional[str] = None
    previous_day_low_status: Optional[str] = None

    # Trend context
    trend_1m: Optional[str] = None
    trend_5m: Optional[str] = None
    trend_15m: Optional[str] = None
    trend_1h: Optional[str] = None

    # Secondary, co-occurring flags - event_type carries the primary signal (see
    # this module's docstring); these are not a duplicate encoding of it.
    liquidity_sweep: Optional[bool] = None
    reclaim: Optional[bool] = None
    rejection: Optional[bool] = None
    displacement: Optional[bool] = None
    volume_spike: Optional[bool] = None

    def __post_init__(self) -> None:
        if not self.schema_version or not self.schema_version.strip():
            raise MarketEngineValidationError("schema_version must not be blank")
        try:
            MarketEventType(self.envelope.event_type)
        except ValueError:
            raise MarketEngineValidationError(
                f"envelope.event_type {self.envelope.event_type!r} is not a recognized "
                f"MarketEventType value: {[e.value for e in MarketEventType]}"
            ) from None

    @property
    def event_type(self) -> MarketEventType:
        """Typed access to the envelope's event_type string - the envelope is
        the single source of truth (see __post_init__'s validation); this is a
        read-only convenience, not a second stored value that could drift."""
        return MarketEventType(self.envelope.event_type)
