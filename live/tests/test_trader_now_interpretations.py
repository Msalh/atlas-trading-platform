"""Sprint 12B Part 7 tests for canonical Setup Interpretation composition."""

from copy import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from inspect import signature
from typing import cast

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.service import build_replay_output_window
from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import SetupEngineOutput
from atlas.setup_interpretation.models import (
    DirectionSource,
    SetupDirection,
    SetupInterpretation,
)
from atlas.setup_interpretation.service import interpret_setups
from atlas.trader_now.interpretations import SetupInterpretationComposer
from atlas.trader_now.models import (
    AvailabilityStatus,
    InterpretationAvailabilityReason,
    InterpretationAvailabilityStatus,
    MarketInputIdentity,
    MarketInputWindow,
    MarketSourceAvailability,
    EconomicInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    RuleAvailability,
    RuleAvailabilityReason,
    RuleProjection,
    SetupAvailability,
    SetupAvailabilityReason,
    SetupAvailabilityStatus,
    SetupProjection,
    SourceEventIdentity,
)
from atlas.trader_now.rules import RuleComposer
from atlas.trader_now.setups import SetupComposer

NOW = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
CONTRACT = "MNQU6"


def _state(index: int) -> MarketState:
    occurred_at = NOW - timedelta(minutes=5 * (20 - index))
    return MarketState(
        envelope=Event(
            event_id=f"event-{index}",
            event_type="bar_closed",
            source="test",
            occurred_at=occurred_at,
            received_at=occurred_at + timedelta(seconds=1),
        ),
        schema_version="1.0",
        symbol=Symbol(CONTRACT),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
        atr=2.0,
    )


def _market_input() -> MarketInputWindow:
    states = [_state(index) for index in range(21)]
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
        latest_closed_at=states[-1].envelope.occurred_at,
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


def _dependencies():
    market_input = _market_input()
    rules = RuleComposer().compose(market_input)
    setups = SetupComposer().compose(market_input=market_input, rules=rules)
    assert rules.output is not None
    assert setups.output is not None
    return market_input, rules, setups


def test_canonical_interpretation_entry_point_is_default():
    assert SetupInterpretationComposer()._evaluator is interpret_setups


def test_actual_dependency_graph_is_latest_rule_and_setup_only():
    assert tuple(signature(SetupInterpretationComposer.compose).parameters) == (
        "self",
        "rules",
        "setups",
    )


def test_successful_composition_preserves_canonical_tuple():
    _, rules, setups = _dependencies()
    result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    expected = interpret_setups(
        rule_engine_output=rules.output,  # type: ignore[arg-type]
        setup_engine_output=setups.output,  # type: ignore[arg-type]
    )
    assert result.availability.status == InterpretationAvailabilityStatus.AVAILABLE
    assert result.output == expected
    assert result.input_identity is rules.input_identity


def test_only_latest_canonical_outputs_are_passed_unchanged():
    _, rules, setups = _dependencies()
    captured: dict[str, object] = {}

    def evaluator(
        *,
        rule_engine_output: RuleEngineOutput,
        setup_engine_output: SetupEngineOutput,
    ) -> tuple[SetupInterpretation, ...]:
        captured["rule"] = rule_engine_output
        captured["setup"] = setup_engine_output
        return interpret_setups(
            rule_engine_output=rule_engine_output,
            setup_engine_output=setup_engine_output,
        )

    result = SetupInterpretationComposer(evaluator=evaluator).compose(
        rules=rules, setups=setups
    )
    assert result.output
    assert captured == {"rule": rules.output, "setup": setups.output}
    assert captured["rule"] is rules.output
    assert captured["setup"] is setups.output


def test_market_and_context_are_not_interpretation_dependencies():
    _, rules, setups = _dependencies()
    result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    assert result.availability.status == InterpretationAvailabilityStatus.AVAILABLE


def test_canonical_unavailable_directions_remain_available_domain_outputs():
    _, rules, setups = _dependencies()
    result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    assert result.output
    assert any(
        entry.direction == SetupDirection.UNAVAILABLE
        and entry.source == DirectionSource.INSUFFICIENT_DATA
        for entry in result.output
    )
    assert result.availability.status == InterpretationAvailabilityStatus.AVAILABLE


