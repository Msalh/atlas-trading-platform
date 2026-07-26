"""Sprint 12B Part 4 tests for canonical Rule Engine composition."""

from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.trader_now.models import (
    AvailabilityStatus,
    EconomicInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    MarketInputIdentity,
    MarketInputWindow,
    MarketSourceAvailability,
    MarketSourceReason,
    RuleAvailabilityReason,
    SourceEventIdentity,
)
from atlas.trader_now.rules import RuleComposer

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
CONTRACT = "MNQU6"


def _state(index: int, *, minute_offset: int | None = None) -> MarketState:
    occurred_at = NOW - timedelta(
        minutes=5 * (20 - index) if minute_offset is None else minute_offset
    )
    return MarketState(
        envelope=Event(
            event_id=f"event-{index}",
            event_type="bar_closed",
            source="tradingview",
            occurred_at=occurred_at,
            received_at=occurred_at + timedelta(seconds=1),
        ),
        schema_version="1.0",
        symbol=Symbol(CONTRACT),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
        open=None,
        high=None,
        low=None,
        close=None,
        volume=None,
    )


def _market_input(states: list[MarketState]) -> MarketInputWindow:
    latest = states[-1]
    events = tuple(
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
        source_events=events,
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
        states=tuple(states),
    )


def _output(
    market_input: MarketInputWindow,
    *,
    occurred_at: str | None = None,
    symbol: str = CONTRACT,
    timeframe: str = "5m",
) -> RuleEngineOutput:
    assert market_input.identity is not None
    canonical = build_rule_engine_output_window(list(market_input.states))[-1]
    return RuleEngineOutput(
        schema_version=canonical.schema_version,
        symbol=symbol,
        timeframe=timeframe,
        occurred_at=occurred_at or market_input.identity.latest_closed_at.isoformat(),
        facts=canonical.facts,
    )


def test_successful_rule_composition_preserves_canonical_output_unchanged():
    market_input = _market_input([_state(index) for index in range(20)])
    result = RuleComposer().compose(market_input)
    expected = build_rule_engine_output_window(list(market_input.states))[-1]

    assert result.availability.status == AvailabilityStatus.AVAILABLE
    assert result.output == expected
    assert result.input_identity is market_input.identity
    assert tuple(result.output.facts) == tuple(expected.facts)


def test_short_contiguous_history_is_typed_insufficiency_without_rule_output(caplog):
    market_input = _market_input([_state(19)])
    result = RuleComposer().compose(market_input)
    assert result.availability.status == AvailabilityStatus.INSUFFICIENT_DATA
    assert result.availability.reason_codes == (
        RuleAvailabilityReason.INSUFFICIENT_HISTORY,
    )
    assert result.output is None
    assert result.metadata is None
    assert result.window == ()
    assert caplog.records[-1].diagnostic_category == (
        "insufficient_contiguous_history"
    )


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        (
            {"occurred_at": (NOW + timedelta(minutes=5)).isoformat()},
            RuleAvailabilityReason.TIMESTAMP_MISMATCH,
        ),
        ({"symbol": "MNQZ6"}, RuleAvailabilityReason.IDENTITY_MISMATCH),
        ({"timeframe": "1m"}, RuleAvailabilityReason.TIMEFRAME_MISMATCH),
    ],
)
def test_alignment_mismatch_is_typed_and_never_repaired(override, reason):
    market_input = _market_input([_state(index) for index in range(20)])
    mismatched = _output(market_input, **override)
    result = RuleComposer(evaluator=lambda _: [mismatched]).compose(market_input)
    assert result.availability.status == AvailabilityStatus.UNAVAILABLE
    assert result.availability.reason_codes == (reason,)
    assert result.output is None
    assert result.metadata is None


def test_rule_engine_failure_is_typed_unavailability(caplog):
    market_input = _market_input([_state(index) for index in range(20)])

    def fail(_: list[MarketState]) -> list[RuleEngineOutput]:
        raise RuntimeError("sensitive rule internals")

    result = RuleComposer(evaluator=fail).compose(market_input)
    assert result.availability.status == AvailabilityStatus.UNAVAILABLE
    assert result.availability.reason_codes == (
        RuleAvailabilityReason.RULE_ENGINE_FAILURE,
    )
    assert caplog.records[-1].diagnostic_category == "rule_engine_failure"
    assert "sensitive rule internals" not in caplog.text


def test_gapped_input_preserves_canonical_rule_window_failure():
    states = [_state(index) for index in range(20)]
    states[-1] = _state(19, minute_offset=-5)
    result = RuleComposer().compose(_market_input(states))
    assert result.availability.reason_codes == (
        RuleAvailabilityReason.RULE_ENGINE_FAILURE,
    )


def test_empty_evaluator_output_is_rule_unavailable():
    market_input = _market_input([_state(index) for index in range(20)])
    result = RuleComposer(evaluator=lambda _: []).compose(market_input)
    assert result.availability.reason_codes == (
        RuleAvailabilityReason.RULE_OUTPUT_UNAVAILABLE,
    )


def test_raw_market_unavailable_prevents_rule_evaluation():
    unavailable = MarketSourceAvailability(
        AvailabilityStatus.NO_DATA, (MarketSourceReason.NO_DATA,), NOW
    )
    market_input = MarketInputWindow(
        availability=unavailable,
        history_availability=unavailable,
        identity=None,
    )
    called = False

    def evaluator(_: list[MarketState]) -> list[RuleEngineOutput]:
        nonlocal called
        called = True
        return []

    result = RuleComposer(evaluator=evaluator).compose(market_input)
    assert called is False
    assert result.availability.reason_codes == (
        RuleAvailabilityReason.RAW_MARKET_UNAVAILABLE,
    )


def test_rule_metadata_and_definition_versions_are_preserved():
    market_input = _market_input([_state(index) for index in range(20)])
    result = RuleComposer().compose(market_input)
    assert result.output is not None
    assert result.metadata is not None
    assert result.metadata.schema_version == result.output.schema_version
    assert result.metadata.symbol == result.output.symbol
    assert result.metadata.timeframe == result.output.timeframe
    assert result.metadata.occurred_at == result.output.occurred_at
    assert dict(result.metadata.definition_versions) == {
        fact_id: outcome.definition_version
        for fact_id, outcome in result.output.facts.items()
    }


def test_latest_output_is_aligned_to_latest_closed_input_snapshot():
    market_input = _market_input([_state(index) for index in range(20)])
    result = RuleComposer().compose(market_input)
    assert result.output is not None
    assert market_input.identity is not None
    assert result.output.occurred_at == (
        market_input.identity.latest_closed_at.isoformat()
    )


def test_live_composer_matches_replay_canonical_rule_entry_for_identical_fixture():
    """Replay uses this exact public Rule-window function; compare at its boundary."""
    market_input = _market_input([_state(index) for index in range(20)])
    replay_rule_outputs = build_rule_engine_output_window(list(market_input.states))
    live_projection = RuleComposer().compose(market_input)
    assert live_projection.output == replay_rule_outputs[-1]
