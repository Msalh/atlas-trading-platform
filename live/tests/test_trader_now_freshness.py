"""Sprint 12B Part 3 freshness and raw-source trust tests."""

from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.trader_now.freshness import FreshnessPolicy, FreshnessService
from atlas.trader_now.models import (
    AvailabilityStatus,
    FreshnessReason,
    FreshnessStatus,
    MarketInputIdentity,
    MarketInputWindow,
    MarketSourceAvailability,
    MarketSourceReason,
    EconomicInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    SourceEventIdentity,
    StructuralValidityStatus,
    TrustStatus,
)
from atlas.trader_now.trust import project_raw_source_trust

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
EXPECTED = NOW - timedelta(minutes=5)


class StubExpectedClose:
    def __init__(
        self,
        value: datetime | None,
        error: Exception | None = None,
    ) -> None:
        self.value = value
        self.error = error
        self.calls: list[tuple[str, str, datetime]] = []

    def expected_close(
        self, symbol: str, timeframe: str, evaluation_time: datetime
    ) -> datetime | None:
        self.calls.append((symbol, timeframe, evaluation_time))
        if self.error is not None:
            raise self.error
        return self.value


class StubClock:
    def __init__(self, value: datetime) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return self.value


def _service(
    expected: datetime | None = EXPECTED,
    *,
    clock: StubClock | None = None,
    policy: FreshnessPolicy | None = None,
    error: Exception | None = None,
) -> tuple[FreshnessService, StubExpectedClose, StubClock]:
    provider = StubExpectedClose(expected, error)
    injected_clock = clock or StubClock(NOW)
    return (
        FreshnessService(
            expected_close_provider=provider,
            clock=injected_clock,
            policy=policy or FreshnessPolicy(),
        ),
        provider,
        injected_clock,
    )


@pytest.mark.parametrize(
    ("lateness_seconds", "expected_status"),
    [
        (0, FreshnessStatus.CURRENT),
        (90, FreshnessStatus.CURRENT),
        (90.001, FreshnessStatus.DELAYED),
        (390, FreshnessStatus.DELAYED),
        (390.001, FreshnessStatus.STALE),
    ],
)
def test_default_policy_boundaries(lateness_seconds, expected_status):
    service, _, _ = _service()
    result = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=EXPECTED - timedelta(seconds=lateness_seconds),
    )
    assert result.status == expected_status
    assert result.lateness_seconds == pytest.approx(lateness_seconds)


def test_expected_close_variation_changes_lateness_not_clock():
    later_expected = EXPECTED + timedelta(minutes=5)
    service, provider, clock = _service(later_expected)
    result = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=EXPECTED,
    )
    assert result.status == FreshnessStatus.DELAYED
    assert result.lateness_seconds == 300
    assert provider.calls == [("MNQU6", "5m", NOW)]
    assert clock.calls == 1


def test_bar_newer_than_expected_close_is_current_with_zero_lateness():
    service, _, _ = _service()
    result = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=EXPECTED + timedelta(seconds=30),
    )
    assert result.status == FreshnessStatus.CURRENT
    assert result.lateness_seconds == 0


def test_latest_bar_future_timestamp_honors_clock_skew_tolerance():
    service, _, _ = _service()
    tolerated = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=NOW + timedelta(seconds=5),
    )
    assert tolerated.status == FreshnessStatus.CURRENT

    invalid = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=NOW + timedelta(seconds=5, microseconds=1),
    )
    assert invalid.status == FreshnessStatus.INVALID
    assert invalid.reason_codes == (FreshnessReason.LATEST_BAR_IN_FUTURE,)


def test_expected_close_future_clock_skew_is_invalid():
    service, _, _ = _service(NOW + timedelta(seconds=6))
    result = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=NOW,
    )
    assert result.status == FreshnessStatus.INVALID
    assert result.reason_codes == (FreshnessReason.EXPECTED_CLOSE_IN_FUTURE,)


def test_no_latest_bar_is_unavailable():
    service, _, _ = _service()
    result = service.classify(symbol="MNQU6", timeframe="5m", latest_closed_at=None)
    assert result.status == FreshnessStatus.UNAVAILABLE
    assert result.reason_codes == (FreshnessReason.NO_LATEST_CLOSED_BAR,)


def test_expected_close_none_is_not_applicable():
    service, _, _ = _service(None)
    result = service.classify(symbol="MNQU6", timeframe="5m", latest_closed_at=EXPECTED)
    assert result.status == FreshnessStatus.NOT_APPLICABLE
    assert result.reason_codes == (FreshnessReason.EXPECTED_CLOSE_NOT_APPLICABLE,)


def test_expected_close_failure_is_unavailable_without_leaking_exception():
    service, _, _ = _service(error=RuntimeError("calendar details"))
    result = service.classify(symbol="MNQU6", timeframe="5m", latest_closed_at=EXPECTED)
    assert result.status == FreshnessStatus.UNAVAILABLE
    assert result.reason_codes == (FreshnessReason.EXPECTED_CLOSE_UNAVAILABLE,)