def test_canonical_neutral_status_remains_available():
    _, rules, setups = _dependencies()
    assert rules.output is not None
    assert setups.output is not None
    canonical = list(
        interpret_setups(
            rule_engine_output=rules.output,
            setup_engine_output=setups.output,
        )
    )
    neutral = copy(canonical[0])
    object.__setattr__(neutral, "detected", True)
    object.__setattr__(neutral, "direction", SetupDirection.NEUTRAL)
    object.__setattr__(neutral, "source", DirectionSource.INTENTIONALLY_NEUTRAL)
    canonical[0] = neutral
    result = SetupInterpretationComposer(
        evaluator=lambda **kwargs: tuple(canonical)
    ).compose(rules=rules, setups=setups)
    assert result.availability.status == InterpretationAvailabilityStatus.AVAILABLE
    assert result.output[0].direction == SetupDirection.NEUTRAL


def test_rule_dependency_unavailable_preserves_reason_chain():
    _, _, setups = _dependencies()
    rules = RuleProjection(
        availability=RuleAvailability(
            AvailabilityStatus.UNAVAILABLE,
            (RuleAvailabilityReason.RULE_ENGINE_FAILURE,),
        ),
        input_identity=None,
        output=None,
        metadata=None,
    )
    result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    assert (
        result.availability.status
        == InterpretationAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.RULE_DEPENDENCY_UNAVAILABLE,
    )
    assert result.availability.rule_dependency_reasons == (
        RuleAvailabilityReason.RULE_ENGINE_FAILURE,
    )


def test_setup_dependency_unavailable_preserves_reason_chain():
    _, rules, _ = _dependencies()
    setups = SetupProjection(
        availability=SetupAvailability(
            SetupAvailabilityStatus.UNAVAILABLE,
            (SetupAvailabilityReason.SETUP_ENGINE_FAILURE,),
        ),
        input_identity=None,
        output=None,
        metadata=None,
    )
    result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    assert (
        result.availability.status
        == InterpretationAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.setup_dependency_reasons == (
        SetupAvailabilityReason.SETUP_ENGINE_FAILURE,
    )


def test_invalid_required_dependency_is_not_invoked():
    _, rules, _ = _dependencies()
    setups = SetupProjection(
        availability=SetupAvailability(
            SetupAvailabilityStatus.INVALID,
            (SetupAvailabilityReason.STRUCTURALLY_INVALID,),
        ),
        input_identity=None,
        output=None,
        metadata=None,
    )
    result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    assert (
        result.availability.status
        == InterpretationAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.setup_dependency_reasons == (
        SetupAvailabilityReason.STRUCTURALLY_INVALID,
    )


def test_dependency_identity_invalid_short_circuits_service():
    market_input, rules, setups = _dependencies()
    assert setups.input_identity is not None
    other_identity = replace(
        setups.input_identity,
        market_data_series=replace(
            setups.input_identity.market_data_series, symbol="MNQZ6"
        ),
    )
    mismatched = replace(setups, input_identity=other_identity)
    invoked = False

    def evaluator(**kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("evaluator must not be invoked")

    result = SetupInterpretationComposer(evaluator=evaluator).compose(
        rules=rules, setups=mismatched
    )
    assert not invoked
    assert (
        result.availability.status
        == InterpretationAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert market_input.availability.status == AvailabilityStatus.AVAILABLE


def _replace_rule_output(rules: RuleProjection, **changes: object) -> RuleProjection:
    assert rules.output is not None
    changed = replace(rules.output, **changes)
    return replace(rules, output=changed, window=(*rules.window[:-1], changed))


def _replace_setup_output(
    setups: SetupProjection, **changes: object
) -> SetupProjection:
    assert setups.output is not None
    changed = replace(setups.output, **changes)
    return replace(setups, output=changed, window=(*setups.window[:-1], changed))


def test_source_timestamp_mismatch_is_invalid():
    _, rules, setups = _dependencies()
    changed = _replace_setup_output(
        setups, occurred_at=(NOW - timedelta(minutes=5)).isoformat()
    )
    result = SetupInterpretationComposer().compose(rules=rules, setups=changed)
    assert result.availability.status == InterpretationAvailabilityStatus.INVALID
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.SOURCE_TIMESTAMP_MISMATCH,
    )


def test_source_rule_timestamp_mismatch_is_invalid():
    _, rules, setups = _dependencies()
    changed = _replace_rule_output(
        rules, occurred_at=(NOW - timedelta(minutes=5)).isoformat()
    )
    result = SetupInterpretationComposer().compose(rules=changed, setups=setups)
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.SOURCE_TIMESTAMP_MISMATCH,
    )


def test_source_symbol_mismatch_is_invalid():
    _, rules, setups = _dependencies()
    changed = _replace_setup_output(setups, symbol="MNQZ6")
    result = SetupInterpretationComposer().compose(rules=rules, setups=changed)
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.SOURCE_SYMBOL_MISMATCH,
    )


def test_source_timeframe_mismatch_is_invalid():
    _, rules, setups = _dependencies()
    changed = _replace_setup_output(setups, timeframe="15m")
    result = SetupInterpretationComposer().compose(rules=rules, setups=changed)
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.SOURCE_TIMEFRAME_MISMATCH,
    )


