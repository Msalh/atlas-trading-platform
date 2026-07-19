"""
In-memory MarketStateRepository - this Sprint's only implementation. Not a test
double standing in for a "real" one (there is no other one yet, per this
Sprint's declared scope) - Sprint 3 adds a Postgres implementation of the exact
same MarketStateRepository Protocol, at which point this class becomes the test
double the way InMemoryTradeRepository already is for TradeRepository.
"""
import asyncio
from datetime import datetime
from typing import Optional

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import MarketState
from atlas.market_engine.ports import IngestOutcome


class InMemoryMarketStateRepository:
    def __init__(self) -> None:
        # keyed by (symbol.ticker, timeframe.value, event_id) - mirrors the
        # dedup key this Sprint's port documents.
        self._store: dict[tuple[str, str, str], MarketState] = {}
        self._raw_payloads: dict[tuple[str, str, str], str] = {}
        self._lock = asyncio.Lock()

    async def ingest(self, state: MarketState, raw_payload: str) -> IngestOutcome:
        key = (state.symbol.ticker, state.timeframe.value, state.envelope.event_id)
        async with self._lock:
            if key in self._store:
                return IngestOutcome.DUPLICATE
            self._store[key] = state
            self._raw_payloads[key] = raw_payload
            return IngestOutcome.STORED

    def raw_payload_for(self, symbol: Symbol, timeframe: Timeframe, event_id: str) -> Optional[str]:
        """Test/inspection helper only - not part of the MarketStateRepository
        Protocol. Lets tests assert the raw payload was actually preserved
        without needing a real database round-trip to check it."""
        return self._raw_payloads.get((symbol.ticker, timeframe.value, event_id))

    async def get_latest(self, symbol: Symbol, timeframe: Timeframe) -> Optional[MarketState]:
        matches = self._matching(symbol, timeframe)
        if not matches:
            return None
        return max(matches, key=lambda s: s.envelope.occurred_at)

    async def get_history(
        self, symbol: Symbol, timeframe: Timeframe, limit: int = 100
    ) -> list[MarketState]:
        matches = self._matching(symbol, timeframe)
        matches.sort(key=lambda s: s.envelope.occurred_at, reverse=True)
        return matches[:limit]

    async def get_range(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime, limit: int = 10000
    ) -> list[MarketState]:
        matches = [
            s for s in self._matching(symbol, timeframe)
            if start <= s.envelope.occurred_at <= end
        ]
        matches.sort(key=lambda s: s.envelope.occurred_at)
        return matches[:limit]

    def _matching(self, symbol: Symbol, timeframe: Timeframe) -> list[MarketState]:
        return [
            s for s in self._store.values()
            if s.symbol == symbol and s.timeframe == timeframe
        ]
