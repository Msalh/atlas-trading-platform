"""
Phase N3, Sprint 3. Tests for
atlas.strategy_engine.strategies.displacement_volume_context.DisplacementVolumeContext -
the first concrete StrategyPlugin. Every ReplayFrame here is built from
real project model constructors (MarketState, RuleEngineOutput,
SetupEngineOutput, MarketContext), not loose mocks, so these tests
exercise the plugin against the actual typed shapes it reads in
production.
"""
import ast
from datetime import datetime, timezone
from pathlib import Path

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
from atlas.rule_engine.models import FactResult, RuleEngineOutput
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.setup_engine.models import InsufficientData as SetupInsufficientData
from atlas.setup_engine.models import SetupEngineOutput, SetupEvidence, SetupResult, Severity
from atlas.strategy_engine.models import StrategyDirection, StrategyDisposition
from atlas.strategy_engine.service import evaluate_strategies
from atlas.strategy_engine.strategies.displacement_volume_context import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    TARGET_SETUP_NAME,
    DisplacementVolumeContext,
)

_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
_FINGERPRINT = "0123456789abcdef"


def _market_state() -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=_OCCURRED_AT, event_id="e0"),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
    )


def _rule_engine_output(trend_outcome=None) -> RuleEngineOutput:
    facts = {}
    if trend_outcome is not None:
        facts["trend_5m"] = trend_outcome
    return RuleEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=_OCCURRED_AT.isoformat(), facts=facts,
    )


def _setup_engine_output(setup_outcome=None) -> SetupEngineOutput:
    setups = (setup_outcome,) if setup_outcome is not None else ()
    return SetupEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=_OCCURRED_AT.isoformat(), setups=setups,
    )


def _market_context(quality: ContextQuality = ContextQuality.TRUSTED) -> MarketContext:
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
        session=session, volatility=volatility, quality=quality,
        classifier_version="REGIME_CLASSIFIER_V1", calendar_version="CME_RTH_V1",
        context_fingerprint=_FINGERPRINT,
    )


def _frame(setup_outcome=None, trend_outcome=None, quality: ContextQuality = ContextQuality.TRUSTED) -> ReplayFrame:
    return ReplayFrame(
        market_state=_market_state(),
        rule_engine_output=_rule_engine_output(trend_outcome),
        setup_engine_output=_setup_engine_output(setup_outcome),
        market_context=_market_context(quality),
    )


def _triggered_setup() -> SetupResult:
    return SetupResult(
        setup_name=TARGET_SETUP_NAME, definition_version="1.0", detected=True, severity=Severity.NORMAL,
        evidence=SetupEvidence(supporting_facts=()),
    )


def _not_triggered_setup() -> SetupResult:
    return SetupResult(
        setup_name=TARGET_SETUP_NAME, definition_version="1.0", detected=False, severity=None,
        evidence=SetupEvidence(supporting_facts=()),
    )


def _insufficient_setup() -> SetupInsufficientData:
    return SetupInsufficientData(setup_name=TARGET_SETUP_NAME, definition_version="1.0", reason="no history")


def _trend(value: str) -> FactResult:
    return FactResult(fact_name="trend_5m", definition_version="1.0", value=value, evidence={})


def _insufficient_trend() -> FactInsufficientData:
    return FactInsufficientData(fact_name="trend_5m", definition_version="1.0", reason="not enough bars")


_UP = _trend("up")
_DOWN = _trend("down")
_FLAT = _trend("flat")


# ---- 1. stable strategy_id and strategy_version ----

def test_strategy_id_and_version_are_stable():
    plugin = DisplacementVolumeContext()
    assert plugin.strategy_id == STRATEGY_ID == "displacement_volume_context"
    assert plugin.strategy_version == STRATEGY_VERSION == "1.0.0"
    for _ in range(20):
        assert plugin.strategy_id == STRATEGY_ID
        assert plugin.strategy_version == STRATEGY_VERSION


# ---- 2. target setup absent -> NO_SIGNAL / FLAT ----

