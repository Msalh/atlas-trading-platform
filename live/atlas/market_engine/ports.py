"""
The MarketStateRepository port. Deliberately minimal for this Sprint - store,
get-latest, get-history - matching the in-memory-only, no-idempotency-guarantee,
no-staleness-policy scope this Sprint declared. Concurrency-safe idempotency
(the advisory-lock pattern already proven for TradeRepository) is Sprint 3's
job, against real Postgres, not guessed at here against an in-memory dict.

Modeled directly on atlas.repositories.base.TradeRepository's shape - a
Protocol, async methods - so a future concrete Postgres implementation slots in
the same way PostgresTradeRepository already does.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import MarketState


class IngestOutcome(str, Enum):
    STORED = "stored"
    DUPLICATE = "duplicate"


class MarketStateRepository(Protocol):
    async def ingest(self, state: MarketState, raw_payload: str) -> IngestOutcome:
        """Stores `state`, keyed by (symbol, timeframe, event_id), alongside
        the raw inbound payload it was translated from. Returns DUPLICATE
        without modifying anything if this exact (symbol, timeframe, event_id)
        has already been ingested - STORED otherwise.

        raw_payload (added in Sprint 3, when persistence first made "what do
        we store" a live question) exists because a canonical MarketState is a
        lossy summary of the wire payload it came from - the project
        architecture review's replayability requirement is explicit that the
        original payload must be recoverable too, the same way
        trades.raw_entry_payload already preserves the raw entry webhook body.
        It is not a MarketState field, deliberately - it is a persistence-
        boundary concern (traceability/audit), not a property of what the
        market did, so it stays out of the canonical domain model and is
        threaded through here instead, mirroring exactly how
        TradeRepository.claim_and_forward's own raw_body parameter is handled."""
        ...

    async def get_latest(self, symbol: Symbol, timeframe: Timeframe) -> Optional[MarketState]:
        """The stored MarketState with the greatest envelope.occurred_at for
        this (symbol, timeframe), or None if nothing has been ingested for it
        yet. Defined by occurred_at, not by ingestion order - a late-arriving
        event with an OLDER occurred_at never becomes "latest"."""
        ...

    async def get_history(
        self, symbol: Symbol, timeframe: Timeframe, limit: int = 100
    ) -> list[MarketState]:
        """Up to `limit` stored events for this (symbol, timeframe), ordered by
        envelope.occurred_at, most recent first."""
        ...

    async def get_range(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime, limit: int = 10000
    ) -> list[MarketState]:
        """Sprint 9 (Dataset Builder). Up to `limit` stored events for this
        (symbol, timeframe) with envelope.occurred_at in [start, end]
        (inclusive both ends), ordered CHRONOLOGICALLY ASCENDING - the
        opposite convention from get_history's most-recent-first, and
        deliberately so: get_history serves a "what just happened" UI query;
        get_range serves a bulk export, where ascending is the natural
        reading order for the resulting file.

        `limit`'s default and ceiling are materially higher than
        get_history's (100/1000) because bulk export is this method's actual
        purpose, not "the last few for a dashboard" - but it is still bounded:
        an unbounded range query is never allowed. If a real caller needs more
        than `limit` rows in one range, that is a concrete signal for
        pagination in a future Sprint, not something to solve speculatively
        here."""
        ...
