"""
Phase N3, Sprint 2. Tests for atlas.strategy_engine.service.evaluate_strategies()
- the pure evaluation service composing one or more StrategyPlugin
implementations against one ReplayFrame. No concrete trading strategy
exists yet; every plugin here is a small, deterministic fake built only to
exercise the service's own contract (ordering, alignment, propagation,
non-mutation) - never a real strategy.
"""
from datetime import datetime, timedelta, timezone

import pytest
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
from atlas.strategy_engine.service import (
    StrategyContextFingerprintMismatchError,
    StrategyIdentityMismatchError,
    StrategyOccurredAtMismatchError,
    evaluate_strategies,
)

_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
_FINGERPRINT = "0123456789abcdef"


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
        context_fingerprint=_FINGERPRINT,
    )


def _frame() -> ReplayFrame:
    return ReplayFrame(
        market_state=_market_state(), rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(), market_context=_market_context(),
        setup_interpretations=(),  # Sprint 5 schema field, unused by evaluate_strategies() itself
    )


def _aligned_no_signal_decision(frame: ReplayFrame, strategy_id: str, strategy_version: str) -> StrategyDecision:
    return StrategyDecision(
        occurred_at=frame.market_state.envelope.occurred_at,
        strategy_id=strategy_id, strategy_version=strategy_version,
        disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
        setup_ids=(), reason_codes=(), context_fingerprint=frame.market_context.context_fingerprint,
    )


def _aligned_candidate_decision(frame: ReplayFrame, strategy_id: str, strategy_version: str) -> StrategyDecision:
    return StrategyDecision(
        occurred_at=frame.market_state.envelope.occurred_at,
        strategy_id=strategy_id, strategy_version=strategy_version,
        disposition=StrategyDisposition.CANDIDATE, direction=StrategyDirection.LONG,
        setup_ids=("displacement_with_volume_confirmation",), reason_codes=(),
        context_fingerprint=frame.market_context.context_fingerprint,
    )


class _FakePlugin:
    """A minimal, deterministic conforming plugin - returns whatever
    `decision_builder` produces (defaulting to an aligned NO_SIGNAL
    decision), letting each test construct exactly the aligned or
    misaligned scenario it needs without a real trading strategy."""

    def __init__(self, strategy_id, strategy_version, decision_builder=None):
        self._strategy_id = strategy_id
        self._strategy_version = strategy_version
        self._decision_builder = decision_builder or _aligned_no_signal_decision
        self.call_count = 0

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def strategy_version(self) -> str:
        return self._strategy_version

    def evaluate(self, frame: ReplayFrame) -> StrategyDecision:
        self.call_count += 1
        return self._decision_builder(frame, self._strategy_id, self._strategy_version)


class _BoomError(Exception):
    pass


class _RaisingPlugin:
    strategy_id = "raiser"
    strategy_version = "V1"

    def evaluate(self, frame: ReplayFrame) -> StrategyDecision:
        raise _BoomError("plugin exploded")


# ---- 1. empty strategy sequence ----

def test_empty_strategy_sequence_returns_empty_tuple():
    assert evaluate_strategies(_frame(), []) == ()


# ---- 2. single strategy evaluated exactly once ----

def test_single_strategy_evaluated_exactly_once():
    plugin = _FakePlugin("solo", "V1")
    evaluate_strategies(_frame(), [plugin])
    assert plugin.call_count == 1


# ---- 3. multiple strategies preserve input order ----

def test_multiple_strategies_preserve_input_order():
    a = _FakePlugin("alpha", "V1")
    b = _FakePlugin("beta", "V1")
    c = _FakePlugin("gamma", "V1")
    result = evaluate_strategies(_frame(), [a, b, c])
    assert [d.strategy_id for d in result] == ["alpha", "beta", "gamma"]


# ---- 4. returned value is a tuple ----

def test_returned_value_is_a_tuple():
    result = evaluate_strategies(_frame(), [_FakePlugin("solo", "V1")])
    assert isinstance(result, tuple)


# ---- 5. plugin decisions returned by object identity, not rebuilt ----

def test_plugin_decisions_are_returned_by_object_identity_not_rebuilt():
    frame = _frame()
    fixed_decision = _aligned_no_signal_decision(frame, "solo", "V1")
    plugin = _FakePlugin("solo", "V1", decision_builder=lambda f, sid, sv: fixed_decision)
    result = evaluate_strategies(frame, [plugin])
    assert result[0] is fixed_decision


# ---- 6. ReplayFrame is not mutated ----

def test_replay_frame_is_not_mutated():
    frame = _frame()
    original_market_state = frame.market_state
    original_market_context = frame.market_context
    original_rule_engine_output = frame.rule_engine_output
    original_setup_engine_output = frame.setup_engine_output

    evaluate_strategies(frame, [_FakePlugin("solo", "V1"), _FakePlugin("solo2", "V1")])

    assert frame.market_state is original_market_state
    assert frame.market_context is original_market_context
    assert frame.rule_engine_output is original_rule_engine_output
    assert frame.setup_engine_output is original_setup_engine_output


# ---- 7. strategy sequence is not mutated ----

def test_strategy_sequence_is_not_mutated():
    strategies = [_FakePlugin("alpha", "V1"), _FakePlugin("beta", "V1")]
    strategies_copy = list(strategies)
    evaluate_strategies(_frame(), strategies)
    assert strategies == strategies_copy
    assert all(a is b for a, b in zip(strategies, strategies_copy))


