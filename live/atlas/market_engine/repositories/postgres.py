"""
Postgres-backed MarketStateRepository - Sprint 3 (ingest), Sprint 4 (read).

ingest() is a single INSERT ... ON CONFLICT DO NOTHING, with no advisory lock -
a deliberate difference from PostgresTradeRepository.claim_and_forward, not an
oversight. That lock exists there specifically to make a NON-IDEMPOTENT SIDE
EFFECT (a PickMyTrade HTTP call) safe under concurrency: two requests for the
same correlation_id must never both fire the external call. Market-state
ingestion has no side effect beyond the insert itself, and Postgres's own
UNIQUE constraint (migrations/0006_market_engine.sql) already makes a
concurrent duplicate insert atomic and correct without any additional locking
- copying the advisory-lock pattern here would be unnecessary complexity
solving a problem this table doesn't have.

get_latest/get_history (Sprint 4) both query
(symbol, timeframe, occurred_at DESC) - exactly the index
migrations/0007_market_engine_read_index.sql adds, in this Sprint, alongside
the query that first needs it (see that migration's own comment for why it
did not belong in Sprint 3). _row_to_state is the deliberate inverse of
_state_to_params below - kept next to it so a future column change is easy to
keep both directions in sync.
"""
from datetime import date, datetime
from typing import Any, Optional

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_engine.constants import TICK_SIZE
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.ports import IngestOutcome

_INSERT_SQL = """
    INSERT INTO market_state_events (
        event_id, symbol, timeframe, schema_version, event_type, source,
        occurred_at, received_at, bar_status,
        open, high, low, close, volume,
        session_name, is_rth, trading_date, rth_open,
        previous_day_high, previous_day_low, overnight_high, overnight_low,
        vwap, distance_from_vwap_points, atr, volume_ratio,
        nearest_liquidity_level, nearest_liquidity_type, distance_to_liquidity_ticks,
        overnight_high_status, overnight_low_status,
        previous_day_high_status, previous_day_low_status,
        trend_1m, trend_5m, trend_15m, trend_1h,
        liquidity_sweep, reclaim, rejection, displacement, volume_spike,
        raw_payload
    ) VALUES (
        %(event_id)s, %(symbol)s, %(timeframe)s, %(schema_version)s, %(event_type)s, %(source)s,
        %(occurred_at)s, %(received_at)s, %(bar_status)s,
        %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s,
        %(session_name)s, %(is_rth)s, %(trading_date)s, %(rth_open)s,
        %(previous_day_high)s, %(previous_day_low)s, %(overnight_high)s, %(overnight_low)s,
        %(vwap)s, %(distance_from_vwap_points)s, %(atr)s, %(volume_ratio)s,
        %(nearest_liquidity_level)s, %(nearest_liquidity_type)s, %(distance_to_liquidity_ticks)s,
        %(overnight_high_status)s, %(overnight_low_status)s,
        %(previous_day_high_status)s, %(previous_day_low_status)s,
        %(trend_1m)s, %(trend_5m)s, %(trend_15m)s, %(trend_1h)s,
        %(liquidity_sweep)s, %(reclaim)s, %(rejection)s, %(displacement)s, %(volume_spike)s,
        %(raw_payload)s
    )
    ON CONFLICT (symbol, timeframe, event_id) DO NOTHING
    RETURNING id
"""


def _price_value(price: Optional[Price]) -> Optional[float]:
    return None if price is None else price.value


def _state_to_params(state: MarketState, raw_payload: str) -> dict:
    return {
        "event_id": state.envelope.event_id,
        "symbol": state.symbol.ticker,
        "timeframe": state.timeframe.value,
        "schema_version": state.schema_version,
        "event_type": state.envelope.event_type,
        "source": state.envelope.source,
        "occurred_at": state.envelope.occurred_at.isoformat(),
        "received_at": state.envelope.received_at.isoformat(),
        "bar_status": state.bar_status.value,
        "open": _price_value(state.open),
        "high": _price_value(state.high),
        "low": _price_value(state.low),
        "close": _price_value(state.close),
        "volume": state.volume,
        "session_name": state.session_name.value if state.session_name is not None else None,
        "is_rth": state.is_rth,
        "trading_date": state.trading_date.isoformat() if state.trading_date is not None else None,
        "rth_open": _price_value(state.rth_open),
        "previous_day_high": _price_value(state.previous_day_high),
        "previous_day_low": _price_value(state.previous_day_low),
        "overnight_high": _price_value(state.overnight_high),
        "overnight_low": _price_value(state.overnight_low),
        "vwap": _price_value(state.vwap),
        "distance_from_vwap_points": state.distance_from_vwap_points,
        "atr": state.atr,
        "volume_ratio": state.volume_ratio,
        "nearest_liquidity_level": _price_value(state.nearest_liquidity_level),
        "nearest_liquidity_type": state.nearest_liquidity_type,
        "distance_to_liquidity_ticks": state.distance_to_liquidity_ticks,
        "overnight_high_status": state.overnight_high_status,
        "overnight_low_status": state.overnight_low_status,
        "previous_day_high_status": state.previous_day_high_status,
        "previous_day_low_status": state.previous_day_low_status,
        "trend_1m": state.trend_1m,
        "trend_5m": state.trend_5m,
        "trend_15m": state.trend_15m,
        "trend_1h": state.trend_1h,
        "liquidity_sweep": state.liquidity_sweep,
        "reclaim": state.reclaim,
        "rejection": state.rejection,
        "displacement": state.displacement,
        "volume_spike": state.volume_spike,
        "raw_payload": raw_payload,
    }