def test_setup_absent_from_output_yields_no_signal_flat():
    frame = _frame(setup_outcome=None, trend_outcome=_UP)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.NO_SIGNAL
    assert decision.direction == StrategyDirection.FLAT
    assert decision.setup_ids == ()
    assert decision.reason_codes == ("setup_absent",)


def test_setup_evaluated_as_insufficient_data_yields_no_signal_flat():
    frame = _frame(setup_outcome=_insufficient_setup(), trend_outcome=_UP)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.NO_SIGNAL
    assert decision.direction == StrategyDirection.FLAT


# ---- 3. setup present but not triggered -> NO_SIGNAL / FLAT ----

def test_setup_present_but_not_triggered_yields_no_signal_flat():
    frame = _frame(setup_outcome=_not_triggered_setup(), trend_outcome=_UP)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.NO_SIGNAL
    assert decision.direction == StrategyDirection.FLAT
    assert decision.setup_ids == ()


# ---- 4/5. long/short accepted candidate ----

def test_long_accepted_candidate():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP, quality=ContextQuality.TRUSTED)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.CANDIDATE
    assert decision.direction == StrategyDirection.LONG
    assert decision.reason_codes == ("accepted",)


def test_short_accepted_candidate():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_DOWN, quality=ContextQuality.TRUSTED)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.CANDIDATE
    assert decision.direction == StrategyDirection.SHORT
    assert decision.reason_codes == ("accepted",)


def test_degraded_context_quality_still_allows_a_candidate():
    """DEGRADED is documented as still-trustworthy for volatility - the
    only Market Context signal this plugin's acceptance logic reads."""
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP, quality=ContextQuality.DEGRADED)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.CANDIDATE


# ---- 6. insufficient/untrusted context -> REJECTED / FLAT ----

def test_unknown_context_quality_rejects():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP, quality=ContextQuality.UNKNOWN)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.REJECTED
    assert decision.direction == StrategyDirection.FLAT
    assert decision.reason_codes == ("context_insufficient",)


def test_trend_insufficient_data_rejects_as_context_insufficient():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_insufficient_trend())
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.REJECTED
    assert decision.direction == StrategyDirection.FLAT
    assert decision.reason_codes == ("context_insufficient",)


def test_trend_absent_from_facts_rejects_as_context_insufficient():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=None)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.REJECTED
    assert decision.reason_codes == ("context_insufficient",)


# ---- 7. context/trend-direction conflict -> REJECTED / FLAT ----

def test_flat_trend_is_a_context_conflict_and_rejects():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_FLAT, quality=ContextQuality.TRUSTED)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.disposition == StrategyDisposition.REJECTED
    assert decision.direction == StrategyDirection.FLAT
    assert decision.reason_codes == ("context_conflict",)


# ---- 8. candidate contains the target setup ID ----

def test_candidate_contains_the_target_setup_id():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.setup_ids == (TARGET_SETUP_NAME,)


def test_rejected_also_contains_the_target_setup_id_since_it_was_recognized():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_FLAT)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.setup_ids == (TARGET_SETUP_NAME,)


# ---- 9. decisions use frame occurred_at and context fingerprint exactly ----

def test_decisions_use_the_frame_occurred_at_and_context_fingerprint_exactly():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP)
    decision = DisplacementVolumeContext().evaluate(frame)
    assert decision.occurred_at == frame.market_state.envelope.occurred_at
    assert decision.context_fingerprint == frame.market_context.context_fingerprint


# ---- 10. no stop/target/invalidation/confidence invented ----

def test_no_stop_target_invalidation_or_confidence_is_ever_invented():
    frames = [
        _frame(setup_outcome=None),
        _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP),
        _frame(setup_outcome=_triggered_setup(), trend_outcome=_DOWN),
        _frame(setup_outcome=_triggered_setup(), trend_outcome=_FLAT),
        _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP, quality=ContextQuality.UNKNOWN),
    ]
    for frame in frames:
        decision = DisplacementVolumeContext().evaluate(frame)
        assert decision.stop is None
        assert decision.target is None
        assert decision.invalidation is None
        assert decision.confidence is None


