"""Sprint 12B Part 5 tests for canonical Setup Engine composition."""

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import InsufficientData, SetupEngineOutput
from atlas.setup_engine.service import build_setup_engine_output_window
from atlas.trader_now.models import (
    AvailabilityStatus,
    MarketInputIdentity,
    MarketInputWindow,
    MarketSourceAvailability,
    MarketSourceReason,
    EconomicInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    RuleAvailabilityReason,
    SetupAvailabilityReason,
    SetupAvailabilityStatus,
    SourceEventIdentity,
)
from atlas.trader_now.rules import RuleComposer
from atlas.trader_now.setups import (
    SetupComposer,
    combined_rule_setup_history_required,
)

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
CONTRACT = "MNQU6"


def _state(index: int, *, complete: bool = True) -> MarketState:
    occurred_at = NOW - timedelta(minutes=5 * (21 - index))
    base = 20000.0 + index
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
        open=Price(base, 0.25) if complete else None,
        high=Price(base + 2, 0.25) if complete else None,
        low=Price(base - 2, 0.25) if complete else None,
        close=Price(base + 1, 0.25) if complete else None,
        volume=1000.0 if complete else None,
        previous_day_high=Price(20100, 0.25) if complete else None,
        previous_day_low=Price(19900, 0.25) if complete else None,
        overnight_high=Price(20080, 0.25) if complete else None,
        overnight_low=Price(19920, 0.25) if complete else None,
        vwap=base if complete else None,
        distance_from_vwap_points=1.0 if complete else None,
        atr=2.0 if complete else None,
        volume_ratio=2.0 if complete else None,
    )


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
        history_availability=MarketSourceAvailability(
            AvailabilityStatus.INSUFFICIENT_DATA,
            (MarketSourceReason.INSUFFICIENT_HISTORY,),
            NOW,
        ),
        identity=identity,
        states=tuple(states),
    )


def _inputs(count: int = 21, *, complete: bool = True):
    market_input = _market_input(
        [_state(index, complete=complete) for index in range(count)]
    )
    rules = RuleComposer().compose(market_input)
    assert rules.availability.status == AvailabilityStatus.AVAILABLE
    return market_input, rules


def _setup_output(
    market_input: MarketInputWindow,
    rules,
    *,
    occurred_at: str | None = None,
    symbol: str = CONTRACT,
    timeframe: str = "5m",
    setups=None,
) -> SetupEngineOutput:
    assert market_input.identity is not None
    canonical = build_setup_engine_output_window(list(rules.window))[-1]
    return SetupEngineOutput(
        schema_version=canonical.schema_version,
        symbol=symbol,
        timeframe=timeframe,
        occurred_at=occurred_at or market_input.identity.latest_closed_at.isoformat(),
        setups=canonical.setups if setups is None else setups,
    )


def test_combined_history_is_derived_from_canonical_registries():
    assert combined_rule_setup_history_required() == 21


def test_successful_setup_composition_preserves_canonical_output():
    market_input, rules = _inputs()
    result = SetupComposer().compose(market_input=market_input, rules=rules)
    expected = build_setup_engine_output_window(list(rules.window))[-1]
    assert result.availability.status == SetupAvailabilityStatus.AVAILABLE
    assert result.output == expected
    assert result.input_identity is market_input.identity


def test_complete_rule_window_is_passed_without_rule_recomputation():
    market_input, rules = _inputs()
    captured: list[RuleEngineOutput] = []

    def evaluator(window: list[RuleEngineOutput]) -> list[SetupEngineOutput]:
        captured.extend(window)
        return build_setup_engine_output_window(window)

    result = SetupComposer(evaluator=evaluator).compose(
        market_input=market_input, rules=rules
    )
    assert result.output is not None
    assert captured == list(rules.window)
    assert len(captured) == len(market_input.states)


def test_insufficient_20_bar_history_preserves_output_and_other_layers():
    market_input, rules = _inputs(20)
    result = SetupComposer().compose(market_input=market_input, rules=rules)
    assert result.availability.status == SetupAvailabilityStatus.INSUFFICIENT_DATA
    assert result.output is not None
    assert market_input.availability.status == AvailabilityStatus.AVAILABLE
    assert rules.availability.status == AvailabilityStatus.AVAILABLE


def test_sufficient_21_bar_history_can_be_fully_available():
    market_input, rules = _inputs(21)
    result = SetupComposer().compose(market_input=market_input, rules=rules)
    assert result.availability.status == SetupAvailabilityStatus.AVAILABLE
    assert result.metadata is not None
    assert result.metadata.has_insufficient_data is False


def test_canonical_insufficient_data_is_preserved_not_engine_failure():
    market_input, rules = _inputs(21, complete=False)
    result = SetupComposer().compose(market_input=market_input, rules=rules)
    assert result.availability.status == SetupAvailabilityStatus.INSUFFICIENT_DATA
    assert result.output is not None
    assert any(
        isinstance(outcome, InsufficientData) for outcome in result.output.setups
    )
    assert result.availability.reason_codes == (
        SetupAvailabilityReason.INSUFFICIENT_HISTORY,
    )


