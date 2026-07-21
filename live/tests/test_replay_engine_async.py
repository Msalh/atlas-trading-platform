"""
Phase N2, Sprint 3. Tests for atlas.replay_engine.service.replay() - the
thin async orchestration boundary: fetch (replay_market_state), segment
(segment_replay_window), compose per segment (build_replay_output_window),
yield. No test here re-verifies Sprint 2's own composition/alignment
correctness (already covered by test_replay_engine_service.py) beyond what's
needed to prove replay() wires the pieces together and preserves segment
boundaries correctly.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import RegimeClassifierDefinition, RegimeClassifierParams
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository
from atlas.replay_engine.service import build_replay_output_window, replay

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)
_RANGE_START = datetime(2026, 7, 1, tzinfo=timezone.utc)
_RANGE_END = datetime(2026, 8, 1, tzinfo=timezone.utc)

_SMALL = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=3, min_bars_required=3, compressed_percentile=25, expanded_percentile=75,
    ),
)


def _state(event_id: str, occurred_at: datetime, atr=1.0, symbol="MNQU6", timeframe=Timeframe.M5) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=event_id),
        schema_version="1.0", symbol=Symbol(symbol), timeframe=timeframe, bar_status=BarStatus.CLOSED,
        atr=atr,
    )


def _series(count: int, base: datetime, cadence_minutes: int = 5, prefix: str = "e") -> list[MarketState]:
    step = timedelta(minutes=cadence_minutes)
    return [_state(f"{prefix}{i}", base + step * i, atr=1.0 + i * 0.1) for i in range(count)]


async def _seed(repository: InMemoryMarketStateRepository, states: list[MarketState]) -> None:
    for state in states:
        await repository.ingest(state, raw_payload="{}")


async def _collect(**kwargs) -> list:
    kwargs.setdefault("symbol", Symbol("MNQU6"))
    kwargs.setdefault("timeframe", Timeframe.M5)
    kwargs.setdefault("start", _RANGE_START)
    kwargs.setdefault("end", _RANGE_END)
    kwargs.setdefault("classifier", _SMALL)
    return [frame async for frame in replay(**kwargs)]


@pytest.fixture
def repo():
    return InMemoryMarketStateRepository()


class _RecordingRepository:
    """Delegates to a real InMemoryMarketStateRepository, recording every
    get_range call's arguments - replay() only ever calls get_range
    (via replay_market_state), so nothing else needs recording."""

    def __init__(self, inner: InMemoryMarketStateRepository):
        self._inner = inner
        self.get_range_calls: list[tuple] = []

    async def get_range(self, symbol, timeframe, start, end, limit=10000):
        self.get_range_calls.append((symbol, timeframe, start, end, limit))
        return await self._inner.get_range(symbol, timeframe, start, end, limit)


class _BoomError(Exception):
    pass


class _FailingRepository:
    async def get_range(self, symbol, timeframe, start, end, limit=10000):
        raise _BoomError("repository unavailable")


# ---- 1. empty repository yields zero frames ----

@pytest.mark.asyncio
async def test_empty_repository_yields_zero_frames(repo):
    frames = await _collect(repository=repo)
    assert frames == []


# ---- 2. single-bar replay ----

@pytest.mark.asyncio
async def test_single_bar_replay(repo):
    states = _series(1, _BASE)
    await _seed(repo, states)
    frames = await _collect(repository=repo)
    assert len(frames) == 1
    assert frames[0].market_state == states[0]


# ---- 3. one contiguous multi-bar segment ----

@pytest.mark.asyncio
async def test_one_contiguous_multi_bar_segment(repo):
    states = _series(6, _BASE)
    await _seed(repo, states)
    frames = await _collect(repository=repo)
    assert len(frames) == 6
    assert [f.market_state for f in frames] == states


# ---- 4. multiple segments separated by a gap ----

@pytest.mark.asyncio
async def test_multiple_segments_separated_by_a_gap(repo):
    segment_a = _series(3, _BASE, prefix="a")
    segment_b = _series(4, _BASE + timedelta(days=3), prefix="b")
    await _seed(repo, segment_a + segment_b)

    frames = await _collect(repository=repo)

    assert len(frames) == 7
    assert [f.market_state for f in frames] == segment_a + segment_b


# ---- 5. segment isolation ----

@pytest.mark.asyncio
async def test_segment_isolation_first_frame_of_new_segment_does_not_inherit_prior_history(repo):
    segment_a = _series(5, _BASE, prefix="a")
    segment_b = _series(5, _BASE + timedelta(days=5), prefix="b")
    await _seed(repo, segment_a + segment_b)

    frames = await _collect(repository=repo)

    # If segment B genuinely started fresh (no memory of segment A), its
    # frames must be byte-identical to composing segment B alone.
    isolated_b = build_replay_output_window(segment_b, classifier=_SMALL)
    assert frames[len(segment_a):] == isolated_b
    assert frames[len(segment_a)] == isolated_b[0]


# ---- 6. strict chronological ordering ----

@pytest.mark.asyncio
async def test_strict_chronological_ordering_across_segments(repo):
    segment_a = _series(2, _BASE, prefix="a")
    segment_b = _series(2, _BASE + timedelta(days=2), prefix="b")
    segment_c = _series(2, _BASE + timedelta(days=4), prefix="c")
    await _seed(repo, segment_a + segment_b + segment_c)

    frames = await _collect(repository=repo)
    occurred_ats = [f.market_state.envelope.occurred_at for f in frames]
    assert occurred_ats == sorted(occurred_ats)


# ---- 7. exact alignment of all four ReplayFrame components ----

@pytest.mark.asyncio
async def test_exact_alignment_of_all_four_replay_frame_components(repo):
    states = _series(5, _BASE)
    await _seed(repo, states)

    frames = await _collect(repository=repo)

    for frame in frames:
        expected_at = frame.market_state.envelope.occurred_at
        assert frame.rule_engine_output.occurred_at == expected_at.isoformat()
        assert frame.setup_engine_output.occurred_at == expected_at.isoformat()
        assert frame.market_context.occurred_at == expected_at


# ---- 8. repository arguments forwarded correctly ----

@pytest.mark.asyncio
async def test_repository_arguments_are_forwarded_correctly(repo):
    recorder = _RecordingRepository(repo)
    symbol = Symbol("MNQU6")
    timeframe = Timeframe.M5
    start = datetime(2026, 7, 5, tzinfo=timezone.utc)
    end = datetime(2026, 7, 10, tzinfo=timezone.utc)

    await _collect(repository=recorder, symbol=symbol, timeframe=timeframe, start=start, end=end, limit=42)

    assert recorder.get_range_calls == [(symbol, timeframe, start, end, 42)]


# ---- 9. repository exceptions propagate unchanged ----

@pytest.mark.asyncio
async def test_repository_exception_propagates_unchanged():
    with pytest.raises(_BoomError, match="repository unavailable"):
        await _collect(repository=_FailingRepository())


# ---- 10. composition exceptions propagate unchanged ----

@pytest.mark.asyncio
async def test_composition_exception_propagates_unchanged(repo):
    # An unset atr among enough bars for classify_volatility_regime to
    # actually compare it (min_bars_required=3) raises TypeError inside
    # composition - proving replay() adds no try/except around it.
    states = _series(3, _BASE)
    poisoned = replace(states[1], atr=None)
    states = [states[0], poisoned, states[2]]
    await _seed(repo, states)

    with pytest.raises(TypeError):
        await _collect(repository=repo)


# ---- 11. determinism across repeated complete replay runs ----

@pytest.mark.asyncio
async def test_determinism_across_repeated_complete_replay_runs(repo):
    segment_a = _series(3, _BASE, prefix="a")
    segment_b = _series(3, _BASE + timedelta(days=3), prefix="b")
    await _seed(repo, segment_a + segment_b)

    first = await _collect(repository=repo)
    second = await _collect(repository=repo)

    assert first == second


# ---- 12. early consumer termination avoids processing a later segment ----

@pytest.mark.asyncio
async def test_early_termination_never_reaches_a_later_poisoned_segment(repo):
    segment_a = _series(3, _BASE, prefix="a")
    segment_b = _series(3, _BASE + timedelta(days=3), prefix="b")
    poisoned_b = [segment_b[0], replace(segment_b[1], atr=None), segment_b[2]]
    await _seed(repo, segment_a + poisoned_b)

    collected = []
    async for frame in replay(
        Symbol("MNQU6"), Timeframe.M5, _RANGE_START, _RANGE_END, repo, classifier=_SMALL,
    ):
        collected.append(frame)
        if frame.market_state.envelope.event_id == "a2":  # last bar of segment A
            break

    assert [f.market_state for f in collected] == segment_a

    # Confirm segment B genuinely would have raised if it had been reached -
    # proving the early break above is why it never surfaced, not luck.
    with pytest.raises(TypeError):
        build_replay_output_window(poisoned_b, classifier=_SMALL)
