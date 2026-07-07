"""
In-memory TradeRepository test double. Implements the exact same interface as
PostgresTradeRepository so unit tests can exercise the webhook/service orchestration
logic (idempotency, non-blocking Claude, failure visibility, lifecycle updates)
without a real database. Real Postgres behavior itself (SQL correctness, the
advisory-lock concurrency guarantee) is covered separately by
tests/integration/test_postgres_repository.py against an actual Postgres instance -
this class is a test seam, not a substitute for that.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

from atlas.repositories.base import ClaimResult

ENTRY_FIELDS = [
    "signal_time", "direction", "setup_tag", "symbol",
    "entry_price", "sl", "tp", "atr", "ema_distance_atr", "regime_slope_pct",
    "sweep_age_bars", "session", "quantity",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InMemoryTradeRepository:
    def __init__(self):
        self._trades: dict[str, dict[str, Any]] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def claim_and_forward(self, correlation_id, entry, raw_body, forward) -> ClaimResult:
        async with self._lock:
            existing = self._trades.get(correlation_id)
            if existing and existing["pmt_forwarded"]:
                return ClaimResult(forwarded=True, pmt_status_code=None, pmt_error=None, duplicate=True)

            forwarded, pmt_status_code, pmt_error = await forward()

            if existing:
                row = existing
            else:
                row = {
                    "id": self._next_id,
                    "status": "open",
                    "current_price": None, "unrealized_pnl": None, "last_update_at": None,
                    "exit_price": None, "realized_pnl": None, "closed_at": None,
                    "llm_model": None, "llm_analysis": None, "llm_error": None,
                }
                self._next_id += 1

            row["correlation_id"] = correlation_id  # trust the explicit parameter, not entry["correlation_id"]
            row["received_at"] = now_iso()
            for field in ENTRY_FIELDS:
                row[field] = entry.get(field)
            row["pmt_forwarded"] = forwarded
            row["pmt_status_code"] = pmt_status_code
            row["pmt_error"] = pmt_error
            row["raw_entry_payload"] = raw_body

            self._trades[correlation_id] = row
            return ClaimResult(
                forwarded=forwarded, pmt_status_code=pmt_status_code, pmt_error=pmt_error, duplicate=False,
            )

    async def update_price(self, correlation_id, current_price, unrealized_pnl, updated_at) -> int:
        row = self._trades.get(correlation_id)
        if not row:
            return 0
        row["current_price"] = current_price
        row["unrealized_pnl"] = unrealized_pnl
        row["last_update_at"] = updated_at
        return 1

    async def update_exit(self, correlation_id, status, exit_price, realized_pnl, closed_at) -> int:
        row = self._trades.get(correlation_id)
        if not row:
            return 0
        row["status"] = status
        row["exit_price"] = exit_price
        row["realized_pnl"] = realized_pnl
        row["closed_at"] = closed_at
        return 1

    async def update_ai_analysis(self, correlation_id, model, analysis, error) -> None:
        row = self._trades.get(correlation_id)
        if row is None:
            return
        row["llm_model"] = model
        row["llm_analysis"] = analysis
        row["llm_error"] = error

    async def list_recent(self, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        rows = sorted(self._trades.values(), key=lambda r: r["id"], reverse=True)
        if status:
            rows = [r for r in rows if r["status"] == status]
        return rows[:limit]

    async def get_open_trade(self) -> dict[str, Any] | None:
        open_trades = await self.list_recent(limit=1, status="open")
        return open_trades[0] if open_trades else None

    async def get_by_correlation_id(self, correlation_id: str) -> dict[str, Any] | None:
        row = self._trades.get(correlation_id)
        return dict(row) if row else None

    async def ping(self) -> bool:
        return True
