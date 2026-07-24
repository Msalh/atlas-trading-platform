"""Sprint 12B Part 8 tests for canonical Strategy Engine composition."""

from copy import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from inspect import signature
from typing import cast

from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_context.definitions import (
    RegimeClassifierDefinition,
    RegimeClassifierParams,
)
from atlas.market_context.models import ContextQuality
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.models import ReplayFrame
from atlas.replay_engine.service import build_replay_output_window
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)
from atlas.strategy_engine.service import evaluate_strategies
from atlas.strategy_engine.strategies.displacement_volume_context import (
    DisplacementVolumeContext,
)
from atlas.trader_now.contexts import MarketContextComposer
from atlas.trader_now.interpretations import SetupInterpretationComposer
from atlas.trader_now.models import (
    AvailabilityStatus,
    ContextAvailability,
    ContextAvailabilityReason,
    ContextAvailabilityStatus,
    ContextProjection,
    InterpretationAvailability,
    InterpretationAvailabilityReason,
    InterpretationAvailabilityStatus,
    InterpretationProjection,
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
    StrategyAvailabilityReason,
    StrategyAvailabilityStatus,
)
from atlas.trader_now.rules import RuleComposer
from atlas.trader_now.setups import SetupComposer
from atlas.trader_now.strategies import StrategyComposer

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


def _states(
    *,
    volume_ratio: float = 2.0,
    session_name: Session | None = Session.RTH,
    is_rth: bool | None = True,
) -> list[MarketState]:
    first = NOW - timedelta(minutes=5 * 20)
    states = []
    for index in range(21):
        occurred_at = first + timedelta(minutes=5 * index)
        close = 20000.0 + index
        states.append(
            MarketState(
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
                open=Price(close - 1, 0.25),
                high=Price(close + 10, 0.25),
                low=Price(close - 10, 0.25),
                close=Price(close, 0.25),
                volume_ratio=volume_ratio,
                atr=10.0,
                session_name=session_name,
                is_rth=is_rth,
            )
        )
    return states


def _market_input(states: list[MarketState]) -> MarketInputWindow:
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


def _pipeline(
    *,
    states: list[MarketState] | None = None,
    classifier: RegimeClassifierDefinition = _SMALL,
):
    market_input = _market_input(states or _states())
    rules = RuleComposer().compose(market_input)
    setups = SetupComposer().compose(market_input=market_input, rules=rules)
    context = MarketContextComposer(classifier=classifier).compose(market_input)
    interpretations = SetupInterpretationComposer().compose(rules=rules, setups=setups)
    assert rules.output is not None
    assert setups.output is not None
    assert context.output is not None
    assert interpretations.output
    return market_input, rules, setups, context, interpretations


def _compose(dependencies=None, **composer_kwargs):
    values = dependencies or _pipeline()
    market_input, rules, setups, context, interpretations = values
    result = StrategyComposer(**composer_kwargs).compose(
        market_input=market_input,
        rules=rules,
        setups=setups,
        context=context,
        interpretations=interpretations,
    )
    return values, result


def test_authoritative_strategy_entry_point_is_default():
    assert StrategyComposer()._evaluator is evaluate_strategies


def test_actual_dependency_graph_is_complete_replay_frame_sources():
    assert tuple(signature(StrategyComposer.compose).parameters) == (
        "self",
        "market_input",
        "rules",
        "setups",
        "context",
        "interpretations",
    )


def test_replay_equivalent_frame_uses_exact_canonical_objects():
    captured: dict[str, object] = {}

    def evaluator(frame, strategies):
        captured["frame"] = frame
        captured["strategies"] = strategies
        return evaluate_strategies(frame, strategies)

    values, result = _compose(evaluator=evaluator)
    market_input, rules, setups, context, interpretations = values
    frame = cast(ReplayFrame, captured["frame"])
    assert frame.market_state is market_input.states[-1]
    assert frame.rule_engine_output is rules.output
    assert frame.setup_engine_output is setups.output
    assert frame.market_context is context.output
    assert frame.setup_interpretations is interpretations.output
    assert result.output


