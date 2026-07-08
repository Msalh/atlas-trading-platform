"""
Postgres-backed implementation of TradeRepository, used in every deployed environment.

Concurrency note: `claim_and_forward` wraps the "has this already been forwarded /
forward it / record the result" sequence in a single Postgres transaction holding an
advisory lock scoped to the correlation_id (`pg_advisory_xact_lock(hashtext(...))`).
This is a genuine hardening over the Sprint 0 SQLite version: SQLite's single-writer
model made a true concurrent-duplicate-webhook race unlikely in practice, but nothing
actually prevented it. Postgres gives us a cheap, correct primitive for it, so two
webhook deliveries for the same correlation_id arriving at the same instant can no
longer both reach PickMyTrade - the second one blocks on the lock until the first
transaction commits, then sees `pmt_forwarded = true` and is treated as a duplicate.

This does mean a pooled connection is held for the duration of the PickMyTrade HTTP
call (up to its 15s timeout) while inside the transaction. That's an accepted
trade-off given TradingView's low signal frequency for this strategy - see
docs/sprint1/architecture-decisions.md.
"""
import json
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from atlas.repositories.base import ClaimResult, ForwardFn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decode_ai_note(row: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Replaces the stored `factors_json` TEXT column with a real `factors` list (or
    None) - callers of the repository interface work with Python data, never a JSON
    string. See migrations/0004_ai_intelligence_fields.sql."""
    if row is None:
        return None
    raw = row.pop("factors_json", None)
    row["factors"] = json.loads(raw) if raw else None
    return row


class PostgresTradeRepository:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def claim_and_forward(
        self, correlation_id: str, entry: dict[str, Any], raw_body: str, forward: ForwardFn,
    ) -> ClaimResult:
        async with self._pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (correlation_id,))

                cur = await conn.execute(
                    "SELECT pmt_forwarded FROM trades WHERE correlation_id = %s", (correlation_id,)
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return ClaimResult(forwarded=True, pmt_status_code=None, pmt_error=None, duplicate=True)

                forwarded, pmt_status_code, pmt_error = await forward()

                params = {
                    "correlation_id": correlation_id,
                    "received_at": now_iso(),
                    "signal_time": entry.get("signal_time"),
                    "direction": entry.get("direction"),
                    "setup_tag": entry.get("setup_tag"),
                    "symbol": entry.get("symbol"),
                    "entry_price": entry.get("entry_price"),
                    "sl": entry.get("sl"),
                    "tp": entry.get("tp"),
                    "atr": entry.get("atr"),
                    "ema_distance_atr": entry.get("ema_distance_atr"),
                    "regime_slope_pct": entry.get("regime_slope_pct"),
                    "sweep_age_bars": entry.get("sweep_age_bars"),
                    "session": entry.get("session"),
                    "quantity": entry.get("quantity"),
                    "pmt_forwarded": forwarded,
                    "pmt_status_code": pmt_status_code,
                    "pmt_error": pmt_error,
                    "raw_entry_payload": raw_body,
                }
                await conn.execute(
                    """
                    INSERT INTO trades
                        (correlation_id, received_at, signal_time, direction, setup_tag, symbol,
                         entry_price, sl, tp, atr, ema_distance_atr, regime_slope_pct, sweep_age_bars,
                         session, quantity, status, pmt_forwarded, pmt_status_code, pmt_error, raw_entry_payload)
                    VALUES
                        (%(correlation_id)s, %(received_at)s, %(signal_time)s, %(direction)s, %(setup_tag)s,
                         %(symbol)s, %(entry_price)s, %(sl)s, %(tp)s, %(atr)s, %(ema_distance_atr)s,
                         %(regime_slope_pct)s, %(sweep_age_bars)s, %(session)s, %(quantity)s, 'open',
                         %(pmt_forwarded)s, %(pmt_status_code)s, %(pmt_error)s, %(raw_entry_payload)s)
                    ON CONFLICT (correlation_id) DO UPDATE SET
                        received_at = EXCLUDED.received_at, signal_time = EXCLUDED.signal_time,
                        direction = EXCLUDED.direction, setup_tag = EXCLUDED.setup_tag,
                        symbol = EXCLUDED.symbol, entry_price = EXCLUDED.entry_price,
                        sl = EXCLUDED.sl, tp = EXCLUDED.tp, atr = EXCLUDED.atr,
                        ema_distance_atr = EXCLUDED.ema_distance_atr,
                        regime_slope_pct = EXCLUDED.regime_slope_pct,
                        sweep_age_bars = EXCLUDED.sweep_age_bars, session = EXCLUDED.session,
                        quantity = EXCLUDED.quantity,
                        pmt_forwarded = EXCLUDED.pmt_forwarded, pmt_status_code = EXCLUDED.pmt_status_code,
                        pmt_error = EXCLUDED.pmt_error, raw_entry_payload = EXCLUDED.raw_entry_payload
                    """,
                    params,
                )
                # Deliberately does not touch status/current_price/exit_price/llm_* columns
                # on conflict, so a retry of a previously-failed entry can't clobber later
                # lifecycle data.
                return ClaimResult(
                    forwarded=forwarded, pmt_status_code=pmt_status_code, pmt_error=pmt_error, duplicate=False,
                )

    async def update_price(self, correlation_id, current_price, unrealized_pnl, updated_at) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE trades SET current_price=%s, unrealized_pnl=%s, last_update_at=%s WHERE correlation_id=%s",
                (current_price, unrealized_pnl, updated_at, correlation_id),
            )
            return cur.rowcount

    async def update_pmt_diagnostics(self, correlation_id: str, diagnostics: dict[str, Any]) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE trades SET pmt_relay_diagnostics=%s WHERE correlation_id=%s",
                (json.dumps(diagnostics, default=str), correlation_id),
            )
            return cur.rowcount

    async def update_exit(self, correlation_id, status, exit_price, realized_pnl, closed_at) -> int:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE trades SET status=%s, exit_price=%s, realized_pnl=%s, closed_at=%s WHERE correlation_id=%s",
                (status, exit_price, realized_pnl, closed_at, correlation_id),
            )
            return cur.rowcount

    async def add_ai_note(
        self, *, trade_correlation_id, note_type, model, content, error, score=None, score_label=None,
        expected_r=None, historical_win_rate_pct=None, similar_trade_count=None, factors=None,
    ) -> dict[str, Any]:
        factors_json = json.dumps(factors) if factors is not None else None
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO ai_notes
                        (trade_correlation_id, note_type, created_at, model, score, score_label, content, error,
                         expected_r, historical_win_rate_pct, similar_trade_count, factors_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        trade_correlation_id, note_type, now_iso(), model, score, score_label, content, error,
                        expected_r, historical_win_rate_pct, similar_trade_count, factors_json,
                    ),
                )
                return _decode_ai_note(await cur.fetchone())

    async def list_ai_notes(self, *, trade_correlation_id=None, note_type=None, limit=100) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if trade_correlation_id is not None:
            conditions.append("trade_correlation_id = %s")
            params.append(trade_correlation_id)
        if note_type is not None:
            conditions.append("note_type = %s")
            params.append(note_type)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"SELECT * FROM ai_notes {where_clause} ORDER BY id DESC LIMIT %s", params,
                )
                return [_decode_ai_note(row) for row in await cur.fetchall()]

    async def list_recent(self, limit: int = 100, status: Optional[str] = None) -> list[dict[str, Any]]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                if status:
                    await cur.execute(
                        "SELECT * FROM trades WHERE status = %s ORDER BY id DESC LIMIT %s", (status, limit)
                    )
                else:
                    await cur.execute("SELECT * FROM trades ORDER BY id DESC LIMIT %s", (limit,))
                return await cur.fetchall()

    async def get_open_trade(self) -> Optional[dict[str, Any]]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM trades WHERE status = 'open' ORDER BY id DESC LIMIT 1")
                return await cur.fetchone()

    async def get_by_correlation_id(self, correlation_id: str) -> Optional[dict[str, Any]]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM trades WHERE correlation_id = %s", (correlation_id,))
                return await cur.fetchone()

    async def ping(self) -> bool:
        async with self._pool.connection() as conn:
            await conn.execute("SELECT 1")
        return True
