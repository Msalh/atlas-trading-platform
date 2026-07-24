"""Sprint 12C Part 2 canonical TraderNow application-facade tests."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from atlas.application import InvalidCompositionTimeError, TraderNowApplication
from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_context.definitions import (
    RegimeClassifierDefinition,
    RegimeClassifierParams,
)
from atlas.market_engine.models import BarStatus, MarketState
from atlas.risk_assessment.service import assess_candidate_risk
from atlas.risk_projection import project_risk_assessment
from atlas.trader_now.contexts import MarketContextComposer
from atlas.trader_now.errors import UnsupportedTraderNowIdentityError
from atlas.trader_now.freshness import FreshnessPolicy
from atlas.trader_now.interpretations import SetupInterpretationComposer
from atlas.trader_now.market_data_resolution import ConfiguredMarketDataSeriesResolver
from atlas.trader_now.models import (
    AvailabilityStatus,
    MarketDataProvider,
    MarketDataSeriesType,
    StrategyAvailabilityStatus,
)
from atlas.trader_now.rules import RuleComposer
from atlas.trader_now.service import TraderNowService
from atlas.trader_now.setups import SetupComposer
from atlas.trader_now.strategies import StrategyComposer
from tests.risk_assessment_fixtures import (
    account_snapshot,
    assessment_input,
    candidate_trade_input,
    position_snapshot,
)

NOW = datetime(2026, 7, 24, 18, 0, tzinfo=timezone.utc)
CONTRACT = "MNQ1!"
SMALL_CLASSIFIER = RegimeClassifierDefinition(
    version="application-test-small.v1",
    params=RegimeClassifierParams(
        lookback_bars=10,
        min_bars_required=10,
        compressed_percentile=25,
        expanded_percentile=75,
    ),
)


def states(count: int = 288) -> list[MarketState]:
    first = NOW - timedelta(minutes=5 * count)
    values = []
    for index in range(count):
        occurred_at = first + timedelta(minutes=5 * index)
        close = 20_000.0 + index
        values.append(
            MarketState(
                envelope=Event(
                    event_id=f"event-{index}",
                    event_type="bar_closed",
                    source="fixture",
                    occurred_at=occurred_at,
                    received_at=occurred_at + timedelta(seconds=1),
                ),
                schema_version="1.0",
                symbol=Symbol(CONTRACT),
                timeframe=Timeframe.M5,
                bar_status=BarStatus.CLOSED,
                open=Price(close - 1, 0.25),
                high=Price(close + 10, 0.25),
                low=Price(close - 10, 0.25),
                close=Price(close, 0.25),
                volume=1000.0,
                volume_ratio=2.0,
                atr=10.0,
                previous_day_high=Price(close + 100, 0.25),
                previous_day_low=Price(close - 100, 0.25),
                overnight_high=Price(close + 80, 0.25),
                overnight_low=Price(close - 80, 0.25),
                vwap=close - 1,
                distance_from_vwap_points=1.0,
                session_name=Session.RTH,
                is_rth=True,
            )
        )
    return values


class Repository:
    def __init__(self, rows: list[MarketState]) -> None:
        self.rows = rows
        self.calls = 0

    async def get_history(self, symbol, timeframe, limit=100):
        self.calls += 1
        assert symbol == Symbol(CONTRACT)
        assert timeframe is Timeframe.M5
        assert limit == 288
        return list(reversed(self.rows))


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.value


class ExpectedClose:
    def __init__(self, value: datetime | None) -> None:
        self.value = value
        self.calls: list[tuple[str, str, datetime]] = []

    def expected_close(self, symbol, timeframe, evaluation_time):
        self.calls.append((symbol, timeframe, evaluation_time))
        return self.value


class CapturingStrategyComposer:
    def __init__(self) -> None:
        self.delegate = StrategyComposer()
        self.results = []

    def compose(self, **kwargs):
        result = self.delegate.compose(**kwargs)
        self.results.append(result)
        return result


class CapturingComposer:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.results = []

    def compose(self, *args, **kwargs):
        result = self.delegate.compose(*args, **kwargs)
        self.results.append(result)
        return result


class TrackingTraderNowService(TraderNowService):
    def __init__(self) -> None:
        self.risk_calls = []

    def compose_risk(self, result, *, strategy_decisions=(), risk_input=None):
        self.risk_calls.append((strategy_decisions, risk_input))
        return super().compose_risk(
            result,
            strategy_decisions=strategy_decisions,
            risk_input=risk_input,
        )


class OrderedComposer:
    def __init__(self, name, delegate, calls) -> None:
        self.name = name
        self.delegate = delegate
        self.calls = calls

    def compose(self, *args, **kwargs):
        self.calls.append(self.name)
        return self.delegate.compose(*args, **kwargs)


def application(
    *,
    rows: list[MarketState] | None = None,
    clock: Clock | None = None,
    expected_close: ExpectedClose | None = None,
    contract: str | None = CONTRACT,
    rule_composer=None,
    setup_composer=None,
    context_composer=None,
    interpretation_composer=None,
    strategy_composer=None,
    trader_now_service=None,
):
    repository = Repository(states() if rows is None else rows)
    injected_clock = clock or Clock()
    provider = expected_close or ExpectedClose(NOW - timedelta(minutes=5))
    app = TraderNowApplication(
        repository=repository,
        market_data_series_resolver=ConfiguredMarketDataSeriesResolver(
            provider=MarketDataProvider.TRADINGVIEW,
            series_symbol=contract,
            series_type=MarketDataSeriesType.CONTINUOUS,
            resolution_version="configured.v1",
            resolution_owner="operations",
        ),
        clock=injected_clock,
        expected_close_provider=provider,
        freshness_policy=FreshnessPolicy(),
        rule_composer=rule_composer or RuleComposer(),
        setup_composer=setup_composer or SetupComposer(),
        context_composer=context_composer or MarketContextComposer(),
        interpretation_composer=(
            interpretation_composer or SetupInterpretationComposer()
        ),
        strategy_composer=strategy_composer or StrategyComposer(),
        trader_now_service=trader_now_service or TraderNowService(),
    )
    return app, repository, injected_clock, provider


@pytest.mark.asyncio
async def test_complete_successful_canonical_composition():
    app, repository, clock, provider = application()

    result = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
    )

    assert result.identity.product == "MNQ"
    assert result.identity.symbol == "MNQ"
    assert result.identity.timeframe == "5m"
    assert result.identity.strategy_id == "displacement_volume_context"
    assert result.snapshot is None
    assert result.risk is None
    assert result.trust.status.value == "trusted"
    assert tuple(result.availability) == (
        "market",
        "market_history",
        "rules",
        "setups",
        "context",
        "interpretations",
        "strategy",
    )
    assert all(
        availability.status is AvailabilityStatus.AVAILABLE
        for availability in result.availability.values()
    )
    assert repository.calls == 1
    assert clock.calls == 1
    assert provider.calls == [(CONTRACT, "5m", NOW)]


@pytest.mark.asyncio
async def test_trader_now_retains_every_canonical_composition_projection():
    rules = CapturingComposer(RuleComposer())
    setups = CapturingComposer(SetupComposer())
    context = CapturingComposer(MarketContextComposer())
    interpretations = CapturingComposer(SetupInterpretationComposer())
    strategy = CapturingComposer(StrategyComposer())
    app, _, _, _ = application(
        rule_composer=rules,
        setup_composer=setups,
        context_composer=context,
        interpretation_composer=interpretations,
        strategy_composer=strategy,
    )

    result = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )

    assert result.market is not None
    assert result.source_trust is not None
    assert result.source_trust.freshness.latest_closed_at == (
        result.market.identity.latest_closed_at
    )
    assert result.rules is rules.results[-1]
    assert result.setups is setups.results[-1]
    assert result.context is context.results[-1]
    assert result.interpretations is interpretations.results[-1]
    assert result.strategy is strategy.results[-1]
    assert result.rules.output is result.rules.window[-1]
    assert result.setups.output is result.setups.window[-1]
    with pytest.raises(FrozenInstanceError):
        result.rules = rules.results[-1]


@pytest.mark.asyncio
async def test_explicit_as_of_reads_no_clock_and_reaches_all_time_stages():
    explicit = NOW + timedelta(minutes=5)
    clock = Clock()
    provider = ExpectedClose(NOW - timedelta(minutes=5))
    app, _, _, _ = application(clock=clock, expected_close=provider)

    result = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=explicit,
    )

    assert clock.calls == 0
    assert provider.calls == [(CONTRACT, "5m", explicit)]
    assert result.trust.policy_version == FreshnessPolicy().version


@pytest.mark.asyncio
async def test_canonical_derived_stages_are_invoked_in_order():
    calls = []
    app, _, _, _ = application(
        rule_composer=OrderedComposer("rules", RuleComposer(), calls),
        setup_composer=OrderedComposer("setups", SetupComposer(), calls),
        context_composer=OrderedComposer("context", MarketContextComposer(), calls),
        interpretation_composer=OrderedComposer(
            "interpretations", SetupInterpretationComposer(), calls
        ),
        strategy_composer=OrderedComposer("strategy", StrategyComposer(), calls),
    )

    await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )

    assert calls == ["rules", "setups", "context", "interpretations", "strategy"]


@pytest.mark.asyncio
async def test_naive_composition_time_is_rejected_before_repository_read():
    app, repository, _, _ = application()

    with pytest.raises(InvalidCompositionTimeError):
        await app.compose_latest(
            symbol="MNQ",
            timeframe="5m",
            strategy_id="displacement_volume_context",
            as_of=NOW.replace(tzinfo=None),
        )

    assert repository.calls == 0


@pytest.mark.asyncio
async def test_unsupported_identity_is_rejected_before_repository_read():
    app, repository, _, _ = application()

    with pytest.raises(
        UnsupportedTraderNowIdentityError,
        match="unsupported TraderNow strategy_id",
    ):
        await app.compose_latest(
            symbol="MNQ",
            timeframe="5m",
            strategy_id="unknown",
            as_of=NOW,
        )

    assert repository.calls == 0


@pytest.mark.asyncio
async def test_unresolved_series_and_missing_market_are_valid_results():
    unresolved, unresolved_repository, _, _ = application(contract=None)
    missing, missing_repository, _, _ = application(rows=[])

    unresolved_result = await unresolved.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )
    missing_result = await missing.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )

    assert (
        unresolved_result.availability["market"].status
        is AvailabilityStatus.UNAVAILABLE
    )
    assert unresolved_repository.calls == 0
    assert missing_result.availability["market"].status is AvailabilityStatus.NO_DATA
    assert (
        missing_result.availability["strategy"].status is AvailabilityStatus.UNAVAILABLE
    )
    assert missing_result.risk is None
    assert missing_repository.calls == 1


@pytest.mark.asyncio
async def test_insufficient_history_remains_a_valid_degraded_result():
    app, _, _, _ = application(
        rows=states(21),
        context_composer=MarketContextComposer(classifier=SMALL_CLASSIFIER),
    )

    result = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )

    assert result.availability["market"].status is AvailabilityStatus.AVAILABLE
    assert (
        result.availability["market_history"].status
        is AvailabilityStatus.INSUFFICIENT_DATA
    )
    assert result.availability["strategy"].status is AvailabilityStatus.AVAILABLE


@pytest.mark.asyncio
async def test_risk_is_omitted_without_calling_risk_composition():
    service = TrackingTraderNowService()
    app, _, _, _ = application(trader_now_service=service)

    result = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )

    assert result.risk is None
    assert service.risk_calls == []


@pytest.mark.asyncio
async def test_supplied_risk_uses_exact_canonical_strategy_tuple():
    strategy = CapturingStrategyComposer()
    service = TrackingTraderNowService()
    app, _, _, _ = application(
        strategy_composer=strategy,
        trader_now_service=service,
    )
    await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )
    decisions = strategy.results[-1].output
    assert (
        strategy.results[-1].availability.status is StrategyAvailabilityStatus.AVAILABLE
    )
    decision = decisions[0]
    risk_input = assessment_input(
        strategy_decision=decision,
        candidate=replace(
            candidate_trade_input(),
            strategy_id=decision.strategy_id,
            strategy_version=decision.strategy_version,
            context_fingerprint=decision.context_fingerprint,
            candidate_at=decision.occurred_at,
        ),
        evaluated_at=NOW,
        latest_closed_at=decision.occurred_at,
        account=replace(
            account_snapshot(),
            observed_at=NOW,
            received_at=NOW,
        ),
        positions=(
            replace(
                position_snapshot(),
                observed_at=NOW,
                received_at=NOW,
            ),
        ),
    )
    expected = project_risk_assessment(assess_candidate_risk(risk_input))

    result = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
        risk_input=risk_input,
    )

    assert result.risk == expected
    assert result.market is not None
    assert result.source_trust is not None
    assert result.strategy is strategy.results[-1]
    assert service.risk_calls[-1] == (strategy.results[-1].output, risk_input)


@pytest.mark.asyncio
async def test_repeated_composition_is_equal_and_inputs_remain_immutable():
    rows = states()
    app, _, _, _ = application(rows=rows)
    original_rows = tuple(rows)

    first = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )
    second = await app.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )

    assert first == second
    assert tuple(rows) == original_rows
    with pytest.raises(TypeError):
        first.availability["new"] = first.availability["market"]