def test_candidate_result_and_reason_codes_are_preserved():
    _, result = _compose()
    assert result.availability.status == StrategyAvailabilityStatus.AVAILABLE
    assert result.output[0].disposition == StrategyDisposition.CANDIDATE
    assert result.output[0].direction == StrategyDirection.LONG
    assert result.output[0].reason_codes == ("accepted",)


def test_no_signal_result_is_available_and_preserved():
    values = _pipeline(states=_states(volume_ratio=1.0))
    _, result = _compose(values)
    assert result.availability.status == StrategyAvailabilityStatus.AVAILABLE
    assert result.output[0].disposition == StrategyDisposition.NO_SIGNAL
    assert result.output[0].reason_codes == ("setup_absent",)


def test_unknown_context_rejection_is_available_and_preserved():
    values = _pipeline(
        classifier=replace(
            _SMALL,
            params=replace(_SMALL.params, min_bars_required=22),
        )
    )
    assert values[3].output is not None
    assert values[3].output.quality == ContextQuality.UNKNOWN
    _, result = _compose(values)
    assert result.availability.status == StrategyAvailabilityStatus.AVAILABLE
    assert result.output[0].disposition == StrategyDisposition.REJECTED
    assert result.output[0].reason_codes == ("context_insufficient",)


def test_degraded_context_remains_valid_strategy_input():
    values = _pipeline(states=_states(session_name=Session.OVERNIGHT, is_rth=False))
    assert values[3].output is not None
    assert values[3].output.quality == ContextQuality.DEGRADED
    _, result = _compose(values)
    assert result.availability.status == StrategyAvailabilityStatus.AVAILABLE
    assert result.output[0].disposition == StrategyDisposition.CANDIDATE


def test_latest_market_timestamp_is_strategy_timestamp():
    values, result = _compose()
    assert result.output[0].occurred_at == values[0].identity.latest_closed_at  # type: ignore[union-attr]


def test_required_rule_dependency_unavailable_short_circuits():
    values = list(_pipeline())
    values[1] = RuleProjection(
        availability=RuleAvailability(
            AvailabilityStatus.UNAVAILABLE,
            (RuleAvailabilityReason.RULE_ENGINE_FAILURE,),
        ),
        input_identity=None,
        output=None,
        metadata=None,
    )
    _, result = _compose(tuple(values))
    assert (
        result.availability.status
        == StrategyAvailabilityStatus.UNAVAILABLE_DUE_TO_DEPENDENCY
    )
    assert result.availability.rule_dependency_reasons == (
        RuleAvailabilityReason.RULE_ENGINE_FAILURE,
    )


def test_required_setup_dependency_invalid_short_circuits():
    values = list(_pipeline())
    values[2] = SetupProjection(
        availability=SetupAvailability(
            SetupAvailabilityStatus.INVALID,
            (SetupAvailabilityReason.STRUCTURALLY_INVALID,),
        ),
        input_identity=None,
        output=None,
        metadata=None,
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.SETUP_DEPENDENCY_UNAVAILABLE,
    )


def test_required_context_dependency_unavailable_short_circuits():
    values = list(_pipeline())
    values[3] = ContextProjection(
        availability=ContextAvailability(
            ContextAvailabilityStatus.UNAVAILABLE,
            (ContextAvailabilityReason.MARKET_CONTEXT_SERVICE_FAILURE,),
        ),
        input_identity=None,
        output=None,
        metadata=None,
    )
    _, result = _compose(tuple(values))
    assert result.availability.context_dependency_reasons == (
        ContextAvailabilityReason.MARKET_CONTEXT_SERVICE_FAILURE,
    )


def test_required_interpretation_dependency_unavailable_short_circuits():
    values = list(_pipeline())
    values[4] = InterpretationProjection(
        availability=InterpretationAvailability(
            InterpretationAvailabilityStatus.UNAVAILABLE,
            (InterpretationAvailabilityReason.SERVICE_FAILURE,),
        ),
        input_identity=None,
        output=(),
        metadata=None,
    )
    _, result = _compose(tuple(values))
    assert result.availability.interpretation_dependency_reasons == (
        InterpretationAvailabilityReason.SERVICE_FAILURE,
    )


