"""Production configuration, assembly, and read-only dependency tests."""

from dataclasses import FrozenInstanceError
from datetime import date, timezone

import pytest

from atlas.application.trader_now_production import (
    TraderNowProductionConfig,
    build_trader_now_application,
    utc_clock,
)
from atlas.trader_now.expected_close import CmeExpectedCloseConfig
from atlas.trader_now.models import MarketDataProvider, MarketDataSeriesType


class ReadOnlyRepository:
    def __init__(self):
        self.reads = 0

    async def get_history(self, symbol, timeframe, limit=100):
        self.reads += 1
        return []

    async def ingest(self, *args, **kwargs):
        raise AssertionError("TraderNow must never call ingest")


def config(series="MNQ1!"):
    return TraderNowProductionConfig(
        product="MNQ",
        market_data_provider=MarketDataProvider.TRADINGVIEW,
        market_data_series_symbol=series,
        market_data_series_type=MarketDataSeriesType.CONTINUOUS,
        resolution_version="tradingview-mnq1.v1",
        effective_date=date(2026, 6, 15),
        calendar=CmeExpectedCloseConfig("calendar.v1", frozenset(), {}),
    )


@pytest.mark.parametrize(
    "series",
    ["", "MNQ", "MNQU6", "ES1!", "MNQTEST", "mnq1!"],
)
def test_invalid_market_data_series_configuration_fails(series):
    with pytest.raises(ValueError):
        config(series)


def test_production_config_is_immutable():
    value = config()
    with pytest.raises(FrozenInstanceError):
        value.market_data_series_symbol = "MNQU6"


def test_utc_clock_is_aware_and_utc():
    value = utc_clock()
    assert value.tzinfo is timezone.utc
    assert value.utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_factory_builds_no_risk_placeholders_and_uses_one_read():
    repository = ReadOnlyRepository()
    application = build_trader_now_application(
        repository=repository,
        config=config(),
    )

    result = await application.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
    )

    assert result.risk is None
    assert result.availability["market"].status.value == "no_data"
    assert repository.reads == 1
