"""
UI v2, amendments 1 and 3. Focused tests for atlas.live_view.episode_projector
against a real InMemoryMarketStateRepository - proves the four
LeftBoundaryReason cases, the progressive-widening and hard-maximum-
truncation paths, and the right-boundary (is_active / LiveTerminationReason)
cases, using the SAME synthetic-MarketState-fixture style established
throughout this project (e.g. tests/test_setup_profiling.py).

displacement_with_volume_confirmation is used as the primary probe setup
throughout: detected = (high-low)/atr > 1.5 AND volume_ratio > 1.5 (Rule
Engine's own thresholds) - MarketState.displacement/volume_spike
themselves are unused wire placeholders (always False from Pine, Sprint 5
design), a real mistake made and caught while first exercising this
module for real, not predicted by the design - see the "active" helper
below for the corrected fixture shape.
"""
from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.live_view.episode_projector import build_live_window_result
from atlas.live_view.models import LeftBoundaryReason, LiveTerminationReason
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository

TICK = 0.25
BASE = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
SYMBOL = Symbol("MNQ1!")
TIMEFRAME = Timeframe.M5
DISPLACEMENT_SETUP = "displacement_with_volume_confirmation"
STREAK_SETUP = "sustained_displacement_streak"


def _market_state(active: bool, occurred_at: datetime, **overrides) -> MarketState:
    """`active=True` sets the REAL Rule Engine inputs displacement/
    volume_spike are computed from - (high-low)/atr > 1.5 and
    volume_ratio > 1.5 - never the unused MarketState.displacement/
    volume_spike wire fields themselves."""
    if active:
        high, low, volume_ratio = Price(20200.00, TICK), Price(20100.00, TICK), 2.0
    else:
        high, low, volume_ratio = Price(20128.50, TICK), Price(20118.00, TICK), 1.0
    base = dict(
        envelope=Event(
            event_type="bar_closed", source="tradingview", occurred_at=occurred_at,
            received_at=occurred_at, event_id=f"e-{occurred_at.isoformat()}",
        ),
        schema_version="1.0", symbol=SYMBOL, timeframe=TIMEFRAME, bar_status=BarStatus.CLOSED,
        open=Price(20120.00, TICK), high=high, low=low, close=Price(20125.75, TICK),
        volume=4210, session_name=Session.RTH, is_rth=True, trading_date=occurred_at.date(),
        rth_open=Price(19980.00, TICK),
        previous_day_high=Price(20180.00, TICK), previous_day_low=Price(19950.00, TICK),
        overnight_high=Price(20300.00, TICK), overnight_low=Price(19900.00, TICK),
        vwap=20100.0, distance_from_vwap_points=25.75, atr=42.5, volume_ratio=volume_ratio,
        nearest_liquidity_level=Price(20180.00, TICK), nearest_liquidity_type="previous_day_high",
        distance_to_liquidity_ticks=217,
        trend_1m="up", trend_5m="up", trend_15m="flat", trend_1h="down",
        liquidity_sweep=False, reclaim=False, rejection=False, displacement=False, volume_spike=False,
    )
    base.update(overrides)
    return MarketState(**base)


async def _seed(repo, pattern: list[bool], start: datetime = BASE, cadence_minutes: int = 5):
    """`pattern[i]` is whether bar i is "active" - ingests len(pattern)
    contiguous bars starting at `start`."""
    for i, active in enumerate(pattern):
        await repo.ingest(_market_state(active, start + timedelta(minutes=cadence_minutes * i)), "{}")


@pytest.fixture
def repo():
    return InMemoryMarketStateRepository()


class TestLeftBoundaryObservedActivation:
    @pytest.mark.asyncio
    async def test_a_false_bar_immediately_before_activation_resolves_without_widening(self, repo):
        await _seed(repo, [False] * 5 + [True] * 5)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert ep.left_boundary_reason == LeftBoundaryReason.OBSERVED_ACTIVATION
        assert ep.activation_timestamp_observed is not None
        assert not ep.is_window_truncated
        assert result.actually_used_window == 10  # no widening needed


class TestLeftBoundaryInsufficientData:
    @pytest.mark.asyncio
    async def test_a_setup_needing_history_resolves_insufficient_data_at_the_windows_own_start(self, repo):
        # sustained_displacement_streak needs 2 bars of history - the very
        # first bar of ANY window has none, so it always resolves
        # insufficient_data there, never left-censored/ambiguous.
        await _seed(repo, [True] * 10)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        ep = result.setups[STREAK_SETUP].current_episode
        assert ep is not None
        assert ep.left_boundary_reason == LeftBoundaryReason.INSUFFICIENT_DATA
        assert ep.activation_timestamp_observed is not None
        assert not ep.is_window_truncated


class TestLeftBoundarySegmentStart:
    @pytest.mark.asyncio
    async def test_a_genuine_gap_before_activation_resolves_after_widening(self, repo):
        await _seed(repo, [False] * 5, start=BASE)
        gap_start = BASE + timedelta(days=3)
        await _seed(repo, [True] * 10, start=gap_start)

        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=8, hard_max_window=40)
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert ep.left_boundary_reason == LeftBoundaryReason.SEGMENT_START
        assert ep.activation_timestamp_observed is None
        assert not ep.is_window_truncated
        assert ep.duration_bars_observed == 10
        assert len(result.segments) == 2

    @pytest.mark.asyncio
    async def test_wide_enough_initial_window_resolves_without_any_widening(self, repo):
        await _seed(repo, [False] * 5, start=BASE)
        gap_start = BASE + timedelta(days=3)
        await _seed(repo, [True] * 10, start=gap_start)

        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=15, hard_max_window=40)
        assert result.actually_used_window == 15
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert ep.left_boundary_reason == LeftBoundaryReason.SEGMENT_START


