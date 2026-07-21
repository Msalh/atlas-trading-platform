"""
Phase N2, Sprint 1. Tests for atlas.replay_engine.segmentation -
segment_replay_window(), a thin wrapper around the already-tested
atlas.profiling.service.segment_by_gap. These tests exist to prove the
wrapper adds nothing and loses nothing (see
test_wrapper_result_matches_segment_by_gap_exactly), not to re-prove
segment_by_gap's own gap-detection logic a second time - that coverage
already exists in test_profiling.py::TestSegmentByGap.
"""
from datetime import datetime, timedelta, timezone

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.profiling.service import segment_by_gap
from atlas.replay_engine.segmentation import segment_replay_window

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)


def _state(event_id: str, occurred_at: datetime, symbol: str = "MNQU6", timeframe: Timeframe = Timeframe.M5) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=event_id),
        schema_version="1.0", symbol=Symbol(symbol), timeframe=timeframe, bar_status=BarStatus.CLOSED,
    )


def _series(
    count: int, base: datetime = _BASE, cadence_minutes: int = 5, timeframe: Timeframe = Timeframe.M5,
) -> list[MarketState]:
    step = timedelta(minutes=cadence_minutes)
    return [_state(f"e{i}", base + step * i, timeframe=timeframe) for i in range(count)]


# ---- 1. empty input returns no segments ----

def test_empty_input_returns_no_segments():
    assert segment_replay_window([]) == []


# ---- 2. one contiguous sequence returns one segment ----

def test_one_contiguous_sequence_returns_one_segment():
    states = _series(5)
    assert segment_replay_window(states) == [states]


# ---- 3. one injected gap returns two segments ----

def test_one_injected_gap_returns_two_segments():
    states = _series(3)
    states.append(_state("e3", states[-1].envelope.occurred_at + timedelta(days=3)))  # a real gap
    segments = segment_replay_window(states)
    assert len(segments) == 2
    assert segments[0] == states[:3]
    assert segments[1] == states[3:]


# ---- 4. multiple gaps return correctly ordered segments ----

def test_multiple_gaps_return_correctly_ordered_segments():
    a = _series(2, base=_BASE)
    b = _series(2, base=_BASE + timedelta(days=1))
    c = _series(2, base=_BASE + timedelta(days=2))
    segments = segment_replay_window(a + b + c)
    assert [len(s) for s in segments] == [2, 2, 2]
    assert segments == [a, b, c]


# ---- 5. input order and object identity are preserved ----

def test_input_order_and_object_identity_are_preserved():
    states = _series(6)
    segments = segment_replay_window(states)
    flattened = [state for segment in segments for state in segment]
    assert flattened == states
    assert all(a is b for a, b in zip(flattened, states))


# ---- 6. input collection is not mutated ----

def test_input_collection_is_not_mutated():
    states = _series(4)
    states_copy = list(states)
    segment_replay_window(states)
    assert states == states_copy
    assert all(a is b for a, b in zip(states, states_copy))


# ---- 7. wrapper's result matches segment_by_gap exactly ----

def test_wrapper_result_matches_segment_by_gap_exactly():
    states = _series(3) + _series(2, base=_BASE + timedelta(days=5))
    assert segment_replay_window(states) == segment_by_gap(states)
    # Not just equal in value - the same object instances flow through untouched.
    wrapper_flat = [s for segment in segment_replay_window(states) for s in segment]
    direct_flat = [s for segment in segment_by_gap(states) for s in segment]
    assert all(a is b for a, b in zip(wrapper_flat, direct_flat))


# ---- 8. weekend/holiday-sized gaps are segment boundaries, not exceptions ----

def test_weekend_sized_gap_is_a_segment_boundary_not_an_exception():
    states = _series(2, base=_BASE)
    states += _series(2, base=_BASE + timedelta(days=3))  # a weekend-sized jump
    segments = segment_replay_window(states)
    assert len(segments) == 2
    assert [len(s) for s in segments] == [2, 2]


def test_holiday_sized_gap_is_a_segment_boundary_not_an_exception():
    states = _series(2, base=_BASE)
    states += _series(2, base=_BASE + timedelta(days=14))  # a holiday/multi-day-closure-sized jump
    segments = segment_replay_window(states)
    assert len(segments) == 2
    assert [len(s) for s in segments] == [2, 2]


# ---- 9. different valid timeframes use their own cadence correctly ----

def test_m1_timeframe_uses_its_own_one_minute_cadence():
    states = _series(4, cadence_minutes=1, timeframe=Timeframe.M1)
    assert segment_replay_window(states) == [states]


def test_m15_timeframe_uses_its_own_fifteen_minute_cadence():
    states = _series(4, cadence_minutes=15, timeframe=Timeframe.M15)
    assert segment_replay_window(states) == [states]


def test_h1_timeframe_uses_its_own_sixty_minute_cadence():
    states = _series(4, cadence_minutes=60, timeframe=Timeframe.H1)
    assert segment_replay_window(states) == [states]


def test_a_gap_relative_to_one_timeframes_own_cadence_still_splits_correctly():
    """A 5-minute jump inside an M1 (1-minute cadence) series is a real gap
    for M1's own cadence, even though it would be exactly one bar's worth
    of interval for M5 - proving cadence is read from the series' own
    timeframe, not a fixed constant."""
    states = _series(2, cadence_minutes=1, timeframe=Timeframe.M1)
    states.append(_state("e2", states[-1].envelope.occurred_at + timedelta(minutes=5), timeframe=Timeframe.M1))
    segments = segment_replay_window(states)
    assert len(segments) == 2
    assert [len(s) for s in segments] == [2, 1]
