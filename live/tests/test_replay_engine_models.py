"""
Phase N2, Sprint 1; widened Sprint 5 (Setup Interpretation integration).
Tests for atlas.replay_engine.models.ReplayFrame - a frozen, aligned
bundle of the five objects that already describe one historical bar. No
behavior beyond immutability and value equality is exercised here -
ReplayFrame computes nothing.
"""
import atlas.replay_engine.models as replay_engine_models
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
from atlas.setup_interpretation.models import DirectionSource, SetupDirection, SetupInterpretation
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
_RECEIVED_AT = datetime(2026, 7, 21, 12, 0, 1, tzinfo=timezone.utc)


def _market_state() -> MarketState:
    return MarketState(
        envelope=Event(
            event_type="bar_closed", source="test",
            occurred_at=_OCCURRED_AT, received_at=_RECEIVED_AT, event_id="e0",
        ),
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


def _setup_interpretations() -> tuple:
    """A single, real-shaped, hand-built SetupInterpretation - deliberately
    non-empty (unlike _setup_engine_output()'s own empty setups=()) so the
    identity/equality tests below exercise a genuine object, not CPython's
    interned empty-tuple singleton (which would make an identity check
    trivially true regardless of whether wiring is actually correct)."""
    return (
        SetupInterpretation(
            occurred_at=_OCCURRED_AT, setup_id="displacement_with_volume_confirmation",
            detected=False, direction=SetupDirection.UNAVAILABLE, source=DirectionSource.INSUFFICIENT_DATA,
            source_fact_ids=(), reason_codes=("not_detected_or_source_fact_insufficient_data",),
            interpretation_version="SETUP_INTERPRETATION_V1", interpretation_fingerprint="fedcba9876543210",
        ),
    )


def _frame() -> ReplayFrame:
    return ReplayFrame(
        market_state=_market_state(), rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(), market_context=_market_context(),
        setup_interpretations=_setup_interpretations(),
    )


# ---- 1. bundles the five approved objects ----

def test_replay_frame_bundles_the_five_approved_objects():
    market_state = _market_state()
    rule_engine_output = _rule_engine_output()
    setup_engine_output = _setup_engine_output()
    market_context = _market_context()
    setup_interpretations = _setup_interpretations()

    frame = ReplayFrame(
        market_state=market_state, rule_engine_output=rule_engine_output,
        setup_engine_output=setup_engine_output, market_context=market_context,
        setup_interpretations=setup_interpretations,
    )

    assert frame.market_state == market_state
    assert frame.rule_engine_output == rule_engine_output
    assert frame.setup_engine_output == setup_engine_output
    assert frame.market_context == market_context
    assert frame.setup_interpretations == setup_interpretations


# ---- setup_interpretations is required, not defaulted ----

def test_replay_frame_requires_setup_interpretations():
    with pytest.raises(TypeError):
        ReplayFrame(
            market_state=_market_state(), rule_engine_output=_rule_engine_output(),
            setup_engine_output=_setup_engine_output(), market_context=_market_context(),
        )


# ---- 2 & 3. frozen, mutation raises FrozenInstanceError ----

@pytest.mark.parametrize(
    "field_name, new_value",
    [
        pytest.param("market_state", _market_state(), id="market_state"),
        pytest.param("rule_engine_output", _rule_engine_output(), id="rule_engine_output"),
        pytest.param("setup_engine_output", _setup_engine_output(), id="setup_engine_output"),
        pytest.param("market_context", _market_context(), id="market_context"),
        pytest.param("setup_interpretations", (), id="setup_interpretations"),
    ],
)
def test_replay_frame_is_frozen_mutation_raises(field_name, new_value):
    frame = _frame()
    with pytest.raises(FrozenInstanceError):
        setattr(frame, field_name, new_value)


# ---- 4. preserves the exact supplied object instances ----

def test_replay_frame_preserves_the_exact_supplied_object_instances():
    market_state = _market_state()
    rule_engine_output = _rule_engine_output()
    setup_engine_output = _setup_engine_output()
    market_context = _market_context()
    setup_interpretations = _setup_interpretations()

    frame = ReplayFrame(
        market_state=market_state, rule_engine_output=rule_engine_output,
        setup_engine_output=setup_engine_output, market_context=market_context,
        setup_interpretations=setup_interpretations,
    )

    assert frame.market_state is market_state
    assert frame.rule_engine_output is rule_engine_output
    assert frame.setup_engine_output is setup_engine_output
    assert frame.market_context is market_context
    assert frame.setup_interpretations is setup_interpretations


# ---- 5. equality is value-based and deterministic ----

def test_replay_frame_equality_is_value_based_and_deterministic():
    a = _frame()
    b = _frame()

    assert a is not b
    assert a == b
    # Repeated comparisons must be stable - no hidden mutable/random state.
    for _ in range(10):
        assert a == b

    c = ReplayFrame(
        market_state=_market_state(), rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(),
        market_context=MarketContext(
            symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, occurred_at=_OCCURRED_AT,
            session=_market_context().session, volatility=_market_context().volatility,
            quality=ContextQuality.DEGRADED,  # the one differing value
            classifier_version="REGIME_CLASSIFIER_V1", calendar_version="CME_RTH_V1",
            context_fingerprint="0123456789abcdef",
        ),
        setup_interpretations=_setup_interpretations(),
    )
    assert a != c


# ---- setup_interpretations is a genuinely distinguishing field too ----

def test_replay_frame_equality_distinguishes_on_setup_interpretations_alone():
    a = _frame()
    d = ReplayFrame(
        market_state=_market_state(), rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(), market_context=_market_context(),
        setup_interpretations=(),  # the one differing value: empty instead of one entry
    )
    assert a != d


# ---- 6. no ReplaySession class exists ----

def test_no_replay_session_class_exists_in_replay_engine_models():
    assert not hasattr(replay_engine_models, "ReplaySession")
    session_like_names = [name for name in dir(replay_engine_models) if "Session" in name]
    assert session_like_names == []