class TestLeftBoundaryQueryWindowStart:
    @pytest.mark.asyncio
    async def test_active_for_the_entire_available_history_truncates_at_hard_max(self, repo):
        await _seed(repo, [True] * 60)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert ep.left_boundary_reason == LeftBoundaryReason.QUERY_WINDOW_START
        assert ep.is_window_truncated
        assert ep.activation_timestamp_observed is None
        assert result.actually_used_window == 40
        assert any("displacement_with_volume_confirmation" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_duration_bars_observed_is_a_lower_bound_when_truncated(self, repo):
        await _seed(repo, [True] * 60)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert ep.duration_bars_observed == 40  # exactly the fetched window, a known lower bound


class TestRightBoundaryStillActive:
    @pytest.mark.asyncio
    async def test_active_through_the_latest_bar_has_no_real_ending(self, repo):
        await _seed(repo, [False] * 5 + [True] * 3)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert ep.is_active
        assert ep.end_timestamp_observed is None
        assert ep.termination_reason is None
        assert not ep.right_boundary_observed
        assert ep.last_observed_timestamp == result.data_as_of

    @pytest.mark.asyncio
    async def test_activation_bar_itself_is_not_a_continuation(self, repo):
        await _seed(repo, [False] * 5 + [True] * 1)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert not ep.is_continuation

    @pytest.mark.asyncio
    async def test_a_later_active_bar_is_a_continuation(self, repo):
        await _seed(repo, [False] * 5 + [True] * 3)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        ep = result.setups[DISPLACEMENT_SETUP].current_episode
        assert ep.is_continuation


class TestRightBoundaryClosed:
    @pytest.mark.asyncio
    async def test_recent_episodes_are_always_closed_with_a_real_termination_reason(self, repo):
        # active, then false, then active again - the FIRST run is closed
        # (became_false); only the second/latest run is the open one.
        await _seed(repo, [False] * 3 + [True] * 3 + [False] * 3 + [True] * 3)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=20, hard_max_window=40)
        snapshot = result.setups[DISPLACEMENT_SETUP]
        assert snapshot.current_episode is not None
        assert snapshot.current_episode.is_active
        assert len(snapshot.recent_episodes) == 1
        closed = snapshot.recent_episodes[0]
        assert not closed.is_active
        assert closed.termination_reason == LiveTerminationReason.BECAME_FALSE
        assert closed.end_timestamp_observed is not None
        assert closed.right_boundary_observed

    @pytest.mark.asyncio
    async def test_no_active_episode_when_setup_is_currently_false(self, repo):
        await _seed(repo, [True] * 5 + [False] * 3)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        snapshot = result.setups[DISPLACEMENT_SETUP]
        assert snapshot.current_episode is None
        assert len(snapshot.recent_episodes) == 1
        assert not snapshot.recent_episodes[0].is_active


class TestNoMarketData:
    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_has_been_ingested(self, repo):
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        assert result is None


class TestComputabilitySummary:
    @pytest.mark.asyncio
    async def test_computability_counts_are_consistent_with_active_bars(self, repo):
        await _seed(repo, [False] * 5 + [True] * 5)
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        summary = result.setups[DISPLACEMENT_SETUP].computability
        assert summary.computable_bars == 10
        assert summary.non_computable_bars == 0
        assert summary.detected_true_bars == 5
        assert summary.detected_false_bars == 5


class TestSegmentsAndActivationEvents:
    @pytest.mark.asyncio
    async def test_segments_reflect_real_gaps_within_the_window(self, repo):
        await _seed(repo, [False] * 5, start=BASE)
        await _seed(repo, [False] * 5, start=BASE + timedelta(days=1))
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        assert len(result.segments) == 2
        assert result.segments[0].end_timestamp is not None  # closed, a real gap follows
        assert result.segments[-1].end_timestamp is None  # the window's own last segment is still open

    @pytest.mark.asyncio
    async def test_simultaneous_activation_is_reported_as_one_tied_event(self, repo):
        # displacement_with_volume_confirmation and vwap_extension_with_volume_confirmation
        # both key off volume_spike - drive both true on the same bar.
        pattern_states = [False] * 3
        await _seed(repo, pattern_states)
        active_at = BASE + timedelta(minutes=5 * 3)
        # distance_from_vwap_points/atr far past the extended_above threshold
        await repo.ingest(_market_state(True, active_at, distance_from_vwap_points=300.0), "{}")
        result = await build_live_window_result(repo, SYMBOL, TIMEFRAME, window=10, hard_max_window=40)
        matching = [e for e in result.activation_events if e.timestamp == active_at.isoformat()]
        assert len(matching) == 1
        assert DISPLACEMENT_SETUP in matching[0].activated_setups
        assert "vwap_extension_with_volume_confirmation" in matching[0].activated_setups
        assert list(matching[0].activated_setups) == sorted(matching[0].activated_setups)
