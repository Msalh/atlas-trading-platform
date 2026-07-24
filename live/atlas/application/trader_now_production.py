"""Production dependency assembly for the canonical TraderNow application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from atlas.application.trader_now import TraderNowApplication
from atlas.market_engine.ports import MarketStateRepository
from atlas.trader_now.contexts import MarketContextComposer
from atlas.trader_now.expected_close import (
    CmeExpectedCloseConfig,
    CmeMnqExpectedCloseProvider,
)
from atlas.trader_now.freshness import FreshnessPolicy
from atlas.trader_now.interpretations import SetupInterpretationComposer
from atlas.trader_now.market_data_resolution import ConfiguredMarketDataSeriesResolver
from atlas.trader_now.models import MarketDataProvider, MarketDataSeriesType
from atlas.trader_now.rules import RuleComposer
from atlas.trader_now.service import TraderNowService
from atlas.trader_now.setups import SetupComposer
from atlas.trader_now.strategies import StrategyComposer


@dataclass(frozen=True)
class TraderNowProductionConfig:
    product: str
    market_data_provider: MarketDataProvider
    market_data_series_symbol: str
    market_data_series_type: MarketDataSeriesType
    resolution_version: str
    effective_date: date
    calendar: CmeExpectedCloseConfig

    def __post_init__(self) -> None:
        if self.product != "MNQ":
            raise ValueError("TraderNow production product must be exactly 'MNQ'")
        if self.market_data_provider is not MarketDataProvider.TRADINGVIEW:
            raise ValueError("TraderNow production provider must be TradingView")
        if self.market_data_series_symbol != "MNQ1!":
            raise ValueError(
                "TraderNow production market-data series must be exactly 'MNQ1!'"
            )
        if self.market_data_series_type is not MarketDataSeriesType.CONTINUOUS:
            raise ValueError("TraderNow production series type must be continuous")
        if not self.resolution_version or not self.resolution_version.strip():
            raise ValueError("TraderNow contract resolution version must not be blank")

    @classmethod
    def from_settings(cls, settings) -> TraderNowProductionConfig:
        try:
            effective_date = date.fromisoformat(
                settings.trader_now_series_effective_date
            )
        except ValueError as error:
            raise ValueError(
                "TRADER_NOW_SERIES_EFFECTIVE_DATE must be an ISO date"
            ) from error
        calendar = CmeExpectedCloseConfig.from_json(
            version=settings.trader_now_calendar_version,
            holidays_json=settings.trader_now_holidays_json,
            early_closes_json=settings.trader_now_early_closes_json,
        )
        return cls(
            product=settings.trader_now_product,
            market_data_provider=MarketDataProvider(
                settings.trader_now_market_data_provider
            ),
            market_data_series_symbol=settings.trader_now_market_data_series_symbol,
            market_data_series_type=MarketDataSeriesType(
                settings.trader_now_market_data_series_type
            ),
            resolution_version=settings.trader_now_series_resolution_version,
            effective_date=effective_date,
            calendar=calendar,
        )


def utc_clock() -> datetime:
    return datetime.now(timezone.utc)


def build_trader_now_application(
    *,
    repository: MarketStateRepository,
    config: TraderNowProductionConfig,
) -> TraderNowApplication:
    """Build one application; owns no repository or shutdown resource."""
    return TraderNowApplication(
        repository=repository,
        market_data_series_resolver=ConfiguredMarketDataSeriesResolver(
            provider=config.market_data_provider,
            series_symbol=config.market_data_series_symbol,
            series_type=config.market_data_series_type,
            resolution_version=config.resolution_version,
            resolution_owner=f"operations:{config.effective_date.isoformat()}",
        ),
        clock=utc_clock,
        expected_close_provider=CmeMnqExpectedCloseProvider(config.calendar),
        freshness_policy=FreshnessPolicy(),
        rule_composer=RuleComposer(),
        setup_composer=SetupComposer(),
        context_composer=MarketContextComposer(),
        interpretation_composer=SetupInterpretationComposer(),
        strategy_composer=StrategyComposer(),
        trader_now_service=TraderNowService(),
    )