def test_rule_dependency_unavailable_skips_setup_engine_and_preserves_reason_chain():
    market_input, _ = _inputs()
    unavailable_rules = RuleComposer(evaluator=lambda _: []).compose(market_input)
    called = False

    def evaluator(_: list[RuleEngineOutput]) -> list[SetupEngineOutput]:
        nonlocal called
        called = True
        return []

    result = SetupComposer(evaluator=evaluator).compose(
        market_input=market_input, rules=unavailable_rules
    )
    assert called is False
    assert result.availability.status == (
        SetupAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.reason_codes == (
        SetupAvailabilityReason.RULE_OUTPUT_UNAVAILABLE,
    )
    assert result.availability.rule_dependency_reasons == (
        RuleAvailabilityReason.RULE_OUTPUT_UNAVAILABLE,
    )


def test_rule_alignment_invalid_is_a_distinct_dependency_failure():
    market_input, _ = _inputs()
    assert market_input.identity is not None
    canonical = RuleComposer().compose(market_input)
    assert canonical.output is not None
    mismatched = RuleEngineOutput(
        schema_version=canonical.output.schema_version,
        symbol="MNQZ6",
        timeframe=canonical.output.timeframe,
        occurred_at=canonical.output.occurred_at,
        facts=canonical.output.facts,
    )
    invalid_rules = RuleComposer(evaluator=lambda _: [mismatched]).compose(market_input)
    result = SetupComposer().compose(market_input=market_input, rules=invalid_rules)
    assert result.availability.status == (
        SetupAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.reason_codes == (
        SetupAvailabilityReason.RULE_ALIGNMENT_INVALID,
    )


def test_setup_engine_exception_does_not_change_market_or_rules():
    market_input, rules = _inputs()

    def fail(_: list[RuleEngineOutput]) -> list[SetupEngineOutput]:
        raise RuntimeError("setup internals")

    result = SetupComposer(evaluator=fail).compose(
        market_input=market_input, rules=rules
    )
    assert result.availability.reason_codes == (
        SetupAvailabilityReason.SETUP_ENGINE_FAILURE,
    )
    assert market_input.availability.status == AvailabilityStatus.AVAILABLE
    assert rules.availability.status == AvailabilityStatus.AVAILABLE
    assert rules.output is not None


def test_empty_setup_window_is_unavailable():
    market_input, rules = _inputs()
    result = SetupComposer(evaluator=lambda _: []).compose(
        market_input=market_input, rules=rules
    )
    assert result.availability.reason_codes == (
        SetupAvailabilityReason.EMPTY_SETUP_OUTPUT,
    )


@pytest.mark.parametrize(
    ("override", "expected_reasons"),
    [
        (
            {"occurred_at": (NOW + timedelta(minutes=5)).isoformat()},
            (
                SetupAvailabilityReason.TIMESTAMP_MISMATCH,
                SetupAvailabilityReason.SETUP_TO_RULE_TIMESTAMP_MISMATCH,
            ),
        ),
        ({"symbol": "MNQZ6"}, (SetupAvailabilityReason.SYMBOL_MISMATCH,)),
        ({"timeframe": "1m"}, (SetupAvailabilityReason.TIMEFRAME_MISMATCH,)),
    ],
)
def test_setup_alignment_mismatch_is_invalid_and_excluded(override, expected_reasons):
    market_input, rules = _inputs()
    mismatched = _setup_output(market_input, rules, **override)
    result = SetupComposer(evaluator=lambda _: [mismatched]).compose(
        market_input=market_input, rules=rules
    )
    assert result.availability.status == SetupAvailabilityStatus.INVALID
    assert result.availability.reason_codes == expected_reasons
    assert result.output is None
    assert result.metadata is None


def test_structurally_invalid_setup_output_is_rejected():
    market_input, rules = _inputs()
    result = SetupComposer(
        evaluator=lambda _: cast(list[SetupEngineOutput], [object()])
    ).compose(market_input=market_input, rules=rules)
    assert result.availability.status == SetupAvailabilityStatus.INVALID
    assert result.availability.reason_codes == (
        SetupAvailabilityReason.STRUCTURALLY_INVALID,
    )


def test_empty_setup_tuple_is_structurally_invalid():
    market_input, rules = _inputs()
    empty = _setup_output(market_input, rules, setups=())
    result = SetupComposer(evaluator=lambda _: [empty]).compose(
        market_input=market_input, rules=rules
    )
    assert result.availability.reason_codes == (
        SetupAvailabilityReason.STRUCTURALLY_INVALID,
    )


def test_metadata_definition_versions_and_rule_window_identity_are_preserved():
    market_input, rules = _inputs()
    result = SetupComposer().compose(market_input=market_input, rules=rules)
    assert result.output is not None
    assert result.metadata is not None
    assert result.metadata.schema_version == result.output.schema_version
    assert dict(result.metadata.definition_versions) == {
        outcome.setup_name: outcome.definition_version
        for outcome in result.output.setups
    }
    assert result.metadata.source_rule_window.count == len(rules.window)
    assert result.metadata.source_rule_window.latest_occurred_at == (
        rules.window[-1].occurred_at
    )


def test_latest_setup_rule_and_market_timestamps_align():
    market_input, rules = _inputs()
    result = SetupComposer().compose(market_input=market_input, rules=rules)
    assert result.output is not None
    assert market_input.identity is not None
    assert result.output.occurred_at == rules.window[-1].occurred_at
    assert (
        result.output.occurred_at == market_input.identity.latest_closed_at.isoformat()
    )


def test_live_composition_equals_canonical_replay_pipeline_through_setup_layer():
    market_input, rules = _inputs()
    replay_setup_window = build_setup_engine_output_window(list(rules.window))
    live = SetupComposer().compose(market_input=market_input, rules=rules)
    assert live.window == tuple(replay_setup_window)
    assert live.output == replay_setup_window[-1]
