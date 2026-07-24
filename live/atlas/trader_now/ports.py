"""Ports used by TraderNow's raw market acquisition boundary."""

from datetime import datetime
from typing import Protocol

from atlas.market_engine.ports import MarketStateRepository
from atlas.trader_now.models import MarketDataSeries


class MarketDataSeriesResolver(Protocol):
    """Resolve a product to the exact persisted observation series."""

    def resolve(self, product: str, at: datetime) -> MarketDataSeries: ...


class Clock(Protocol):
    def __call__(self) -> datetime: ...


class ExpectedCloseProvider(Protocol):
    """Return the expected latest close, or None when trading is not applicable."""

    def expected_close(
        self, symbol: str, timeframe: str, evaluation_time: datetime
    ) -> datetime | None: ...


class MarketInputDependencies(Protocol):
    @property
    def market_states(self) -> MarketStateRepository: ...

    @property
    def market_data_series_resolver(self) -> MarketDataSeriesResolver: ...

    @property
    def clock(self) -> Clock: ...
