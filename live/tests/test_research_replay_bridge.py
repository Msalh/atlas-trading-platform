"""
Phase N4 Sprint 3 (Replay Bridge). Integration tests against real
build_replay_output_window()/replay() output - no mocks - proving
replay_bridge's two functions are genuine, unmodified pass-throughs, plus
the dependency audit proving this is the only Research Engine module
importing atlas.replay_engine. Fixture style mirrors
test_replay_engine_async.py's own (real MarketState series,
InMemoryMarketStateRepository) - deliberately, per the roadmap's own test
strategy for this sprint ("mirroring Setup Interpretation's own real-builder
discipline").
"""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import RegimeClassifierDefinition, RegimeClassifierParams
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository
from atlas.replay_engine.service import build_replay_output_window, replay
from atlas.research.replay_bridge import build_replay_frames_for_window, fetch_replay_frames

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


@pytest.fixture
def repo():
    return InMemoryMarketStateRepository()


class _BoomError(Exception):
    pass


class _FailingRepository:
    async def get_range(self, symbol, timeframe, start, end, limit=10000):
        raise _BoomError("repository unavailable")


# ---- build_replay_frames_for_window(): sync pass-through ----

def test_build_replay_frames_for_window_matches_build_replay_output_window_exactly():
    states = _series(6, _BASE)
    expected = build_replay_output_window(states, classifier=_SMALL)
    actual = build_replay_frames_for_window(states, classifier=_SMALL)
    assert actual == expected


def test_build_replay_frames_for_window_empty_input_yields_empty_output():
    assert build_replay_frames_for_window([], classifier=_SMALL) == []


def test_build_replay_frames_for_window_propagates_composition_exceptions_unchanged():
    from dataclasses import replace
    states = _series(3, _BASE)
    poisoned = [states[0], replace(states[1], atr=None), states[2]]
    with pytest.raises(TypeError):
        build_replay_frames_for_window(poisoned, classifier=_SMALL)


# ---- fetch_replay_frames(): async pass-through ----

@pytest.mark.asyncio
async def test_fetch_replay_frames_matches_replay_exactly(repo):
    states = _series(6, _BASE)
    await _seed(repo, states)

    expected = [
        frame async for frame in replay(
            Symbol("MNQU6"), Timeframe.M5, _RANGE_START, _RANGE_END, repo, classifier=_SMALL,
        )
    ]
    actual = [
        frame async for frame in fetch_replay_frames(
            Symbol("MNQU6"), Timeframe.M5, _RANGE_START, _RANGE_END, repo, classifier=_SMALL,
        )
    ]
    assert actual == expected
    assert len(actual) == 6


@pytest.mark.asyncio
async def test_fetch_replay_frames_empty_repository_yields_zero_frames(repo):
    frames = [
        frame async for frame in fetch_replay_frames(
            Symbol("MNQU6"), Timeframe.M5, _RANGE_START, _RANGE_END, repo, classifier=_SMALL,
        )
    ]
    assert frames == []


@pytest.mark.asyncio
async def test_fetch_replay_frames_propagates_repository_exceptions_unchanged():
    with pytest.raises(_BoomError, match="repository unavailable"):
        async for _ in fetch_replay_frames(
            Symbol("MNQU6"), Timeframe.M5, _RANGE_START, _RANGE_END, _FailingRepository(), classifier=_SMALL,
        ):
            pass


@pytest.mark.asyncio
async def test_fetch_replay_frames_preserves_multi_segment_chronological_order(repo):
    segment_a = _series(3, _BASE, prefix="a")
    segment_b = _series(3, _BASE + timedelta(days=3), prefix="b")
    await _seed(repo, segment_a + segment_b)

    frames = [
        frame async for frame in fetch_replay_frames(
            Symbol("MNQU6"), Timeframe.M5, _RANGE_START, _RANGE_END, repo, classifier=_SMALL,
        )
    ]
    assert [f.market_state for f in frames] == segment_a + segment_b


# ---- dependency audit: this is the ONLY Research Engine module importing atlas.replay_engine ----

_RESEARCH_DIR = Path(__file__).resolve().parent.parent / "atlas" / "research"
_REPLAY_BRIDGE_FILE = _RESEARCH_DIR / "replay_bridge.py"

_REPLAY_BRIDGE_ALLOWED = frozenset({
    "atlas.core.primitives",
    "atlas.market_context.definitions",
    "atlas.market_engine.models",
    "atlas.market_engine.ports",
    "atlas.replay_engine.models",
    "atlas.replay_engine.service",
})


def _imported_module_roots(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def _atlas_imports(file_path: Path) -> set[str]:
    return {name for name in _imported_module_roots(file_path) if name.startswith("atlas.")}


def test_replay_bridge_imports_match_its_exact_actual_allowlist():
    disallowed = _atlas_imports(_REPLAY_BRIDGE_FILE) - _REPLAY_BRIDGE_ALLOWED
    assert not disallowed, f"replay_bridge.py imports beyond its allowlist: {disallowed}"


def test_replay_bridge_is_the_only_research_engine_module_importing_replay_engine():
    for py_file in _RESEARCH_DIR.rglob("*.py"):
        if py_file == _REPLAY_BRIDGE_FILE:
            continue
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.replay_engine")}
        assert not offending, f"{py_file} imports atlas.replay_engine unexpectedly: {offending}"
