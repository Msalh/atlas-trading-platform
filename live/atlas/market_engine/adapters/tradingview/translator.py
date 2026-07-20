"""
Translates a validated TradingViewMarketStatePayload into the canonical
MarketState. This is where tick-size rejection actually happens - not a
separate check, but a direct consequence of constructing atlas.core.primitives
.Price, which already refuses an off-tick value at construction (Sprint 1).

TICK_SIZE moved to atlas.market_engine.constants in Sprint 4, when the read
path (repositories/postgres.py) became a second consumer - see that module's
docstring for why. Re-exported here as TICK_SIZE for backward compatibility
with anything already importing it from this module's own namespace.
"""
from datetime import date, datetime

from atlas.core.errors import NaiveDatetimeError
from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.core.time import now_utc, require_utc
from atlas.market_engine.adapters.tradingview.wire_models import TradingViewMarketStatePayload
from atlas.market_engine.constants import TICK_SIZE
from atlas.market_engine.errors import MarketEngineValidationError
from atlas.market_engine.models import BarStatus, MarketState

__all__ = ["TICK_SIZE", "to_canonical"]


def _parse_utc_timestamp(raw: str) -> datetime:
    """Accepts a trailing 'Z' (TradingView's convention) as well as an
    explicit numeric UTC offset. Rejects a timestamp with no timezone
    information at all, via the same require_utc() every other timezone-aware
    field in this system is validated with."""
    normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise MarketEngineValidationError(f"timestamp {raw!r} is not a valid ISO-8601 datetime") from e
    try:
        return require_utc(parsed)
    except NaiveDatetimeError as e:
        raise MarketEngineValidationError(
            f"timestamp {raw!r} has no timezone information - a market_state "
            f"timestamp must be explicit UTC (a trailing 'Z' or a numeric offset)"
        ) from e


def _price_or_none(value: float | None) -> Price | None:
    return None if value is None else Price(value=value, tick_size=TICK_SIZE)


def to_canonical(payload: TradingViewMarketStatePayload) -> MarketState:
    envelope = Event(
        event_type=payload.event_type,
        source=payload.source,
        occurred_at=_parse_utc_timestamp(payload.timestamp),
        received_at=now_utc(),
        event_id=payload.event_id,
    )

    trading_date: date | None = (
        date.fromisoformat(payload.trading_date) if payload.trading_date is not None else None
    )
    session_name: Session | None = (
        Session(payload.session_name) if payload.session_name is not None else None
    )

    return MarketState(
        envelope=envelope,
        schema_version=payload.schema_version,
        symbol=Symbol(payload.symbol),
        timeframe=Timeframe(payload.timeframe),
        bar_status=BarStatus(payload.bar_status),
        open=_price_or_none(payload.open),
        high=_price_or_none(payload.high),
        low=_price_or_none(payload.low),
        close=_price_or_none(payload.close),
        volume=payload.volume,
        session_name=session_name,
        is_rth=payload.is_rth,
        trading_date=trading_date,
        rth_open=_price_or_none(payload.rth_open),
        previous_day_high=_price_or_none(payload.previous_day_high),
        previous_day_low=_price_or_none(payload.previous_day_low),
        overnight_high=_price_or_none(payload.overnight_high),
        overnight_low=_price_or_none(payload.overnight_low),
        vwap=payload.vwap,
        distance_from_vwap_points=payload.distance_from_vwap_points,
        atr=payload.atr,
        volume_ratio=payload.volume_ratio,
        nearest_liquidity_level=_price_or_none(payload.nearest_liquidity_level),
        nearest_liquidity_type=payload.nearest_liquidity_type,
        distance_to_liquidity_ticks=payload.distance_to_liquidity_ticks,
        overnight_high_status=payload.overnight_high_status,
        overnight_low_status=payload.overnight_low_status,
        previous_day_high_status=payload.previous_day_high_status,
        previous_day_low_status=payload.previous_day_low_status,
        trend_1m=payload.trend_1m,
        trend_5m=payload.trend_5m,
        trend_15m=payload.trend_15m,
        trend_1h=payload.trend_1h,
        liquidity_sweep=payload.liquidity_sweep,
        reclaim=payload.reclaim,
        rejection=payload.rejection,
        displacement=payload.displacement,
        volume_spike=payload.volume_spike,
    )
