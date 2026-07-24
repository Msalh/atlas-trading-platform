"""Focused tests for Sprint 12B Part 2 raw MarketState acquisition."""

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.trader_now.errors import MarketDataSeriesResolutionError
from atlas.trader_now.market_data_resolution import ConfiguredMarketDataSeriesResolver
from atlas.trader_now.models import (
    AvailabilityStatus,
    MarketDataProvider,
    MarketDataSeriesType,
    MarketSourceReason,
)
from atlas.trader_now.service import (
    MAX_MARKET_STATES,
    MarketInputAcquirer,
    TraderNowService,
)

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
SERIES = "MNQ1!"


def _state(
    index: int,
    *,
    symbol: str = SERIES,
    timeframe: Timeframe = Timeframe.M5,
    status: BarStatus = BarStatus.CLOSED,
    occurred_at: datetime | None = None,
    received_at: datetime | None = None,
) -> MarketState:
    occurred = occurred_at or NOW - timedelta(minutes=5 * (MAX_MARKET_STATES - index))
    received = received_at or occurred + timedelta(seconds=1)
    return MarketState(
        envelope=Event(
            event_id=f"event-{index}",
            event_type="bar_closed",
            source="tradingview",
            occurred_at=occurred,
            received_at=received,
        ),
        schema_version="1.0",
        symbol=Symbol(symbol),
        timeframe=timeframe,
        bar_status=status,
    )


class StubRepository:
    def __init__(self, rows: list[MarketState], error: Exception | None = None) -> None:
        self.rows = rows
        self.error = error
        self.calls: list[tuple[Symbol, Timeframe, int]] = []

    async def get_history(
        self, symbol: Symbol, timeframe: Timeframe, limit: int = 100
    ) -> list[MarketState]:
        self.calls.append((symbol, timeframe, limit))
        if self.error is not None:
            raise self.error
        return self.rows


def _resolver(series: str | None = SERIES) -> ConfiguredMarketDataSeriesResolver:
    return ConfiguredMarketDataSeriesResolver(
        provider=MarketDataProvider.TRADINGVIEW,
        series_symbol=series,
        series_type=MarketDataSeriesType.CONTINUOUS,
        resolution_version="mnq_series.manual.v1",
        resolution_owner="operations",
    )


def _identity():
    return TraderNowService().validate_request(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
    )


def _acquirer(
    rows: list[MarketState],
    *,
    resolver: ConfiguredMarketDataSeriesResolver | None = None,
    error: Exception | None = None,
):
    repository = StubRepository(rows, error)
    acquirer = MarketInputAcquirer(
        repository=repository,
        market_data_series_resolver=resolver or _resolver(),
        clock=lambda: NOW,
    )
    return acquirer, repository


def test_initializer_exists_at_the_real_package_path():
    from atlas import trader_now

    assert trader_now.__file__ is not None
    assert trader_now.__file__.replace("\\", "/").endswith(
        "/atlas/trader_now/__init__.py"
    )


def test_successful_mnq_series_resolution_is_exact_versioned_and_owned():
    resolved = _resolver().resolve("MNQ", NOW)
    assert resolved.economic_instrument.symbol == "MNQ"
    assert resolved.provider is MarketDataProvider.TRADINGVIEW
    assert resolved.symbol == SERIES
    assert resolved.series_type is MarketDataSeriesType.CONTINUOUS
    assert resolved.resolved_at == NOW
    assert resolved.resolution_version == "mnq_series.manual.v1"
    assert resolved.resolution_owner == "operations"


def test_resolver_does_not_infer_an_unconfigured_series():
    with pytest.raises(MarketDataSeriesResolutionError):
        _resolver(None).resolve("MNQ", NOW)
    with pytest.raises(MarketDataSeriesResolutionError):
        _resolver().resolve("ES", NOW)


@pytest.mark.asyncio
async def test_unresolved_series_returns_typed_unavailability_without_repository_call():
    acquirer, repository = _acquirer([_state(1)], resolver=_resolver(None))
    result = await acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.UNAVAILABLE
    assert result.availability.reason_codes == (
        MarketSourceReason.UNRESOLVED_MARKET_DATA_SERIES,
    )
    assert repository.calls == []


@pytest.mark.asyncio
async def test_newest_first_repository_output_is_normalized_to_ascending():
    newest_first = [_state(index) for index in reversed(range(3))]
    acquirer, repository = _acquirer(newest_first)
    result = await acquirer.acquire(_identity())
    occurred = [state.envelope.occurred_at for state in result.states]
    assert occurred == sorted(occurred)
    assert repository.calls == [(Symbol(SERIES), Timeframe.M5, MAX_MARKET_STATES)]


@pytest.mark.asyncio
async def test_newer_forming_bar_is_excluded_and_latest_closed_anchors_input():
    closed = _state(1, occurred_at=NOW - timedelta(minutes=5))
    forming = _state(2, status=BarStatus.FORMING, occurred_at=NOW)
    acquirer, _ = _acquirer([forming, closed])
    result = await acquirer.acquire(_identity())
    assert result.states == (closed,)
    assert result.identity is not None
    assert result.identity.latest_closed_at == closed.envelope.occurred_at


