"""
The TradeRepository interface. Every piece of business logic (the webhook handler, the
background AI task) depends on this Protocol, never on a concrete database driver -
that's what lets the Postgres implementation be swapped for an in-memory test double
in unit tests, and lets a future implementation (a different database, a sharded
version, etc.) be added later without touching any calling code.
"""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Protocol

ForwardResult = tuple[bool, Optional[int], Optional[str]]  # (forwarded, status_code, error)
ForwardFn = Callable[[], Awaitable[ForwardResult]]


@dataclass
class ClaimResult:
    forwarded: bool
    pmt_status_code: Optional[int]
    pmt_error: Optional[str]
    duplicate: bool  # True if this correlation_id was already forwarded previously - `forward` was never called


class TradeRepository(Protocol):
    async def claim_and_forward(
        self, correlation_id: str, entry: dict[str, Any], raw_body: str, forward: ForwardFn,
    ) -> ClaimResult:
        """
        Atomically resolves idempotency + concurrency safety: if this correlation_id
        was already *successfully* forwarded, `forward` is never called and the
        existing row is left untouched (ClaimResult.duplicate=True). Otherwise
        `forward` is invoked exactly once - even if two requests for the same
        correlation_id arrive concurrently - and its result is persisted alongside the
        entry fields. A previously *failed* forward attempt is not treated as a
        duplicate: `forward` is called again, allowing a genuine retry.
        """
        ...

    async def update_price(
        self, correlation_id: str, current_price: Optional[float], unrealized_pnl: Optional[float], updated_at: str,
    ) -> int:
        """Applies a price_update event. Returns the number of rows matched (0 if no
        trade exists yet for this correlation_id). Must never touch pmt_forwarded/
        pmt_status_code/pmt_error."""
        ...

    async def update_exit(
        self, correlation_id: str, status: str, exit_price: Optional[float], realized_pnl: Optional[float], closed_at: str,
    ) -> int:
        """Applies an exit event. Returns the number of rows matched (0 if no trade
        exists yet for this correlation_id). Must never touch pmt_forwarded/
        pmt_status_code/pmt_error."""
        ...

    async def add_ai_note(
        self,
        *,
        trade_correlation_id: Optional[str],
        note_type: str,
        model: Optional[str],
        content: Optional[str],
        error: Optional[str],
        score: Optional[int] = None,
        score_label: Optional[str] = None,
        expected_r: Optional[float] = None,
        historical_win_rate_pct: Optional[float] = None,
        similar_trade_count: Optional[int] = None,
        factors: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Records one AI pass - an entry score, a post-trade review, or a
        daily/weekly report (trade_correlation_id is None for report types, which
        summarize many trades rather than belonging to one). Commentary only - never
        called on the request-critical path. Returns the stored row.

        expected_r/historical_win_rate_pct/similar_trade_count/factors (Sprint 7) are
        only meaningful for note_type='entry_score' - the deterministic, historically-
        grounded numbers atlas/intelligence.py computed *before* Claude was ever
        called, not anything Claude produced itself. `factors` is a plain Python list
        of dicts in and out - implementations own how (or whether) they serialize it
        for storage, callers never see a JSON string.
        """
        ...

    async def list_ai_notes(
        self,
        *,
        trade_correlation_id: Optional[str] = None,
        note_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Most recent first. Filters are AND-ed together; both are optional."""
        ...

    async def list_recent(self, limit: int = 100, status: Optional[str] = None) -> list[dict[str, Any]]:
        """Most recent trades first. `status`, if given, filters to exactly that
        lifecycle status ('open' / 'won' / 'lost')."""
        ...

    async def get_open_trade(self) -> Optional[dict[str, Any]]:
        """The current open position, if any (most recent trade with status='open').
        None if flat. This strategy only ever holds one position at a time, but the
        query is written to be correct even if that assumption is ever relaxed."""
        ...

    async def get_by_correlation_id(self, correlation_id: str) -> Optional[dict[str, Any]]:
        ...

    async def ping(self) -> bool:
        """Raises if the underlying database is not reachable; used by /health."""
        ...