# ---- 8. plugin exception propagates unchanged ----

def test_plugin_exception_propagates_unchanged():
    with pytest.raises(_BoomError, match="plugin exploded"):
        evaluate_strategies(_frame(), [_RaisingPlugin()])


def test_plugin_exception_stops_evaluation_of_later_plugins():
    later = _FakePlugin("later", "V1")
    with pytest.raises(_BoomError):
        evaluate_strategies(_frame(), [_RaisingPlugin(), later])
    assert later.call_count == 0


# ---- 9. occurred_at mismatch fails loudly ----

def test_occurred_at_mismatch_raises():
    def _bad_decision(frame, strategy_id, strategy_version):
        return StrategyDecision(
            occurred_at=frame.market_state.envelope.occurred_at + timedelta(minutes=5),
            strategy_id=strategy_id, strategy_version=strategy_version,
            disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
            setup_ids=(), reason_codes=(), context_fingerprint=frame.market_context.context_fingerprint,
        )
    plugin = _FakePlugin("bad", "V1", decision_builder=_bad_decision)
    with pytest.raises(StrategyOccurredAtMismatchError):
        evaluate_strategies(_frame(), [plugin])


# ---- 10. context_fingerprint mismatch fails loudly ----

def test_context_fingerprint_mismatch_raises():
    def _bad_decision(frame, strategy_id, strategy_version):
        return StrategyDecision(
            occurred_at=frame.market_state.envelope.occurred_at,
            strategy_id=strategy_id, strategy_version=strategy_version,
            disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
            setup_ids=(), reason_codes=(), context_fingerprint="ffffffffffffffff",
        )
    plugin = _FakePlugin("bad", "V1", decision_builder=_bad_decision)
    with pytest.raises(StrategyContextFingerprintMismatchError):
        evaluate_strategies(_frame(), [plugin])


# ---- 11. strategy_id mismatch fails loudly ----

def test_strategy_id_mismatch_raises():
    def _bad_decision(frame, strategy_id, strategy_version):
        return StrategyDecision(
            occurred_at=frame.market_state.envelope.occurred_at,
            strategy_id="not_the_plugins_own_id", strategy_version=strategy_version,
            disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
            setup_ids=(), reason_codes=(), context_fingerprint=frame.market_context.context_fingerprint,
        )
    plugin = _FakePlugin("real_id", "V1", decision_builder=_bad_decision)
    with pytest.raises(StrategyIdentityMismatchError):
        evaluate_strategies(_frame(), [plugin])


# ---- 12. strategy_version mismatch fails loudly ----

def test_strategy_version_mismatch_raises():
    def _bad_decision(frame, strategy_id, strategy_version):
        return StrategyDecision(
            occurred_at=frame.market_state.envelope.occurred_at,
            strategy_id=strategy_id, strategy_version="NOT_THE_PLUGINS_OWN_VERSION",
            disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
            setup_ids=(), reason_codes=(), context_fingerprint=frame.market_context.context_fingerprint,
        )
    plugin = _FakePlugin("real_id", "V1", decision_builder=_bad_decision)
    with pytest.raises(StrategyIdentityMismatchError):
        evaluate_strategies(_frame(), [plugin])


# ---- 13. determinism across repeated runs ----

def test_determinism_across_repeated_runs_with_deterministic_plugins():
    frame = _frame()
    strategies = [_FakePlugin("alpha", "V1"), _FakePlugin("beta", "V1", decision_builder=_aligned_candidate_decision)]
    first = evaluate_strategies(frame, strategies)
    second = evaluate_strategies(frame, strategies)
    assert first == second


# ---- 14. two plugins may legitimately return different dispositions ----

def test_two_plugins_may_return_different_dispositions_for_the_same_frame():
    frame = _frame()
    no_signal_plugin = _FakePlugin("alpha", "V1", decision_builder=_aligned_no_signal_decision)
    candidate_plugin = _FakePlugin("beta", "V1", decision_builder=_aligned_candidate_decision)
    result = evaluate_strategies(frame, [no_signal_plugin, candidate_plugin])
    assert result[0].disposition == StrategyDisposition.NO_SIGNAL
    assert result[1].disposition == StrategyDisposition.CANDIDATE
    assert result[1].direction == StrategyDirection.LONG


# ---- 15. no aggregation or filtering occurs ----

def test_no_aggregation_or_filtering_every_decision_preserved_independently():
    frame = _frame()
    long_plugin = _FakePlugin("alpha", "V1", decision_builder=_aligned_candidate_decision)

    def _short_decision(frame, strategy_id, strategy_version):
        return StrategyDecision(
            occurred_at=frame.market_state.envelope.occurred_at,
            strategy_id=strategy_id, strategy_version=strategy_version,
            disposition=StrategyDisposition.CANDIDATE, direction=StrategyDirection.SHORT,
            setup_ids=("liquidity_sweep_with_volume_confirmation",), reason_codes=(),
            context_fingerprint=frame.market_context.context_fingerprint,
        )
    short_plugin = _FakePlugin("beta", "V1", decision_builder=_short_decision)

    result = evaluate_strategies(frame, [long_plugin, short_plugin])

    # Both conflicting CANDIDATE decisions come back untouched - no
    # ranking, no winner selection, no reconciliation.
    assert len(result) == 2
    assert result[0].direction == StrategyDirection.LONG
    assert result[1].direction == StrategyDirection.SHORT