def test_dependency_identity_mismatch_is_unavailable_due_to_dependency():
    values = list(_pipeline())
    context = values[3]
    assert isinstance(context, ContextProjection)
    assert context.input_identity is not None
    values[3] = replace(
        context,
        input_identity=replace(
            context.input_identity,
            market_data_series=replace(
                context.input_identity.market_data_series,
                symbol="MNQZ6",
            ),
        ),
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.DEPENDENCY_ALIGNMENT_INVALID,
    )


def _changed_setup(values, **changes):
    setups = values[2]
    assert isinstance(setups, SetupProjection)
    assert setups.output is not None
    output = replace(setups.output, **changes)
    return replace(setups, output=output, window=(*setups.window[:-1], output))


def test_duplicate_setup_identity_is_invalid():
    values = list(_pipeline())
    setups = values[2]
    assert isinstance(setups, SetupProjection)
    assert setups.output is not None
    duplicate = replace(
        setups.output.setups[1],
        setup_name=setups.output.setups[0].setup_name,
    )
    values[2] = _changed_setup(
        values, setups=(setups.output.setups[0], duplicate, *setups.output.setups[2:])
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.DUPLICATE_SETUP_IDENTITY,
    )


def test_duplicate_interpretation_mapping_is_invalid():
    values = list(_pipeline())
    interpretations = values[4]
    assert isinstance(interpretations, InterpretationProjection)
    duplicate = replace(
        interpretations.output[1],
        setup_id=interpretations.output[0].setup_id,
    )
    values[4] = replace(
        interpretations,
        output=(
            interpretations.output[0],
            duplicate,
            *interpretations.output[2:],
        ),
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.AMBIGUOUS_INTERPRETATION_MAPPING,
    )


def test_setup_to_interpretation_order_mismatch_is_invalid():
    values = list(_pipeline())
    interpretations = values[4]
    assert isinstance(interpretations, InterpretationProjection)
    values[4] = replace(
        interpretations,
        output=(
            interpretations.output[1],
            interpretations.output[0],
            *interpretations.output[2:],
        ),
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.INTERPRETATION_IDENTITY_MISMATCH,
    )


def test_context_timestamp_mismatch_is_invalid():
    values = list(_pipeline())
    context = values[3]
    assert isinstance(context, ContextProjection)
    assert context.output is not None
    values[3] = replace(
        context,
        output=replace(
            context.output,
            occurred_at=context.output.occurred_at - timedelta(minutes=5),
        ),
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.CONTEXT_TIMESTAMP_MISMATCH,
    )


def test_symbol_mismatch_is_invalid():
    values = list(_pipeline())
    values[2] = _changed_setup(values, symbol="MNQZ6")
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.SYMBOL_MISMATCH,
    )


def test_timeframe_mismatch_is_invalid():
    values = list(_pipeline())
    values[2] = _changed_setup(values, timeframe="15m")
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.TIMEFRAME_MISMATCH,
    )


def test_context_metadata_fingerprint_mismatch_is_invalid():
    values = list(_pipeline())
    context = values[3]
    assert isinstance(context, ContextProjection)
    assert context.metadata is not None
    values[3] = replace(
        context,
        metadata=replace(context.metadata, context_fingerprint="wrong"),
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.CONTEXT_FINGERPRINT_MISMATCH,
    )


def test_context_metadata_quality_mismatch_is_invalid():
    values = list(_pipeline())
    context = values[3]
    assert isinstance(context, ContextProjection)
    assert context.metadata is not None
    values[3] = replace(
        context,
        metadata=replace(context.metadata, quality=ContextQuality.UNKNOWN),
    )
    _, result = _compose(tuple(values))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.CONTEXT_QUALITY_MISMATCH,
    )


def test_requested_strategy_identity_mismatch_is_invalid():
    class OtherPlugin:
        strategy_id = "other"
        strategy_version = "1.0.0"

        def evaluate(self, frame):
            raise AssertionError("must not be invoked")

    _, result = _compose(strategies=(OtherPlugin(),))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.STRATEGY_IDENTITY_MISMATCH,
    )


