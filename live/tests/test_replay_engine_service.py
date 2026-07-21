"""
Phase N2, Sprint 2. Tests for atlas.replay_engine.service.build_replay_output_window()
- the pure composition core that zips Rule Engine + Setup Engine + Market
Context output into ReplayFrame, one per input MarketState.

No test here re-verifies Rule Engine's, Setup Engine's, or Market Context's
own already-certified internals (fact values, setup detection, session/regime
classification) - only that build_replay_output_window composes and aligns
their existing outputs correctly. Fixtures deliberately omit most optional
MarketState fields (open/high/low/close/volume/vwap/etc.) - every Rule Engine
fact already degrades to InsufficientData when its inputs are missing rather
than raising, so a bare fixture is sufficient to exercise composition/
alignment without asserting anything about fact content.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Session, Symbol, Timeframe
from atlas.market_context.definitions import (
    CME_RTH_V1,
    RegimeClassifierDefinition,
    RegimeClassifierParams,
)
from atlas.market_context.models import ContextQuality, SessionPhase, VolatilityRegime
from atlas.market_context.service import build_market_context
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.models import ReplayFrame
from atlas.replay_engine.service import (
    ReplayLengthMismatchError,
    ReplayOccurredAtMismatchError,
    _assert_aligned,
    build_replay_output_window,
)
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.service import build_setup_engine_output_window

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)
_CENTRAL = ZoneInfo("America/Chicago")

_SMALL = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=10, min_bars_required=10, compressed_percentile=25, expanded_percentile=75,
    ),
)


def _occurred_at_ct(hour: int, minute: int, date: tuple = (2026, 7, 21)) -> datetime:
    year, month, day = date
    return datetime(year, month, day, hour, minute, tzinfo=_CENTRAL).astimezone(timezone.utc)


def _state(
    index: int, occurred_at: datetime, atr: float = 1.0,
    symbol: str = "MNQU6", timeframe: Timeframe = Timeframe.M5,
    session_name=None, is_rth=None,
) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=f"e{index}"),
        schema_version="1.0", symbol=Symbol(symbol), timeframe=timeframe, bar_status=BarStatus.CLOSED,
        atr=atr, session_name=session_name, is_rth=is_rth,
    )


def _window(n: int, base: datetime = _BASE, cadence_minutes: int = 5, **shared) -> list[MarketState]:
    step = timedelta(minutes=cadence_minutes)
    return [_state(i, base + step * i, atr=1.0 + i * 0.1, **shared) for i in range(n)]


def _build_market_contexts(window: list[MarketState]) -> list:
    """Mirrors service.py's own per-position construction, for tests that
    need a valid market_contexts list to mutate/slice directly against
    _assert_aligned."""
    return [
        build_market_context(
            symbol=state.symbol, timeframe=state.timeframe, occurred_at=state.envelope.occurred_at,
            window=window[: i + 1], upstream_session_name=None, upstream_is_rth=None,
        )
        for i, state in enumerate(window)
    ]


# ---- perfect alignment ----

def test_perfect_alignment_for_a_multi_bar_window():
    window = _window(6)
    frames = build_replay_output_window(window)

    assert len(frames) == 6
    for i, frame in enumerate(frames):
        assert frame.market_state is window[i]
        assert frame.rule_engine_output.occurred_at == window[i].envelope.occurred_at.isoformat()
        assert frame.setup_engine_output.occurred_at == window[i].envelope.occurred_at.isoformat()
        assert frame.market_context.occurred_at == window[i].envelope.occurred_at


# ---- single-bar input ----

def test_single_bar_input_produces_exactly_one_frame():
    window = _window(1)
    frames = build_replay_output_window(window)

    assert len(frames) == 1
    assert frames[0].market_state is window[0]
    assert frames[0].market_context.volatility.regime == VolatilityRegime.INSUFFICIENT_HISTORY


def test_empty_input_produces_an_empty_list():
    assert build_replay_output_window([]) == []


# ---- multiple-bar input ----

def test_multiple_bar_input_produces_one_frame_per_bar_in_order():
    window = _window(15)
    frames = build_replay_output_window(window)

    assert len(frames) == 15
    assert [frame.market_state for frame in frames] == window


def test_real_end_to_end_composition_with_a_small_classifier_produces_a_real_classification():
    """Enough bars to clear a deliberately small min_bars_required, at a
    real CME_RTH_V1 mid-session CT time with upstream is_rth=True - proves
    build_replay_output_window drives a genuine TRUSTED/real-regime result
    through the real composed functions, not just INSUFFICIENT_HISTORY
    warm-up on every position."""
    occurred_at = _occurred_at_ct(12, 0)  # MID_SESSION under CME_RTH_V1
    window = _window(10, base=occurred_at - timedelta(minutes=45), session_name=Session.RTH, is_rth=True)

    frames = build_replay_output_window(window, calendar=CME_RTH_V1, classifier=_SMALL)

    last = frames[-1]
    assert last.market_context.session.phase == SessionPhase.MID_SESSION
    assert last.market_context.volatility.regime != VolatilityRegime.INSUFFICIENT_HISTORY
    assert last.market_context.quality == ContextQuality.TRUSTED

    first = frames[0]
    assert first.market_context.quality == ContextQuality.UNKNOWN  # not enough warm-up yet at position 0


# ---- length mismatch ----

def test_assert_aligned_raises_on_length_mismatch():
    window = _window(3)
    rule_outputs = build_rule_engine_output_window(window)
    setup_outputs = build_setup_engine_output_window(rule_outputs)
    market_contexts = _build_market_contexts(window)

    with pytest.raises(ReplayLengthMismatchError):
        _assert_aligned(window, rule_outputs, setup_outputs, market_contexts[:-1])  # one short


def test_assert_aligned_reports_every_mismatched_list_by_name():
    window = _window(3)
    rule_outputs = build_rule_engine_output_window(window)
    setup_outputs = build_setup_engine_output_window(rule_outputs)
    market_contexts = _build_market_contexts(window)

    with pytest.raises(ReplayLengthMismatchError, match="setup_engine_outputs"):
        _assert_aligned(window, rule_outputs, setup_outputs[:-1], market_contexts)


# ---- timestamp mismatch ----

def test_assert_aligned_raises_on_rule_engine_output_occurred_at_mismatch():
    window = _window(3)
    rule_outputs = build_rule_engine_output_window(window)
    setup_outputs = build_setup_engine_output_window(rule_outputs)
    market_contexts = _build_market_contexts(window)

    tampered = replace(rule_outputs[1], occurred_at="2099-01-01T00:00:00+00:00")
    corrupted = rule_outputs[:1] + [tampered] + rule_outputs[2:]

    with pytest.raises(ReplayOccurredAtMismatchError, match="rule_engine_output"):
        _assert_aligned(window, corrupted, setup_outputs, market_contexts)


def test_assert_aligned_raises_on_setup_engine_output_occurred_at_mismatch():
    window = _window(3)
    rule_outputs = build_rule_engine_output_window(window)
    setup_outputs = build_setup_engine_output_window(rule_outputs)
    market_contexts = _build_market_contexts(window)

    tampered = replace(setup_outputs[1], occurred_at="2099-01-01T00:00:00+00:00")
    corrupted = setup_outputs[:1] + [tampered] + setup_outputs[2:]

    with pytest.raises(ReplayOccurredAtMismatchError, match="setup_engine_output"):
        _assert_aligned(window, rule_outputs, corrupted, market_contexts)


def test_assert_aligned_raises_on_market_context_occurred_at_mismatch():
    window = _window(3)
    rule_outputs = build_rule_engine_output_window(window)
    setup_outputs = build_setup_engine_output_window(rule_outputs)
    market_contexts = _build_market_contexts(window)

    tampered = replace(market_contexts[1], occurred_at=datetime(2099, 1, 1, tzinfo=timezone.utc))
    corrupted = market_contexts[:1] + [tampered] + market_contexts[2:]

    with pytest.raises(ReplayOccurredAtMismatchError, match="market_context"):
        _assert_aligned(window, rule_outputs, setup_outputs, corrupted)


def test_assert_aligned_passes_for_genuinely_aligned_input():
    """The construction path build_replay_output_window actually uses never
    triggers _assert_aligned's own errors - this proves the "happy path"
    input it always produces really does pass the same check directly."""
    window = _window(4)
    rule_outputs = build_rule_engine_output_window(window)
    setup_outputs = build_setup_engine_output_window(rule_outputs)
    market_contexts = _build_market_contexts(window)

    _assert_aligned(window, rule_outputs, setup_outputs, market_contexts)  # must not raise


# ---- determinism ----

def test_build_replay_output_window_is_deterministic_across_repeated_calls():
    window = _window(12)
    results = [build_replay_output_window(window) for _ in range(100)]
    assert all(result == results[0] for result in results)


def test_build_replay_output_window_does_not_mutate_its_input():
    window = _window(8)
    window_copy = list(window)
    build_replay_output_window(window)
    assert window == window_copy
    assert all(a is b for a, b in zip(window, window_copy))


# ---- ReplayFrame ordering ----

def test_replay_frames_preserve_ascending_chronological_order():
    window = _window(9)
    frames = build_replay_output_window(window)
    occurred_ats = [frame.market_state.envelope.occurred_at for frame in frames]
    assert occurred_ats == sorted(occurred_ats)
    assert occurred_ats == [state.envelope.occurred_at for state in window]


# ---- identity preservation ----

def test_frame_market_state_is_the_exact_input_object_not_a_copy():
    window = _window(5)
    frames = build_replay_output_window(window)
    assert all(frame.market_state is state for frame, state in zip(frames, window))


def test_every_frame_is_a_replay_frame_instance():
    window = _window(3)
    frames = build_replay_output_window(window)
    assert all(isinstance(frame, ReplayFrame) for frame in frames)
