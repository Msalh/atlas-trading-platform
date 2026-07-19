from datetime import datetime, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository
from atlas.market_engine.service import (
    find_gaps,
    get_latest_market_state,
    get_market_state_export,
    get_market_state_history,
    get_market_state_integrity_report,
    market_state_to_dict,
    replay_market_state,
)


def _state(event_id="e1", occurred_at="2026-07-18T13:35:00", **overrides):
    fields = dict(
        envelope=Event(
            event_type="bar_closed",
            source="tradingview",
            occurred_at=datetime.fromisoformat(occurred_at).replace(tzinfo=timezone.utc),
            event_id=event_id,
        ),
        schema_version="1.0",
        symbol=Symbol("MNQU6"),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
    )
    fields.update(overrides)
    return MarketState(**fields)


@pytest.fixture
def repo():
    return InMemoryMarketStateRepository()


class TestMarketStateToDict:
    def test_minimal_state_produces_explicit_nulls_not_omitted_keys(self):
        d = market_state_to_dict(_state())
        assert d["close"] is None
        assert d["vwap"] is None
        assert d["trend_1h"] is None
        assert "close" in d  # present with value None, not absent

    def test_populated_fields_convert_correctly(self):
        state = _state(
            close=Price(20125.75, 0.25),
            vwap=Price(20118.50, 0.25),
            volume=4210,
            session_name=Session.NY,
            is_rth=True,
            liquidity_sweep=False,
            reclaim=True,
        )
        d = market_state_to_dict(state)
        assert d["close"] == 20125.75
        assert d["vwap"] == 20118.50
        assert d["volume"] == 4210
        assert d["session_name"] == "NY"
        assert d["is_rth"] is True
        assert d["reclaim"] is True
        assert d["liquidity_sweep"] is False

    def test_event_type_included_as_string_value(self):
        state = _state(envelope=Event(
            event_type="reclaim", source="tradingview",
            occurred_at=datetime(2026, 7, 18, 13, 35, tzinfo=timezone.utc), event_id="e1",
        ))
        d = market_state_to_dict(state)
        assert d["event_type"] == "reclaim"

    def test_received_at_always_present_though_not_on_the_wire(self):
        # occurred_at and received_at are independently settable (Sprint 1's
        # Event) - the read shape must expose both distinctly, not collapse
        # them into one timestamp field.
        state = _state()
        d = market_state_to_dict(state)
        assert d["timestamp"] == state.envelope.occurred_at.isoformat()
        assert d["received_at"] == state.envelope.received_at.isoformat()

    def test_timeframe_and_bar_status_are_wire_string_values(self):
        d = market_state_to_dict(_state())
        assert d["timeframe"] == "5m"
        assert d["bar_status"] == "closed"