def test_strategy_service_exception_is_section_local():
    values = _pipeline()

    def evaluator(frame, strategies):
        raise RuntimeError("failed")

    _, result = _compose(values, evaluator=evaluator)
    assert result.availability.status == StrategyAvailabilityStatus.UNAVAILABLE
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.SERVICE_FAILURE,
    )
    assert values[2].output is not None
    assert values[3].output is not None
    assert values[4].output


def test_empty_strategy_output_is_unavailable():
    _, result = _compose(evaluator=lambda frame, strategies: ())
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.EMPTY_OUTPUT,
    )


def test_malformed_strategy_output_is_invalid():
    _, result = _compose(
        evaluator=lambda frame, strategies: cast(
            tuple[StrategyDecision, ...], (object(),)
        )
    )
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.STRUCTURALLY_INVALID,
    )


def _canonical_decision(values) -> StrategyDecision:
    market_input, rules, setups, context, interpretations = values
    assert rules.output is not None
    assert setups.output is not None
    assert context.output is not None
    frame = ReplayFrame(
        market_state=market_input.states[-1],
        rule_engine_output=rules.output,
        setup_engine_output=setups.output,
        market_context=context.output,
        setup_interpretations=interpretations.output,
    )
    return evaluate_strategies(frame, (DisplacementVolumeContext(),))[0]


def test_strategy_output_timestamp_mismatch_is_invalid():
    values = _pipeline()
    bad = replace(
        _canonical_decision(values),
        occurred_at=NOW - timedelta(minutes=5),
    )
    _, result = _compose(values, evaluator=lambda frame, strategies: (bad,))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.TIMESTAMP_MISMATCH,
    )


def test_strategy_output_fingerprint_mismatch_is_invalid():
    values = _pipeline()
    bad = replace(_canonical_decision(values), context_fingerprint="wrong")
    _, result = _compose(values, evaluator=lambda frame, strategies: (bad,))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.CONTEXT_FINGERPRINT_MISMATCH,
    )


def test_strategy_output_identity_mismatch_is_invalid():
    values = _pipeline()
    bad = replace(_canonical_decision(values), strategy_version="wrong")
    _, result = _compose(values, evaluator=lambda frame, strategies: (bad,))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.STRATEGY_IDENTITY_MISMATCH,
    )


def test_unsupported_canonical_disposition_is_invalid():
    values = _pipeline()
    bad = copy(_canonical_decision(values))
    object.__setattr__(bad, "disposition", "unexpected")
    _, result = _compose(values, evaluator=lambda frame, strategies: (bad,))
    assert result.availability.reason_codes == (
        StrategyAvailabilityReason.UNSUPPORTED_DISPOSITION,
    )


def test_metadata_preserves_versions_context_and_canonical_results():
    values, result = _compose()
    assert result.metadata is not None
    assert values[3].output is not None
    decision = result.output[0]
    assert result.metadata.strategy_versions == {
        decision.strategy_id: decision.strategy_version
    }
    assert result.metadata.dispositions == {decision.strategy_id: decision.disposition}
    assert result.metadata.reason_codes == {decision.strategy_id: decision.reason_codes}
    assert result.metadata.context_fingerprint == values[3].output.context_fingerprint
    assert result.metadata.context_quality == values[3].output.quality


def test_candidate_live_replay_equivalence():
    values = _pipeline()
    _, result = _compose(values)
    replay_frame = build_replay_output_window(
        list(values[0].states), classifier=_SMALL
    )[-1]
    expected = evaluate_strategies(replay_frame, (DisplacementVolumeContext(),))
    assert result.output == expected


def test_rejected_live_replay_equivalence():
    strict = replace(
        _SMALL,
        params=replace(_SMALL.params, min_bars_required=22),
    )
    values = _pipeline(classifier=strict)
    _, result = _compose(values)
    replay_frame = build_replay_output_window(
        list(values[0].states), classifier=strict
    )[-1]
    assert result.output == evaluate_strategies(
        replay_frame, (DisplacementVolumeContext(),)
    )


def test_no_signal_live_replay_equivalence():
    values = _pipeline(states=_states(volume_ratio=1.0))
    _, result = _compose(values)
    replay_frame = build_replay_output_window(
        list(values[0].states), classifier=_SMALL
    )[-1]
    assert result.output == evaluate_strategies(
        replay_frame, (DisplacementVolumeContext(),)
    )