@pytest.mark.asyncio
async def test_no_closed_bars_is_distinct_from_zero_rows():
    acquirer, _ = _acquirer([_state(1, status=BarStatus.FORMING)])
    no_closed = await acquirer.acquire(_identity())
    assert no_closed.availability.status == AvailabilityStatus.NO_DATA
    assert no_closed.availability.reason_codes == (MarketSourceReason.NO_CLOSED_BARS,)

    empty_acquirer, _ = _acquirer([])
    empty = await empty_acquirer.acquire(_identity())
    assert empty.availability.status == AvailabilityStatus.NO_DATA
    assert empty.availability.reason_codes == (MarketSourceReason.NO_DATA,)


@pytest.mark.asyncio
async def test_partial_history_keeps_market_available_but_history_insufficient():
    acquirer, _ = _acquirer([_state(index) for index in reversed(range(10))])
    result = await acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.AVAILABLE
    assert result.history_availability.status == AvailabilityStatus.INSUFFICIENT_DATA
    assert result.history_availability.reason_codes == (
        MarketSourceReason.INSUFFICIENT_HISTORY,
    )
    assert result.identity is not None
    assert result.identity.bar_count == 10


@pytest.mark.asyncio
async def test_exactly_288_closed_rows_has_complete_history_availability():
    acquirer, _ = _acquirer(
        [_state(index) for index in reversed(range(MAX_MARKET_STATES))]
    )
    result = await acquirer.acquire(_identity())
    assert len(result.states) == MAX_MARKET_STATES
    assert result.history_availability.status == AvailabilityStatus.AVAILABLE


@pytest.mark.asyncio
async def test_repository_over_return_is_bounded_to_latest_288():
    rows = [_state(index) for index in reversed(range(MAX_MARKET_STATES + 1))]
    acquirer, _ = _acquirer(rows)
    result = await acquirer.acquire(_identity())
    assert len(result.states) == MAX_MARKET_STATES
    assert result.states[0].envelope.event_id == "event-1"
    assert result.states[-1].envelope.event_id == f"event-{MAX_MARKET_STATES}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([_state(1, symbol="MNQZ6")], MarketSourceReason.IDENTITY_MISMATCH),
        ([_state(1, timeframe=Timeframe.M1)], MarketSourceReason.TIMEFRAME_MISMATCH),
    ],
)
async def test_identity_mismatches_are_invalid(rows, reason):
    acquirer, _ = _acquirer(rows)
    result = await acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.INVALID
    assert result.availability.reason_codes == (reason,)


@pytest.mark.asyncio
async def test_duplicate_occurred_at_timestamps_are_invalid():
    timestamp = NOW - timedelta(minutes=5)
    acquirer, _ = _acquirer(
        [
            _state(1, occurred_at=timestamp),
            _state(2, occurred_at=timestamp),
        ]
    )
    result = await acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.INVALID
    assert result.availability.reason_codes == (
        MarketSourceReason.DUPLICATE_TIMESTAMPS,
    )


@pytest.mark.asyncio
async def test_structurally_invalid_repository_input_is_rejected():
    repository = StubRepository(cast(list[MarketState], [object()]))
    acquirer = MarketInputAcquirer(
        repository=repository,
        market_data_series_resolver=_resolver(),
        clock=lambda: NOW,
    )
    result = await acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.INVALID
    assert result.availability.reason_codes == (
        MarketSourceReason.STRUCTURALLY_INVALID,
    )


@pytest.mark.asyncio
async def test_repository_failure_is_typed_unavailability():
    acquirer, _ = _acquirer([], error=RuntimeError("database details"))
    result = await acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.UNAVAILABLE
    assert result.availability.reason_codes == (MarketSourceReason.REPOSITORY_ERROR,)


@pytest.mark.asyncio
async def test_future_timestamp_tolerance_is_explicit():
    tolerated = _state(1, occurred_at=NOW + timedelta(seconds=5), received_at=NOW)
    tolerated_acquirer, _ = _acquirer([tolerated])
    assert (await tolerated_acquirer.acquire(_identity())).availability.status == (
        AvailabilityStatus.AVAILABLE
    )

    future = _state(
        1, occurred_at=NOW + timedelta(seconds=5, microseconds=1), received_at=NOW
    )
    future_acquirer, _ = _acquirer([future])
    result = await future_acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.INVALID
    assert result.availability.reason_codes == (MarketSourceReason.FUTURE_TIMESTAMP,)


@pytest.mark.asyncio
async def test_future_received_at_is_also_invalid():
    state = _state(
        1,
        occurred_at=NOW - timedelta(minutes=5),
        received_at=NOW + timedelta(seconds=6),
    )
    acquirer, _ = _acquirer([state])
    result = await acquirer.acquire(_identity())
    assert result.availability.status == AvailabilityStatus.INVALID
    assert result.availability.reason_codes == (MarketSourceReason.FUTURE_TIMESTAMP,)


@pytest.mark.asyncio
async def test_observation_timestamp_is_injected_and_source_identity_is_preserved():
    state = _state(1)
    acquirer, _ = _acquirer([state])
    result = await acquirer.acquire(_identity())
    assert result.availability.observed_at == NOW
    assert result.identity is not None
    assert result.identity.observed_at == NOW
    assert result.identity.economic_instrument.symbol == "MNQ"
    assert result.identity.market_data_series.symbol == SERIES
    assert result.identity.listed_instrument is None
    assert result.identity.source_schema_versions == ("1.0",)
    assert result.identity.source_events[0].event_id == state.envelope.event_id
    assert result.identity.source_events[0].received_at == state.envelope.received_at
