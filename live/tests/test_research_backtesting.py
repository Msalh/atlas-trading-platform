"""
Phase N4 Sprint 8. Tests for atlas.research.backtesting: execute_realization()
determinism, ResearchStrategyFactory's purity/completeness/explicit-failure
contract, ThresholdCrossPlugin's own concrete behavior, and the mechanical
proof that ResearchStrategyPlugin is structurally distinct from
atlas.strategy_engine.ports.StrategyPlugin.

Note: atlas.strategy_engine.ports.StrategyPlugin is NOT @runtime_checkable
(see that module - only typing.Protocol, no runtime_checkable import), so
isinstance(x, StrategyPlugin) raises TypeError rather than doing a
structural check. The one-direction isinstance proof therefore only works
for ResearchStrategyPlugin (which IS @runtime_checkable, by this sprint's
own design); the other direction is proven the same way
test_strategy_engine_ports.py already proves StrategyPlugin conformance -
an explicit hasattr-based shape check, not isinstance().
"""
from datetime import datetime, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
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
from atlas.research.backtesting.factory import _DISPATCH, build_plugin
from atlas.research.backtesting.models import ResearchDecision, ResearchDispositionKind
from atlas.research.backtesting.ports import ResearchStrategyPlugin
from atlas.research.backtesting.service import execute_realization
from atlas.research.backtesting.templates import ThresholdCrossPlugin
from atlas.research.models import (
    ProvenanceKind,
    Realization,
    RealizationKind,
    RealizationStatus,
    RealizationTemplateKind,
)
from atlas.research.replay_bridge import ReplayFrame
from atlas.rule_engine.models import RuleEngineOutput
from atlas.setup_engine.models import SetupEngineOutput
from atlas.strategy_engine.models import StrategyDecision, StrategyDirection, StrategyDisposition

_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
_TICK_SIZE = 0.25


class _NoSignalStrategyPlugin:
    """A minimal, production-shaped StrategyPlugin fake - mirrors
    test_strategy_engine_ports.py's own _NoSignalPlugin exactly, reused
    here only to prove it does NOT structurally satisfy
    ResearchStrategyPlugin."""

    @property
    def strategy_id(self) -> str:
        return "no_signal_stub"

    @property
    def strategy_version(self) -> str:
        return "STUB_V1"

    def evaluate(self, frame: ReplayFrame) -> StrategyDecision:
        return StrategyDecision(
            occurred_at=frame.market_context.occurred_at,
            strategy_id=self.strategy_id, strategy_version=self.strategy_version,
            disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
            setup_ids=(), reason_codes=(), context_fingerprint=frame.market_context.context_fingerprint,
        )


def _satisfies_strategy_plugin_shape(obj) -> bool:
    return (
        hasattr(obj, "strategy_id") and hasattr(obj, "strategy_version") and callable(getattr(obj, "evaluate", None))
    )


def _market_state(close_value=None) -> MarketState:
    close = Price(value=close_value, tick_size=_TICK_SIZE) if close_value is not None else None
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=_OCCURRED_AT, event_id="e0"),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        close=close,
    )


def _rule_engine_output() -> RuleEngineOutput:
    return RuleEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=_OCCURRED_AT.isoformat(), facts={},
    )


def _setup_engine_output() -> SetupEngineOutput:
    return SetupEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=_OCCURRED_AT.isoformat(), setups=(),
    )


def _market_context(context_fingerprint="0123456789abcdef") -> MarketContext:
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
        context_fingerprint=context_fingerprint,
    )


def _frame(close_value=None, context_fingerprint="0123456789abcdef") -> ReplayFrame:
    return ReplayFrame(
        market_state=_market_state(close_value), rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(), market_context=_market_context(context_fingerprint),
        setup_interpretations=(),
    )


def _realization(**overrides) -> Realization:
    fields = dict(
        realization_id="r1", hypothesis_id="h1", kind=RealizationKind.TEMPLATED_STRATEGY, version="v1",
        parameters={"threshold": 100.0}, status=RealizationStatus.CONSTRUCTED, provenance=ProvenanceKind.HUMAN,
        created_at=_OCCURRED_AT.isoformat(), fingerprint="0123456789abcdef",
        template_kind=RealizationTemplateKind.THRESHOLD_CROSS,
    )
    fields.update(overrides)
    return Realization(**fields)