def test_policy_override_controls_classification():
    policy = FreshnessPolicy(
        version="test.v2",
        current_lateness=timedelta(seconds=10),
        stale_lateness=timedelta(seconds=20),
        future_skew_tolerance=timedelta(seconds=1),
    )
    service, _, _ = _service(policy=policy)
    result = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=EXPECTED - timedelta(seconds=15),
    )
    assert result.status == FreshnessStatus.DELAYED
    assert result.policy_version == "test.v2"


@pytest.mark.parametrize(
    "policy",
    [
        FreshnessPolicy,
    ],
)
def test_policy_validation_is_explicit(policy):
    with pytest.raises(ValueError, match="greater"):
        policy(
            current_lateness=timedelta(seconds=90),
            stale_lateness=timedelta(seconds=90),
        )
    with pytest.raises(ValueError, match="future_skew"):
        policy(future_skew_tolerance=timedelta(seconds=-1))


def test_naive_clock_is_rejected():
    service, _, _ = _service(clock=StubClock(datetime(2026, 7, 24, 12, 0)))
    with pytest.raises(ValueError, match="timezone-aware"):
        service.classify(symbol="MNQU6", timeframe="5m", latest_closed_at=EXPECTED)


def _available_market_input() -> MarketInputWindow:
    state = MarketState(
        envelope=Event(
            event_id="event-1",
            event_type="bar_closed",
            source="tradingview",
            occurred_at=EXPECTED,
            received_at=EXPECTED + timedelta(seconds=1),
        ),
        schema_version="1.0",
        symbol=Symbol("MNQU6"),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
    )
    source = SourceEventIdentity(
        event_id="event-1",
        event_type="bar_closed",
        source="tradingview",
        schema_version="1.0",
        occurred_at=EXPECTED,
        received_at=EXPECTED + timedelta(seconds=1),
    )
    identity = MarketInputIdentity(
        economic_instrument=EconomicInstrument("MNQ"),
        market_data_series=MarketDataSeries(
            economic_instrument=EconomicInstrument("MNQ"),
            provider=MarketDataProvider.TRADINGVIEW,
            symbol="MNQ1!",
            series_type=MarketDataSeriesType.CONTINUOUS,
            resolved_at=NOW,
            resolution_version="manual.v1",
            resolution_owner="operations",
        ),
        listed_instrument=None,
        timeframe="5m",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        latest_closed_at=EXPECTED,
        observed_at=NOW,
        bar_count=1,
        source_events=(source,),
        source_schema_versions=("1.0",),
    )
    available = MarketSourceAvailability(AvailabilityStatus.AVAILABLE, (), NOW)
    return MarketInputWindow(
        availability=available,
        history_availability=MarketSourceAvailability(
            AvailabilityStatus.INSUFFICIENT_DATA,
            (MarketSourceReason.INSUFFICIENT_HISTORY,),
            NOW,
        ),
        identity=identity,
        states=(state,),
    )


def test_trust_aggregation_keeps_dimensions_separate():
    market_input = _available_market_input()
    service, _, _ = _service()
    current = service.classify(
        symbol="MNQU6", timeframe="5m", latest_closed_at=EXPECTED
    )
    trust = project_raw_source_trust(market_input=market_input, freshness=current)
    assert trust.availability == AvailabilityStatus.AVAILABLE
    assert trust.structural_validity == StructuralValidityStatus.VALID
    assert trust.freshness.status == FreshnessStatus.CURRENT
    assert trust.overall == TrustStatus.TRUSTED


@pytest.mark.parametrize(
    ("lateness", "overall"),
    [
        (timedelta(seconds=100), TrustStatus.DEGRADED),
        (timedelta(seconds=400), TrustStatus.UNAVAILABLE),
    ],
)
def test_trust_aggregation_is_deterministic_for_delayed_and_stale(lateness, overall):
    service, _, _ = _service()
    freshness = service.classify(
        symbol="MNQU6",
        timeframe="5m",
        latest_closed_at=EXPECTED - lateness,
    )
    trust = project_raw_source_trust(
        market_input=_available_market_input(), freshness=freshness
    )
    assert trust.overall == overall


def test_invalid_structural_input_overrides_current_freshness():
    invalid_availability = MarketSourceAvailability(
        AvailabilityStatus.INVALID,
        (MarketSourceReason.STRUCTURALLY_INVALID,),
        NOW,
    )
    invalid_input = MarketInputWindow(
        availability=invalid_availability,
        history_availability=invalid_availability,
        identity=None,
    )
    service, _, _ = _service()
    current = service.classify(
        symbol="MNQU6", timeframe="5m", latest_closed_at=EXPECTED
    )
    trust = project_raw_source_trust(market_input=invalid_input, freshness=current)
    assert trust.structural_validity == StructuralValidityStatus.INVALID
    assert trust.freshness.status == FreshnessStatus.CURRENT
    assert trust.overall == TrustStatus.UNAVAILABLE


def test_not_applicable_freshness_does_not_become_trusted():
    service, _, _ = _service(None)
    freshness = service.classify(
        symbol="MNQU6", timeframe="5m", latest_closed_at=EXPECTED
    )
    trust = project_raw_source_trust(
        market_input=_available_market_input(), freshness=freshness
    )
    assert trust.freshness.status == FreshnessStatus.NOT_APPLICABLE
    assert trust.overall == TrustStatus.UNAVAILABLE
