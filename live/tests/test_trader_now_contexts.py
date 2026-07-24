"""Sprint 12B Part 6 tests for canonical Market Context composition."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from inspect import signature
from typing import cast
from zoneinfo import ZoneInfo

from atlas.core.events import Event
from atlas.core.primitives import Session, Symbol, Timeframe
from atlas.market_context.definitions import (
    CME_RTH_V1,
    RegimeClassifierDefinition,
    RegimeClassifierParams,
)
from atlas.market_context.models import ContextQuality, MarketContext
from atlas.market_context.service import build_market_context
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.service import build_replay_output_window
from atlas.trader_now.contexts import MarketContextComposer
from atlas.trader_now.models import (
    AvailabilityStatus,
    ContextAvailabilityReason,
    ContextAvailabilityStatus,
    MarketInputIdentity,
    MarketInputWindow,
    MarketSourceAvailability,
    MarketSourceReason,
    EconomicInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    SourceEventIdentity,
)

_CENTRAL = ZoneInfo("America/Chicago")
NOW = datetime(2026, 7, 24, 18, 0, tzinfo=timezone.utc)
CONTRACT = "MNQU6"
_SMALL = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=10,
        min_bars_required=10,
        compressed_percentile=25,
        expanded_percentile=75,
    ),
)


def _mid_session() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=_CENTRAL).astimezone(timezone.utc)


def _state(
    index: int,
    occurred_at: datetime,
    *,
    symbol: str = CONTRACT,
    timeframe: Timeframe = Timeframe.M5,
    session_name: Session | None = Session.RTH,
    is_rth: bool | None = True,
) -> MarketState:
    return MarketState(
        envelope=Event(
            event_id=f"event-{index}",
            event_type="bar_closed",
            source="test",
            occurred_at=occurred_at,
            received_at=occurred_at + timedelta(seconds=1),
        ),
        schema_version="1.0",
        symbol=Symbol(symbol),
        timeframe=timeframe,
        bar_status=BarStatus.CLOSED,
        atr=1.0 + index,
        session_name=session_name,
        is_rth=is_rth,
    )


def _states(
    count: int = 10,
    *,
    session_name: Session | None = Session.RTH,
    is_rth: bool | None = True,
) -> list[MarketState]:
    latest = _mid_session()
    first = latest - timedelta(minutes=5 * (count - 1))
    return [
        _state(
            index,
            first + timedelta(minutes=5 * index),
            session_name=session_name,
            is_rth=is_rth,
        )
        for index in range(count)
    ]


def _market_input(states: list[MarketState]) -> MarketInputWindow:
    latest = states[-1]
    source_events = tuple(
        SourceEventIdentity(
            event_id=state.envelope.event_id,
            event_type=state.envelope.event_type,
            source=state.envelope.source,
            schema_version=state.schema_version,
            occurred_at=state.envelope.occurred_at,
            received_at=state.envelope.received_at,
        )
        for state in states
    )
    identity = MarketInputIdentity(
        economic_instrument=EconomicInstrument("MNQ"),
        market_data_series=MarketDataSeries(
            economic_instrument=EconomicInstrument("MNQ"),
            provider=MarketDataProvider.TRADINGVIEW,
            symbol=CONTRACT,
            series_type=MarketDataSeriesType.CONTINUOUS,
            resolved_at=NOW,
            resolution_version="manual.v1",
            resolution_owner="operations",
        ),
        listed_instrument=None,
        timeframe="5m",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        latest_closed_at=latest.envelope.occurred_at,
        observed_at=NOW,
        bar_count=len(states),
        source_events=source_events,
        source_schema_versions=("1.0",),
    )
    available = MarketSourceAvailability(AvailabilityStatus.AVAILABLE, (), NOW)
    return MarketInputWindow(
        availability=available,
        history_availability=available,
        identity=identity,
        states=tuple(states),
    )


def _compose(states: list[MarketState] | None = None):
    market_input = _market_input(states or _states())
    result = MarketContextComposer(classifier=_SMALL).compose(market_input)
    return market_input, result


def test_canonical_entry_point_is_the_default():
    assert MarketContextComposer()._evaluator is build_market_context


def test_actual_dependency_graph_is_raw_market_only():
    assert tuple(signature(MarketContextComposer.compose).parameters) == (
        "self",
        "market_input",
    )


def test_successful_context_composition_preserves_canonical_output():
    market_input, result = _compose()
    expected = build_market_context(
        symbol=Symbol(CONTRACT),
        timeframe=Timeframe.M5,
        occurred_at=market_input.identity.latest_closed_at,  # type: ignore[union-attr]
        window=list(market_input.states),
        upstream_session_name="RTH",
        upstream_is_rth=True,
        calendar=CME_RTH_V1,
        classifier=_SMALL,
    )
    assert result.availability.status == ContextAvailabilityStatus.AVAILABLE
    assert result.output == expected
    assert result.input_identity is market_input.identity


def test_bounded_source_window_is_passed_unchanged_without_recomputation():
    market_input = _market_input(_states(12))
    captured: dict[str, object] = {}

    def evaluator(**kwargs):
        captured.update(kwargs)
        return build_market_context(**kwargs)

    result = MarketContextComposer(evaluator=evaluator, classifier=_SMALL).compose(
        market_input
    )
    assert result.output is not None
    assert captured["window"] == list(market_input.states[-10:])
    assert all(
        actual is expected
        for actual, expected in zip(
            cast(list[MarketState], captured["window"]), market_input.states[-10:]
        )
    )


def test_good_quality_remains_available_and_canonical_trusted():
    _, result = _compose()
    assert result.availability.status == ContextAvailabilityStatus.AVAILABLE
    assert result.output is not None
    assert result.output.quality == ContextQuality.TRUSTED
    assert result.metadata is not None
    assert result.metadata.quality == ContextQuality.TRUSTED


def test_degraded_quality_remains_available():
    _, result = _compose(_states(session_name=Session.OVERNIGHT, is_rth=False))
    assert result.availability.status == ContextAvailabilityStatus.AVAILABLE
    assert result.output is not None
    assert result.output.quality == ContextQuality.DEGRADED


def test_unknown_quality_from_missing_upstream_remains_available():
    _, result = _compose(_states(session_name=None, is_rth=None))
    assert result.availability.status == ContextAvailabilityStatus.AVAILABLE
    assert result.output is not None
    assert result.output.quality == ContextQuality.UNKNOWN


def test_insufficient_history_preserves_valid_unknown_output():
    market_input = _market_input(_states(9))
    result = MarketContextComposer(classifier=_SMALL).compose(market_input)
    assert result.availability.status == ContextAvailabilityStatus.INSUFFICIENT_DATA
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.INSUFFICIENT_HISTORY,
    )
    assert result.output is not None
    assert result.output.quality == ContextQuality.UNKNOWN
    assert market_input.availability.status == AvailabilityStatus.AVAILABLE


def test_raw_market_unavailable_short_circuits_with_reason_chain():
    availability = MarketSourceAvailability(
        AvailabilityStatus.INVALID,
        (MarketSourceReason.IDENTITY_MISMATCH,),
        NOW,
    )
    market_input = MarketInputWindow(
        availability=availability,
        history_availability=availability,
        identity=None,
    )
    invoked = False

    def evaluator(**kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("Context evaluator must not be invoked")

    result = MarketContextComposer(evaluator=evaluator).compose(market_input)
    assert not invoked
    assert (
        result.availability.status
        == ContextAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.market_dependency_reasons == (
        MarketSourceReason.IDENTITY_MISMATCH,
    )


def test_rule_and_setup_availability_are_not_context_dependencies():
    market_input, result = _compose()
    assert market_input.availability.status == AvailabilityStatus.AVAILABLE
    assert result.availability.status == ContextAvailabilityStatus.AVAILABLE


def test_invalid_market_dependency_alignment_short_circuits_context():
    market_input = _market_input(_states())
    assert market_input.identity is not None
    mismatched_identity = replace(
        market_input.identity,
        latest_closed_at=market_input.identity.latest_closed_at - timedelta(minutes=5),
    )
    mismatched = replace(market_input, identity=mismatched_identity)
    invoked = False

    def evaluator(**kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("Context evaluator must not be invoked")

    result = MarketContextComposer(evaluator=evaluator).compose(mismatched)
    assert not invoked
    assert (
        result.availability.status
        == ContextAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.DEPENDENCY_ALIGNMENT_INVALID,
    )


def test_context_service_exception_is_section_local_unavailable():
    market_input = _market_input(_states())

    def evaluator(**kwargs):
        raise RuntimeError("service failed")

    result = MarketContextComposer(evaluator=evaluator).compose(market_input)
    assert result.availability.status == ContextAvailabilityStatus.UNAVAILABLE
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.MARKET_CONTEXT_SERVICE_FAILURE,
    )
    assert market_input.availability.status == AvailabilityStatus.AVAILABLE


def test_empty_context_output_is_unavailable():
    result = MarketContextComposer(evaluator=lambda **kwargs: None).compose(
        _market_input(_states())
    )
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.EMPTY_CONTEXT_OUTPUT,
    )


def _mutated_output(**changes) -> MarketContext:
    market_input = _market_input(_states())
    canonical = MarketContextComposer(classifier=_SMALL).compose(market_input).output
    assert canonical is not None
    return replace(canonical, **changes)


def test_timestamp_mismatch_is_invalid():
    output = _mutated_output(occurred_at=_mid_session() - timedelta(minutes=5))
    result = MarketContextComposer(evaluator=lambda **kwargs: output).compose(
        _market_input(_states())
    )
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.TIMESTAMP_MISMATCH,
    )


def test_symbol_mismatch_is_invalid():
    output = _mutated_output(symbol=Symbol("MNQZ6"))
    result = MarketContextComposer(evaluator=lambda **kwargs: output).compose(
        _market_input(_states())
    )
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.SYMBOL_MISMATCH,
    )


def test_timeframe_mismatch_is_invalid():
    output = _mutated_output(timeframe=Timeframe.M15)
    result = MarketContextComposer(evaluator=lambda **kwargs: output).compose(
        _market_input(_states())
    )
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.TIMEFRAME_MISMATCH,
    )


def test_structurally_invalid_output_is_invalid():
    result = MarketContextComposer(
        evaluator=lambda **kwargs: cast(MarketContext, object())
    ).compose(_market_input(_states()))
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.STRUCTURALLY_INVALID,
    )


def test_unsupported_quality_value_is_invalid():
    output = _mutated_output(quality=cast(ContextQuality, "unexpected"))
    result = MarketContextComposer(evaluator=lambda **kwargs: output).compose(
        _market_input(_states())
    )
    assert result.availability.reason_codes == (
        ContextAvailabilityReason.UNSUPPORTED_QUALITY,
    )


def test_metadata_preserves_versions_fingerprint_and_source_identity():
    market_input, result = _compose()
    assert result.output is not None
    assert result.metadata is not None
    assert result.metadata.classifier_version == result.output.classifier_version
    assert result.metadata.calendar_version == result.output.calendar_version
    assert result.metadata.context_fingerprint == result.output.context_fingerprint
    source = result.metadata.source_market_window
    assert source.count == len(market_input.states)
    assert source.latest_occurred_at == market_input.identity.latest_closed_at  # type: ignore[union-attr]
    assert source.symbols == (CONTRACT,)
    assert source.timeframes == ("5m",)
    assert source.schema_versions == ("1.0",)


def test_live_replay_equivalence_for_identical_market_fixture():
    states = _states()
    trader_result = MarketContextComposer(classifier=_SMALL).compose(
        _market_input(states)
    )
    replay_result = build_replay_output_window(
        states, calendar=CME_RTH_V1, classifier=_SMALL
    )[-1].market_context
    assert trader_result.output == replay_result