# ---- execute_realization(): non-executable kinds rejected explicitly ----

@pytest.mark.parametrize("kind", [
    RealizationKind.STATISTICAL_TEST, RealizationKind.CONTEXT_FILTER, RealizationKind.RISK_INPUT,
])
def test_execute_realization_rejects_non_executable_kinds(kind):
    realization = _realization(kind=kind, template_kind=None)
    with pytest.raises(ValueError, match="no executable meaning"):
        execute_realization(realization, [_frame(close_value=99.0)])


# ---- execute_realization(): shape and determinism ----

def test_execute_realization_produces_one_decision_per_frame():
    realization = _realization()
    frames = [_frame(close_value=v) for v in (99.0, 101.0, 99.0)]
    decisions = execute_realization(realization, frames)
    assert len(decisions) == len(frames)
    assert all(isinstance(d, ResearchDecision) for d in decisions)


def test_execute_realization_is_deterministic():
    realization = _realization()
    frames = [_frame(close_value=v) for v in (99.0, 101.0, 99.0, 101.0)]
    first = execute_realization(realization, frames)
    second = execute_realization(realization, list(frames))
    assert first == second


# ---- ThresholdCrossPlugin behavior ----

def test_threshold_cross_plugin_enters_long_on_cross_up_and_exits_on_cross_down():
    realization = _realization(parameters={"threshold": 100.0})
    frames = [_frame(close_value=v) for v in (99.0, 101.0, 99.0)]
    decisions = execute_realization(realization, frames)
    assert decisions[0].disposition == ResearchDispositionKind.NO_ACTION  # no prior close yet
    assert decisions[1].disposition == ResearchDispositionKind.ENTER_LONG  # 99 -> 101 crosses up
    assert decisions[2].disposition == ResearchDispositionKind.EXIT  # 101 -> 99 crosses down


def test_threshold_cross_plugin_no_action_when_never_crossing():
    realization = _realization(parameters={"threshold": 100.0})
    frames = [_frame(close_value=v) for v in (10.0, 11.0, 12.0)]
    decisions = execute_realization(realization, frames)
    assert all(d.disposition == ResearchDispositionKind.NO_ACTION for d in decisions)


def test_threshold_cross_plugin_decision_carries_frame_context():
    realization = _realization()
    frame = _frame(close_value=99.0, context_fingerprint="fp-specific")
    decision = execute_realization(realization, [frame])[0]
    assert decision.occurred_at == frame.market_context.occurred_at
    assert decision.context_fingerprint == "fp-specific"
    assert decision.realization_id == realization.realization_id


# ---- ResearchStrategyFactory: purity, completeness, explicit failure ----

def test_factory_dispatch_depends_only_on_template_kind_and_version():
    a = _realization(realization_id="r-a", parameters={"threshold": 1.0})
    b = _realization(realization_id="r-b", parameters={"threshold": 999.0})
    assert type(build_plugin(a)) is type(build_plugin(b))


def test_factory_completeness_every_template_kind_has_a_supported_version():
    covered_kinds = {kind for kind, _version in _DISPATCH}
    assert covered_kinds == set(RealizationTemplateKind)


def test_factory_raises_explicitly_for_unsupported_version():
    realization = _realization(version="v99")
    with pytest.raises(ValueError, match="no registered plugin"):
        build_plugin(realization)


def test_build_plugin_returns_a_research_strategy_plugin():
    plugin = build_plugin(_realization())
    assert isinstance(plugin, ResearchStrategyPlugin)
    assert isinstance(plugin, ThresholdCrossPlugin)


# ---- structural separation from atlas.strategy_engine.ports.StrategyPlugin ----

def test_a_production_strategy_plugin_does_not_satisfy_research_strategy_plugin():
    assert not isinstance(_NoSignalStrategyPlugin(), ResearchStrategyPlugin)


def test_a_research_strategy_plugin_does_not_satisfy_production_strategy_plugin_shape():
    plugin = build_plugin(_realization())
    assert not _satisfies_strategy_plugin_shape(plugin)
