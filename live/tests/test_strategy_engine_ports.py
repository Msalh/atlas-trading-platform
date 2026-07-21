"""
Phase N3, Sprint 1. Tests for atlas.strategy_engine.ports.StrategyPlugin -
the Protocol every deterministic strategy plugin must satisfy. No concrete
trading strategy exists yet (out of Sprint 1's scope); these tests
exercise the contract itself via a minimal, hand-built conforming fake.
"""
from datetime import datetime, timezone

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.models import (
    ContextQuality,
    DriftStatus,
    MarketContext,
    SessionClassification,
    SessionPhase,
    SessionProgress,
    VolatilityClassification,
    VolatilityRegime,
)
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.models import ReplayFrame
from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import SetupEngineOutput
from atlas.strategy_engine.models import StrategyDecision, StrategyDirection, StrategyDisposition
from atlas.strategy_engine.ports import StrategyPlugin

_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class _NoSignalPlugin:
    """The minimal possible conforming plugin - always returns NO_SIGNAL,
    ignoring the frame's content entirely. Exists only to prove the
    Protocol's shape is satisfiable by ordinary structural typing, with no
    base class and no registration mechanism - never a real strategy."""

    @property
    def strategy_id(self) -> str:
        return "no_signal_stub"

    @property
    def strategy_version(self) -> str:
        return "STUB_V1"

    def evaluate(self, frame: ReplayFrame) -> StrategyDecision:
        return StrategyDecision(
            occurred_at=frame.market_context.occurred_at,
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            disposition=StrategyDisposition.NO_SIGNAL,
            direction=StrategyDirection.FLAT,
            setup_ids=(),
            reason_codes=(),
            context_fingerprint=frame.market_context.context_fingerprint,
        )


def _market_state() -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=_OCCURRED_AT, event_id="e0"),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
    )


def _rule_engine_output() -> RuleEngineOutput:
    return RuleEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=_OCCURRED_AT.isoformat(), facts={},
    )


def _setup_engine_output() -> SetupEngineOutput:
    return SetupEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=_OCCURRED_AT.isoformat(), setups=(),
    )


def _market_context() -> MarketContext:
    session = SessionClassification(
        phase=SessionPhase.MID_SESSION,
        progress=SessionProgress(
            session_open_at=_OCCURRED_AT, session_close_at=_OCCURRED_AT,
            minutes_since_session_open=5, minutes_until_session_close=395,
        ),
        upstream_session_name="RTH", upstream_is_rth=True, drift_status=DriftStatus.AGREEMENT,
    )
    volatility = VolatilityClassification(
        regime=VolatilityRegime.NORMAL, atr_percentile_rank=0.5, lookback_bars_used=288,
    )
    return MarketContext(
        symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, occurred_at=_OCCURRED_AT,
        session=session, volatility=volatility, quality=ContextQuality.TRUSTED,
        classifier_version="REGIME_CLASSIFIER_V1", calendar_version="CME_RTH_V1",
        context_fingerprint="0123456789abcdef",
    )


def _frame() -> ReplayFrame:
    return ReplayFrame(
        market_state=_market_state(), rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(), market_context=_market_context(),
    )


def _satisfies_strategy_plugin_shape(obj) -> bool:
    return (
        hasattr(obj, "strategy_id") and hasattr(obj, "strategy_version") and callable(getattr(obj, "evaluate", None))
    )


# ---- structural conformance ----

def test_a_hand_built_class_with_no_base_class_satisfies_the_protocol_structurally():
    plugin: StrategyPlugin = _NoSignalPlugin()
    assert _satisfies_strategy_plugin_shape(plugin)


# ---- stable identity/version ----

def test_strategy_id_and_version_are_stable_across_repeated_access():
    plugin = _NoSignalPlugin()
    first_id, first_version = plugin.strategy_id, plugin.strategy_version
    for _ in range(50):
        assert plugin.strategy_id == first_id
        assert plugin.strategy_version == first_version


def test_strategy_id_and_version_are_non_blank():
    plugin = _NoSignalPlugin()
    assert plugin.strategy_id.strip() != ""
    assert plugin.strategy_version.strip() != ""


# ---- evaluate() contract ----

def test_evaluate_returns_a_strategy_decision_derived_from_the_frame():
    plugin = _NoSignalPlugin()
    frame = _frame()
    decision = plugin.evaluate(frame)
    assert isinstance(decision, StrategyDecision)
    assert decision.occurred_at == frame.market_context.occurred_at
    assert decision.context_fingerprint == frame.market_context.context_fingerprint
    assert decision.disposition == StrategyDisposition.NO_SIGNAL
    assert decision.direction == StrategyDirection.FLAT


def test_evaluate_is_deterministic_across_repeated_calls_on_the_same_frame():
    plugin = _NoSignalPlugin()
    frame = _frame()
    results = [plugin.evaluate(frame) for _ in range(100)]
    assert all(result == results[0] for result in results)


def test_evaluate_does_not_mutate_the_frame():
    plugin = _NoSignalPlugin()
    frame = _frame()
    original_market_state = frame.market_state
    original_market_context = frame.market_context
    plugin.evaluate(frame)
    assert frame.market_state is original_market_state
    assert frame.market_context is original_market_context


# ---- no ReplaySession dependency ----

def test_no_replay_session_reference_in_ports_module():
    import atlas.strategy_engine.ports as strategy_engine_ports
    assert not hasattr(strategy_engine_ports, "ReplaySession")
