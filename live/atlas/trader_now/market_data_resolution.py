"""Configured market-data series resolution without contract inference."""

from datetime import datetime

from atlas.trader_now.errors import MarketDataSeriesResolutionError
from atlas.trader_now.identity import SUPPORTED_PRODUCT
from atlas.trader_now.models import (
    EconomicInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
)


class ConfiguredMarketDataSeriesResolver:
    """Resolve MNQ to one explicitly configured persisted observation series."""

    def __init__(
        self,
        *,
        provider: MarketDataProvider,
        series_symbol: str | None,
        series_type: MarketDataSeriesType,
        resolution_version: str,
        resolution_owner: str,
    ) -> None:
        self._provider = provider
        self._series_symbol = series_symbol
        self._series_type = series_type
        self._resolution_version = resolution_version
        self._resolution_owner = resolution_owner

    def resolve(self, product: str, at: datetime) -> MarketDataSeries:
        if product != SUPPORTED_PRODUCT or not self._series_symbol:
            raise MarketDataSeriesResolutionError(
                f"no persisted market-data series configured for product {product!r}"
            )
        return MarketDataSeries(
            economic_instrument=EconomicInstrument(product),
            provider=self._provider,
            symbol=self._series_symbol,
            series_type=self._series_type,
            resolved_at=at,
            resolution_version=self._resolution_version,
            resolution_owner=self._resolution_owner,
        )
