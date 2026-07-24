"""Optional real-Postgres certification for the TraderNow read path."""

from datetime import date

import pytest

from atlas.application.trader_now_production import (
    TraderNowProductionConfig,
    build_trader_now_application,
)
from atlas.trader_now.expected_close import CmeExpectedCloseConfig
from atlas.trader_now.models import MarketDataProvider, MarketDataSeriesType


@pytest.mark.asyncio
async def test_real_postgres_repository_no_data_is_a_valid_read_only_result(
    market_engine_repo,
):
    application = build_trader_now_application(
        repository=market_engine_repo,
        config=TraderNowProductionConfig(
            product="MNQ",
            market_data_provider=MarketDataProvider.TRADINGVIEW,
            market_data_series_symbol="MNQ1!",
            market_data_series_type=MarketDataSeriesType.CONTINUOUS,
            resolution_version="integration.v1",
            effective_date=date(2026, 6, 15),
            calendar=CmeExpectedCloseConfig("integration-calendar.v1", frozenset(), {}),
        ),
    )

    result = await application.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
    )

    assert result.availability["market"].status.value == "no_data"
    assert result.risk is None
