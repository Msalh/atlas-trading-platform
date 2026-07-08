"""
Pydantic validation for the TradingView webhook payload (Sprint 9). Replaces raw
`payload.get(...)` access with a real schema, closing the gap the Sprint 8 audit
called out: a malformed field (e.g. an unrecognized `direction`) used to silently
degrade downstream calculations (atlas/risk.py's risk_reward_points returns
`(None, None)` for anything but "long"/"short") instead of being rejected outright.

Deliberately permissive on unknown fields (`extra="allow"`): this does NOT change the
TradingView payload contract or PickMyTrade relay semantics - fields this model
doesn't explicitly know about (PickMyTrade-only fields like `strategy_name`, `data`,
`price`, `token`, etc. - see atlas/services/pickmytrade.py's PMT_FIELDS) still pass
through untouched to whatever reads the raw dict downstream. Only `correlation_id`
and `type` are required; every trade-data field stays optional, matching the existing
`.get()`-based tolerance for a field being absent - the point of this model is to
reject wrong TYPES/VALUES when a field is present, and a wrong type is a very
different, much clearer signal ("this payload is corrupted") than a merely-absent
optional field ("this event type doesn't carry that field").
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["entry", "price_update", "exit"] = "entry"
    correlation_id: str
    secret: Optional[str] = None

    # Entry fields (see atlas/repositories/memory.py's ENTRY_FIELDS for the same set)
    direction: Optional[Literal["long", "short"]] = None
    setup_tag: Optional[str] = None
    symbol: Optional[str] = None
    entry_price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    atr: Optional[float] = None
    ema_distance_atr: Optional[float] = None
    regime_slope_pct: Optional[float] = None
    sweep_age_bars: Optional[int] = None
    session: Optional[str] = None
    quantity: Optional[int] = None
    signal_time: Optional[str] = None

    # price_update fields
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None

    # exit fields - `outcome` deliberately NOT constrained to a Literal: the handler's
    # own logic already treats anything other than "WIN" (case-insensitive) as a loss
    # (see atlas/api/v1/webhook.py::_handle_exit), so over-constraining this field
    # would reject inputs the system has always tolerated by design.
    outcome: Optional[str] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None

    @field_validator("correlation_id")
    @classmethod
    def correlation_id_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("correlation_id must not be blank")
        return v

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError("quantity must be positive")
        return v