# ---- 11. determinism across repeated evaluations ----

def test_determinism_across_repeated_evaluations():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP)
    plugin = DisplacementVolumeContext()
    results = [plugin.evaluate(frame) for _ in range(100)]
    assert all(result == results[0] for result in results)


# ---- 12. ReplayFrame is not mutated ----

def test_replay_frame_is_not_mutated():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP)
    original_market_state = frame.market_state
    original_setup_engine_output = frame.setup_engine_output
    original_rule_engine_output = frame.rule_engine_output
    original_market_context = frame.market_context

    DisplacementVolumeContext().evaluate(frame)

    assert frame.market_state is original_market_state
    assert frame.setup_engine_output is original_setup_engine_output
    assert frame.rule_engine_output is original_rule_engine_output
    assert frame.market_context is original_market_context


# ---- 13. works through evaluate_strategies() without special handling ----

def test_works_through_evaluate_strategies_without_special_handling():
    frame = _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP)
    result = evaluate_strategies(frame, [DisplacementVolumeContext()])
    assert len(result) == 1
    assert result[0].disposition == StrategyDisposition.CANDIDATE
    assert result[0].strategy_id == STRATEGY_ID
    assert result[0].strategy_version == STRATEGY_VERSION


def test_multiple_frames_through_evaluate_strategies_produce_independent_decisions():
    plugin = DisplacementVolumeContext()
    trusted_up = evaluate_strategies(_frame(setup_outcome=_triggered_setup(), trend_outcome=_UP), [plugin])
    unknown_context = evaluate_strategies(
        _frame(setup_outcome=_triggered_setup(), trend_outcome=_UP, quality=ContextQuality.UNKNOWN), [plugin],
    )
    assert trusted_up[0].disposition == StrategyDisposition.CANDIDATE
    assert unknown_context[0].disposition == StrategyDisposition.REJECTED


# ---- 14. dependency audit for the concrete strategy module ----

_STRATEGY_MODULE = (
    Path(__file__).resolve().parent.parent / "atlas" / "strategy_engine" / "strategies"
    / "displacement_volume_context.py"
)

_ALLOWED_ATLAS_IMPORTS = frozenset({
    "atlas.market_context.models",
    "atlas.replay_engine.models",
    "atlas.rule_engine.models",
    "atlas.setup_engine.models",
    "atlas.strategy_engine.models",
})

_FORBIDDEN_PREFIXES = (
    "atlas.market_engine", "atlas.repositories", "atlas.api", "atlas.events", "atlas.execution",
    "atlas.paper_trading", "atlas.brokers", "atlas.services", "atlas.research", "atlas.research_export",
    "atlas.live_view", "atlas.profiling",
)


def _imported_module_roots(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def test_dependency_audit_only_approved_atlas_modules_are_imported():
    atlas_imports = {name for name in _imported_module_roots(_STRATEGY_MODULE) if name.startswith("atlas.")}
    assert atlas_imports <= _ALLOWED_ATLAS_IMPORTS, f"unexpected imports: {atlas_imports - _ALLOWED_ATLAS_IMPORTS}"


def test_dependency_audit_rule_engine_import_is_limited_to_models_only():
    """The one disclosed widening this Sprint makes to Strategy Engine's
    Sprint 1 dependency ceiling - see this module's own docstring."""
    imported = _imported_module_roots(_STRATEGY_MODULE)
    rule_engine_imports = {name for name in imported if name.startswith("atlas.rule_engine")}
    assert rule_engine_imports == {"atlas.rule_engine.models"}


def test_dependency_audit_no_forbidden_package_is_imported():
    atlas_imports = {name for name in _imported_module_roots(_STRATEGY_MODULE) if name.startswith("atlas.")}
    for name in atlas_imports:
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"forbidden import: {name}"


def test_dependency_audit_no_async_or_networking_constructs():
    source = _STRATEGY_MODULE.read_text(encoding="utf-8")
    assert "async def" not in source
    assert "import asyncio" not in source
