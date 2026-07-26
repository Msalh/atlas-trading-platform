"""Canonical production-facing orchestration of the TraderNow pipeline."""

import logging
from datetime import datetime
from enum import Enum

from atlas.application.errors import InvalidCompositionTimeError
from atlas.market_engine.ports import MarketStateRepository
from atlas.risk_assessment.models import RiskAssessmentInput
from atlas.trader_now.analysis_window import latest_contiguous_analysis_window
from atlas.trader_now.contexts import MarketContextComposer
from atlas.trader_now.freshness import FreshnessPolicy, FreshnessService
from atlas.trader_now.interpretations import SetupInterpretationComposer
from atlas.trader_now.models import (
    Availability,
    AvailabilityStatus,
    DecisionNotImplemented,
    MarketInputWindow,
    TraderNow,
    Trust,
)
from atlas.trader_now.ports import (
    Clock,
    ExpectedCloseProvider,
    MarketDataSeriesResolver,
)
from atlas.trader_now.rules import RuleComposer
from atlas.trader_now.service import MarketInputAcquirer, TraderNowService
from atlas.trader_now.setups import SetupComposer
from atlas.trader_now.strategies import StrategyComposer
from atlas.trader_now.trust import project_raw_source_trust

logger = logging.getLogger(__name__)


class TraderNowApplication:
    """Compose one immutable TraderNow result from explicit dependencies."""

    def __init__(
        self,
        *,
        repository: MarketStateRepository,
        market_data_series_resolver: MarketDataSeriesResolver,
        clock: Clock,
        expected_close_provider: ExpectedCloseProvider,
        freshness_policy: FreshnessPolicy,
        rule_composer: RuleComposer,
        setup_composer: SetupComposer,
        context_composer: MarketContextComposer,
        interpretation_composer: SetupInterpretationComposer,
        strategy_composer: StrategyComposer,
        trader_now_service: TraderNowService,
    ) -> None:
        self._repository = repository
        self._market_data_series_resolver = market_data_series_resolver
        self._clock = clock
        self._expected_close_provider = expected_close_provider
        self._freshness_policy = freshness_policy
        self._rule_composer = rule_composer
        self._setup_composer = setup_composer
        self._context_composer = context_composer
        self._interpretation_composer = interpretation_composer
        self._strategy_composer = strategy_composer
        self._trader_now_service = trader_now_service

    async def compose_latest(
        self,
        *,
        symbol: str,
        timeframe: str,
        strategy_id: str,
        as_of: datetime | None = None,
        risk_input: RiskAssessmentInput | None = None,
    ) -> TraderNow:
        effective_at = as_of if as_of is not None else self._clock()
        if effective_at.tzinfo is None or effective_at.utcoffset() is None:
            raise InvalidCompositionTimeError("composition time must be timezone-aware")

        def fixed_clock() -> datetime:
            return effective_at

        identity = self._trader_now_service.validate_request(
            symbol=symbol,
            timeframe=timeframe,
            strategy_id=strategy_id,
        )
        market_input = await MarketInputAcquirer(
            repository=self._repository,
            market_data_series_resolver=self._market_data_series_resolver,
            clock=fixed_clock,
        ).acquire(identity)

        freshness_symbol = (
            market_input.identity.market_data_series.symbol
            if market_input.identity is not None
            else identity.symbol
        )
        latest_closed_at = (
            market_input.identity.latest_closed_at
            if market_input.identity is not None
            else None
        )
        freshness = FreshnessService(
            expected_close_provider=self._expected_close_provider,
            clock=fixed_clock,
            policy=self._freshness_policy,
        ).classify(
            symbol=freshness_symbol,
            timeframe=identity.timeframe,
            latest_closed_at=latest_closed_at,
        )
        raw_trust = project_raw_source_trust(
            market_input=market_input,
            freshness=freshness,
        )

        analysis_market_input = self._latest_contiguous_analysis_window(market_input)
        rules = self._rule_composer.compose(analysis_market_input)
        setups = self._setup_composer.compose(
            market_input=analysis_market_input,
            rules=rules,
        )
        context = self._context_composer.compose(market_input)
        interpretations = self._interpretation_composer.compose(
            rules=rules,
            setups=setups,
        )
        strategy = self._strategy_composer.compose(
            market_input=market_input,
            rules=rules,
            setups=setups,
            context=context,
            interpretations=interpretations,
        )

        result = TraderNow(
            snapshot=None,
            identity=identity,
            trust=Trust(
                status=raw_trust.overall,
                policy_version=freshness.policy_version,
                reason_codes=raw_trust.reason_codes,
            ),
            availability={
                "market": self._availability(
                    market_input.availability.status,
                    market_input.availability.reason_codes,
                ),
                "market_history": self._availability(
                    market_input.history_availability.status,
                    market_input.history_availability.reason_codes,
                ),
                "rules": self._availability(
                    rules.availability.status,
                    rules.availability.reason_codes,
                ),
                "setups": self._availability(
                    setups.availability.status,
                    setups.availability.reason_codes,
                ),
                "context": self._availability(
                    context.availability.status,
                    context.availability.reason_codes,
                ),
                "interpretations": self._availability(
                    interpretations.availability.status,
                    interpretations.availability.reason_codes,
                ),
                "strategy": self._availability(
                    strategy.availability.status,
                    strategy.availability.reason_codes,
                ),
            },
            decision=DecisionNotImplemented(),
            market=market_input,
            source_trust=raw_trust,
            rules=rules,
            setups=setups,
            context=context,
            interpretations=interpretations,
            strategy=strategy,
        )
        if risk_input is None:
            return result
        return self._trader_now_service.compose_risk(
            result,
            strategy_decisions=strategy.output,
            risk_input=risk_input,
        )

    @staticmethod
    def _latest_contiguous_analysis_window(
        market_input: MarketInputWindow,
    ) -> MarketInputWindow:
        """Select the latest cadence-valid suffix for Rule/Setup analysis.

        The returned view reuses the canonical immutable MarketState objects
        and the complete input identity. The original 288-observation window
        remains untouched for market evidence and frozen Context semantics.
        """
        if (
            market_input.availability.status != AvailabilityStatus.AVAILABLE
            or market_input.identity is None
            or not market_input.states
        ):
            return market_input

        analysis_window = latest_contiguous_analysis_window(market_input)
        if len(analysis_window.states) != len(market_input.states):
            logger.info(
                "TraderNow analysis window segmented",
                extra={"diagnostic_category": "market_window_gap"},
            )
        return analysis_window

    @staticmethod
    def _availability(
        status: Enum,
        reasons: tuple[Enum, ...],
    ) -> Availability:
        status_value = str(status.value)
        normalized = (
            AvailabilityStatus.UNAVAILABLE
            if status_value == "unavailable_due_to_dependency"
            else AvailabilityStatus(status_value)
        )
        return Availability(
            status=normalized,
            reason_codes=tuple(str(reason.value) for reason in reasons),
        )