class TestGetLatestMarketState:
    @pytest.mark.asyncio
    async def test_no_data_returns_none(self, repo):
        result = await get_latest_market_state(Symbol("MNQU6"), Timeframe.M5, repo)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_shaped_result(self, repo):
        await repo.ingest(_state(close=Price(20125.75, 0.25)), raw_payload="{}")
        result = await get_latest_market_state(Symbol("MNQU6"), Timeframe.M5, repo)
        assert result["close"] == 20125.75
        assert result["event_id"] == "e1"

    @pytest.mark.asyncio
    async def test_returns_the_actual_latest_by_occurred_at(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        result = await get_latest_market_state(Symbol("MNQU6"), Timeframe.M5, repo)
        assert result["event_id"] == "e2"


class TestGetMarketStateHistory:
    @pytest.mark.asyncio
    async def test_no_data_returns_empty_list(self, repo):
        result = await get_market_state_history(Symbol("MNQU6"), Timeframe.M5, 100, repo)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_dict_shaped_results_most_recent_first(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        result = await get_market_state_history(Symbol("MNQU6"), Timeframe.M5, 100, repo)
        assert [r["event_id"] for r in result] == ["e2", "e1"]

    @pytest.mark.asyncio
    async def test_respects_limit(self, repo):
        for i in range(5):
            await repo.ingest(_state(event_id=f"e{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}")
        result = await get_market_state_history(Symbol("MNQU6"), Timeframe.M5, 2, repo)
        assert len(result) == 2


class TestFindGaps:
    def test_no_states_returns_no_gaps(self):
        assert find_gaps([], Timeframe.M5) == []

    def test_single_state_returns_no_gaps(self):
        assert find_gaps([_state()], Timeframe.M5) == []

    def test_evenly_spaced_bars_have_no_gaps(self):
        states = [
            _state(event_id="e1", occurred_at="2026-07-18T13:30:00"),
            _state(event_id="e2", occurred_at="2026-07-18T13:35:00"),
            _state(event_id="e3", occurred_at="2026-07-18T13:40:00"),
        ]
        assert find_gaps(states, Timeframe.M5) == []

    def test_minor_jitter_under_tolerance_is_not_a_gap(self):
        # 5m timeframe, 1.5x tolerance = 7.5 minutes - 7 minutes is jitter, not a gap
        states = [
            _state(event_id="e1", occurred_at="2026-07-18T13:30:00"),
            _state(event_id="e2", occurred_at="2026-07-18T13:37:00"),
        ]
        assert find_gaps(states, Timeframe.M5) == []

    def test_one_missing_bar_is_detected(self):
        states = [
            _state(event_id="e1", occurred_at="2026-07-18T13:30:00"),
            _state(event_id="e2", occurred_at="2026-07-18T13:40:00"),  # one 5m bar skipped
        ]
        gaps = find_gaps(states, Timeframe.M5)
        assert len(gaps) == 1
        assert gaps[0]["expected_interval_minutes"] == 5
        assert gaps[0]["actual_gap_minutes"] == pytest.approx(10.0)
        assert gaps[0]["estimated_missing_bars"] == 1

    def test_out_of_order_input_is_still_correctly_analyzed(self):
        # get_history's own contract is most-recent-first; find_gaps must not
        # assume any particular input order.
        states = [
            _state(event_id="e2", occurred_at="2026-07-18T13:40:00"),
            _state(event_id="e1", occurred_at="2026-07-18T13:30:00"),
        ]
        gaps = find_gaps(states, Timeframe.M5)
        assert len(gaps) == 1
        assert gaps[0]["after"] == "2026-07-18T13:30:00+00:00"
        assert gaps[0]["before"] == "2026-07-18T13:40:00+00:00"

    def test_multiple_gaps_all_reported(self):
        states = [
            _state(event_id="e1", occurred_at="2026-07-18T13:30:00"),
            _state(event_id="e2", occurred_at="2026-07-18T13:40:00"),  # gap 1
            _state(event_id="e3", occurred_at="2026-07-18T13:45:00"),
            _state(event_id="e4", occurred_at="2026-07-18T14:00:00"),  # gap 2
        ]
        assert len(find_gaps(states, Timeframe.M5)) == 2


class TestGetMarketStateIntegrityReport:
    @pytest.mark.asyncio
    async def test_no_data_returns_empty_report(self, repo):
        report = await get_market_state_integrity_report(Symbol("MNQU6"), Timeframe.M5, 100, repo)
        assert report["checked_count"] == 0
        assert report["gap_count"] == 0
        assert report["gaps"] == []

    @pytest.mark.asyncio
    async def test_reports_symbol_and_timeframe(self, repo):
        report = await get_market_state_integrity_report(Symbol("MNQU6"), Timeframe.M5, 100, repo)
        assert report["symbol"] == "MNQU6"
        assert report["timeframe"] == "5m"

    @pytest.mark.asyncio
    async def test_gap_detected_across_stored_history(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        report = await get_market_state_integrity_report(Symbol("MNQU6"), Timeframe.M5, 100, repo)
        assert report["checked_count"] == 2
        assert report["gap_count"] == 1

    @pytest.mark.asyncio
    async def test_limit_bounds_what_is_checked(self, repo):
        for i in range(5):
            await repo.ingest(_state(event_id=f"e{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}")
        report = await get_market_state_integrity_report(Symbol("MNQU6"), Timeframe.M5, 2, repo)
        assert report["checked_count"] == 2


class TestGetMarketStateExport:
    @pytest.mark.asyncio
    async def test_no_data_returns_empty_export(self, repo):
        report = await get_market_state_export(
            Symbol("MNQU6"), Timeframe.M5,
            datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
            10000, repo,
        )
        assert report["count"] == 0
        assert report["gap_count"] == 0
        assert report["data"] == []

    @pytest.mark.asyncio
    async def test_reports_symbol_timeframe_and_range(self, repo):
        report = await get_market_state_export(
            Symbol("MNQU6"), Timeframe.M5,
            datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
            10000, repo,
        )
        assert report["symbol"] == "MNQU6"
        assert report["timeframe"] == "5m"
        assert report["start"] == "2026-07-18T00:00:00+00:00"
        assert report["end"] == "2026-07-19T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_data_is_dict_shaped_and_chronologically_ordered(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        report = await get_market_state_export(
            Symbol("MNQU6"), Timeframe.M5,
            datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
            10000, repo,
        )
        assert [d["event_id"] for d in report["data"]] == ["e2", "e1"]

    @pytest.mark.asyncio
    async def test_gaps_are_surfaced_inline(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        report = await get_market_state_export(
            Symbol("MNQU6"), Timeframe.M5,
            datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
            10000, repo,
        )
        assert report["gap_count"] == 1
        assert report["count"] == 2

    @pytest.mark.asyncio
    async def test_data_outside_range_excluded(self, repo):
        await repo.ingest(_state(event_id="e-outside", occurred_at="2026-07-17T13:30:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e-inside", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        report = await get_market_state_export(
            Symbol("MNQU6"), Timeframe.M5,
            datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
            10000, repo,
        )
        assert [d["event_id"] for d in report["data"]] == ["e-inside"]


class TestReplayMarketState:
    async def _collect(self, repo, start=None, end=None, limit=10000):
        start = start or datetime(2026, 7, 18, tzinfo=timezone.utc)
        end = end or datetime(2026, 7, 19, tzinfo=timezone.utc)
        return [
            s async for s in replay_market_state(Symbol("MNQU6"), Timeframe.M5, start, end, limit, repo)
        ]

    @pytest.mark.asyncio
    async def test_no_data_yields_nothing(self, repo):
        result = await self._collect(repo)
        assert result == []

    @pytest.mark.asyncio
    async def test_yields_raw_market_state_objects_not_dicts(self, repo):
        # The whole point of this Sprint: Replay is a domain capability, not
        # an HTTP-shaped one - it must yield the actual domain object, never
        # a JSON-ready dict (market_state_to_dict's shape), so a future
        # in-process consumer can operate on it directly.
        await repo.ingest(_state(event_id="e1"), raw_payload="{}")
        result = await self._collect(repo)
        assert len(result) == 1
        assert isinstance(result[0], MarketState)

    @pytest.mark.asyncio
    async def test_yields_in_chronological_ascending_order(self, repo):
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e3", occurred_at="2026-07-18T13:45:00"), raw_payload="{}")
        result = await self._collect(repo)
        assert [s.envelope.event_id for s in result] == ["e1", "e2", "e3"]

    @pytest.mark.asyncio
    async def test_range_boundaries_are_inclusive(self, repo):
        await repo.ingest(_state(event_id="e-start", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e-end", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        result = await self._collect(
            repo,
            start=datetime(2026, 7, 18, 13, 30, tzinfo=timezone.utc),
            end=datetime(2026, 7, 18, 13, 40, tzinfo=timezone.utc),
        )
        assert [s.envelope.event_id for s in result] == ["e-start", "e-end"]

    @pytest.mark.asyncio
    async def test_no_drops_or_duplicates_across_full_series(self, repo):
        for i in range(10):
            await repo.ingest(_state(event_id=f"e{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}")
        result = await self._collect(repo)
        assert [s.envelope.event_id for s in result] == [f"e{i}" for i in range(10)]
        assert len(set(s.envelope.event_id for s in result)) == 10

    @pytest.mark.asyncio
    async def test_respects_limit(self, repo):
        for i in range(5):
            await repo.ingest(_state(event_id=f"e{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}")
        result = await self._collect(repo, limit=2)
        assert [s.envelope.event_id for s in result] == ["e0", "e1"]

    @pytest.mark.asyncio
    async def test_does_not_mix_symbols_or_timeframes(self, repo):
        await repo.ingest(_state(event_id="e1"), raw_payload="{}")
        await repo.ingest(
            _state(event_id="e2", occurred_at="2026-07-18T13:40:00", symbol=Symbol("MNQZ6")), raw_payload="{}"
        )
        result = await self._collect(repo)
        assert [s.envelope.event_id for s in result] == ["e1"]