def test_service_exception_is_section_local_unavailable():
    market_input, rules, setups = _dependencies()

    def evaluator(**kwargs):
        raise RuntimeError("service failed")

    result = SetupInterpretationComposer(evaluator=evaluator).compose(
        rules=rules, setups=setups
    )
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.SERVICE_FAILURE,
    )
    assert rules.output is not None
    assert setups.output is not None
    assert market_input.states


def test_empty_output_is_unavailable():
    _, rules, setups = _dependencies()
    result = SetupInterpretationComposer(evaluator=lambda **kwargs: ()).compose(
        rules=rules, setups=setups
    )
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.EMPTY_OUTPUT,
    )


def test_interpretation_timestamp_mismatch_is_invalid():
    _, rules, setups = _dependencies()
    assert rules.output is not None
    assert setups.output is not None
    canonical = list(
        interpret_setups(
            rule_engine_output=rules.output,
            setup_engine_output=setups.output,
        )
    )
    canonical[0] = replace(
        canonical[0], occurred_at=canonical[0].occurred_at - timedelta(minutes=5)
    )
    result = SetupInterpretationComposer(
        evaluator=lambda **kwargs: tuple(canonical)
    ).compose(rules=rules, setups=setups)
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.TIMESTAMP_MISMATCH,
    )


def test_structurally_invalid_output_is_invalid():
    _, rules, setups = _dependencies()
    result = SetupInterpretationComposer(
        evaluator=lambda **kwargs: cast(tuple[SetupInterpretation, ...], (object(),))
    ).compose(rules=rules, setups=setups)
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.STRUCTURALLY_INVALID,
    )


def test_unsupported_direction_is_invalid():
    _, rules, setups = _dependencies()
    assert rules.output is not None
    assert setups.output is not None
    canonical = list(
        interpret_setups(
            rule_engine_output=rules.output,
            setup_engine_output=setups.output,
        )
    )
    invalid = copy(canonical[0])
    object.__setattr__(invalid, "direction", "unexpected")
    canonical[0] = invalid
    result = SetupInterpretationComposer(
        evaluator=lambda **kwargs: tuple(canonical)
    ).compose(rules=rules, setups=setups)
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.UNSUPPORTED_DIRECTION,
    )


def test_unsupported_source_is_invalid():
    _, rules, setups = _dependencies()
    assert rules.output is not None
    assert setups.output is not None
    canonical = list(
        interpret_setups(
            rule_engine_output=rules.output,
            setup_engine_output=setups.output,
        )
    )
    invalid = copy(canonical[0])
    object.__setattr__(invalid, "source", "unexpected")
    canonical[0] = invalid
    result = SetupInterpretationComposer(
        evaluator=lambda **kwargs: tuple(canonical)
    ).compose(rules=rules, setups=setups)
    assert result.availability.reason_codes == (
        InterpretationAvailabilityReason.UNSUPPORTED_SOURCE,
    )


def test_metadata_preserves_versions_fingerprints_and_source_identity():
    _, rules, setups = _dependencies()
    result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    assert result.metadata is not None
    assert result.output
    assert result.metadata.interpretation_versions == tuple(
        sorted({entry.interpretation_version for entry in result.output})
    )
    assert result.metadata.interpretation_fingerprints == tuple(
        sorted({entry.interpretation_fingerprint for entry in result.output})
    )
    assert result.metadata.setup_ids == tuple(entry.setup_id for entry in result.output)
    assert result.metadata.source_identity.rule_schema_version == (
        rules.output.schema_version  # type: ignore[union-attr]
    )
    assert result.metadata.source_identity.setup_schema_version == (
        setups.output.schema_version  # type: ignore[union-attr]
    )


def test_live_replay_equivalence_through_interpretation_layer():
    market_input, rules, setups = _dependencies()
    trader_result = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    replay_result = build_replay_output_window(list(market_input.states))[
        -1
    ].setup_interpretations
    assert trader_result.output == replay_result
