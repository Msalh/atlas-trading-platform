"""
The raw wire-format payload TradingView Pine sends. Same validation discipline
as atlas.api.v1.webhook_models.WebhookPayload: `extra="allow"` (an unknown
field is tolerated, not rejected - the wire contract can grow additively
without breaking ingestion), but every field this model DOES know about is
type-checked strictly - a wrong type is rejected, an absent optional field is
not.

This model has no knowledge of atlas.core or atlas.market_engine - it only
describes what arrives on the wire. Translating it into the canonical
MarketState (including tick-size and enum validation) is translator.py's job,
not this model's.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class TradingViewMarketStatePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Identity - required
    schema_version: str
    event_id: str
    symbol: str
    source: str = "tradingview"
    timeframe: str
    timestamp: str  # ISO-8601, UTC - parsed by translator.py
    bar_status: Literal["closed", "forming"]
    event_type: str = "bar_closed"

    # Price
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None

    # Session
    session_name: Optional[str] = None
    is_rth: Optional[bool] = None
    trading_date: Optional[str] = None  # YYYY-MM-DD
    rth_open: Optional[float] = None
    previous_day_high: Optional[float] = None
    previous_day_low: Optional[float] = None
    overnight_high: Optional[float] = None
    overnight_low: Optional[float] = None

    # VWAP & volatility
    vwap: Optional[float] = None
    distance_from_vwap_points: Optional[float] = None
    atr: Optional[float] = None
    volume_ratio: Optional[float] = None

    # Liquidity context
    nearest_liquidity_level: Optional[float] = None
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

    # Secondary co-occurring flags
    liquidity_sweep: Optional[bool] = None
    reclaim: Optional[bool] = None
    rejection: Optional[bool] = None
    displacement: Optional[bool] = None
    volume_spike: Optional[bool] = None

    @field_validator("schema_version", "event_id", "symbol", "timeframe")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v