def _row_price(row: dict[str, Any], column: str) -> Optional[Price]:
    value = row[column]
    return None if value is None else Price(value=value, tick_size=TICK_SIZE)


def _row_to_state(row: dict[str, Any]) -> MarketState:
    """The deliberate inverse of _state_to_params. Event's own constructor
    re-validates occurred_at/received_at are timezone-aware UTC on the way
    back out - datetime.fromisoformat() on a string produced by our own
    .isoformat() call always carries its offset, so this is "for free"
    correctness, not a duplicated check."""
    envelope = Event(
        event_type=row["event_type"],
        source=row["source"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        received_at=datetime.fromisoformat(row["received_at"]),
        event_id=row["event_id"],
    )
    return MarketState(
        envelope=envelope,
        schema_version=row["schema_version"],
        symbol=Symbol(row["symbol"]),
        timeframe=Timeframe(row["timeframe"]),
        bar_status=BarStatus(row["bar_status"]),
        open=_row_price(row, "open"),
        high=_row_price(row, "high"),
        low=_row_price(row, "low"),
        close=_row_price(row, "close"),
        volume=row["volume"],
        session_name=Session(row["session_name"]) if row["session_name"] is not None else None,
        is_rth=row["is_rth"],
        trading_date=date.fromisoformat(row["trading_date"]) if row["trading_date"] is not None else None,
        rth_open=_row_price(row, "rth_open"),
        previous_day_high=_row_price(row, "previous_day_high"),
        previous_day_low=_row_price(row, "previous_day_low"),
        overnight_high=_row_price(row, "overnight_high"),
        overnight_low=_row_price(row, "overnight_low"),
        vwap=_row_price(row, "vwap"),
        distance_from_vwap_points=row["distance_from_vwap_points"],
        atr=row["atr"],
        volume_ratio=row["volume_ratio"],
        nearest_liquidity_level=_row_price(row, "nearest_liquidity_level"),
        nearest_liquidity_type=row["nearest_liquidity_type"],
        distance_to_liquidity_ticks=row["distance_to_liquidity_ticks"],
        overnight_high_status=row["overnight_high_status"],
        overnight_low_status=row["overnight_low_status"],
        previous_day_high_status=row["previous_day_high_status"],
        previous_day_low_status=row["previous_day_low_status"],
        trend_1m=row["trend_1m"],
        trend_5m=row["trend_5m"],
        trend_15m=row["trend_15m"],
        trend_1h=row["trend_1h"],
        liquidity_sweep=row["liquidity_sweep"],
        reclaim=row["reclaim"],
        rejection=row["rejection"],
        displacement=row["displacement"],
        volume_spike=row["volume_spike"],
    )


_SELECT_LATEST_SQL = """
    SELECT * FROM market_state_events
    WHERE symbol = %s AND timeframe = %s
    ORDER BY occurred_at DESC
    LIMIT 1
"""

_SELECT_HISTORY_SQL = """
    SELECT * FROM market_state_events
    WHERE symbol = %s AND timeframe = %s
    ORDER BY occurred_at DESC
    LIMIT %s
"""

# Sprint 9 (Dataset Builder): reuses migrations/0007's existing
# (symbol, timeframe, occurred_at DESC) index - a B-tree index can be scanned
# in either direction, so this ASC-ordered range query is still served by it
# (verified via EXPLAIN in tests/integration, the same way get_history's own
# index usage is verified) - no new migration needed for this Sprint.
_SELECT_RANGE_SQL = """
    SELECT * FROM market_state_events
    WHERE symbol = %s AND timeframe = %s AND occurred_at >= %s AND occurred_at <= %s
    ORDER BY occurred_at ASC
    LIMIT %s
"""


class PostgresMarketStateRepository:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def ingest(self, state: MarketState, raw_payload: str) -> IngestOutcome:
        params = _state_to_params(state, raw_payload)
        async with self._pool.connection() as conn:
            cur = await conn.execute(_INSERT_SQL, params)
            row = await cur.fetchone()
            return IngestOutcome.STORED if row is not None else IngestOutcome.DUPLICATE

    async def get_latest(self, symbol: Symbol, timeframe: Timeframe) -> Optional[MarketState]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_LATEST_SQL, (symbol.ticker, timeframe.value))
                row = await cur.fetchone()
        return None if row is None else _row_to_state(row)

    async def get_history(self, symbol: Symbol, timeframe: Timeframe, limit: int = 100) -> list[MarketState]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(_SELECT_HISTORY_SQL, (symbol.ticker, timeframe.value, limit))
                rows = await cur.fetchall()
        return [_row_to_state(row) for row in rows]

    async def get_range(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime, limit: int = 10000
    ) -> list[MarketState]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    _SELECT_RANGE_SQL,
                    (symbol.ticker, timeframe.value, start.isoformat(), end.isoformat(), limit),
                )
                rows = await cur.fetchall()
        return [_row_to_state(row) for row in rows]

    async def ping(self) -> bool:
        async with self._pool.connection() as conn:
            await conn.execute("SELECT 1")
        return True
