from datetime import datetime, timezone

import pytest

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.ports import IngestOutcome
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository


def _state(event_id="e1", occurred_at="2026-07-18T13:35:00", symbol="MNQU6", timeframe=Timeframe.M5):
    return MarketState(
        envelope=Event(
            event_type="bar_closed",
            source="tradingview",
            occurred_at=datetime.fromisoformat(occurred_at).replace(tzinfo=timezone.utc),
            event_id=event_id,
        ),
        schema_version="1.0",
        symbol=Symbol(symbol),
        timeframe=timeframe,
        bar_status=BarStatus.CLOSED,
    )


@pytest.fixture
def repo():
    return InMemoryMarketStateRepository()


class TestIngest:
    @pytest.mark.asyncio
    async def test_new_event_stored(self, repo):
        outcome = await repo.ingest(_state(event_id="e1"), raw_payload="{}")
        assert outcome == IngestOutcome.STORED

    @pytest.mark.asyncio
    async def test_duplicate_event_id_rejected_as_duplicate(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        outcome = await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        assert outcome == IngestOutcome.DUPLICATE

    @pytest.mark.asyncio
    async def test_duplicate_does_not_overwrite_stored_state(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        latest = await repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
        assert latest.envelope.occurred_at.isoformat() == "2026-07-18T13:35:00+00:00"

    @pytest.mark.asyncio
    async def test_same_event_id_different_symbol_is_not_a_duplicate(self, repo):
        # dedup key is (symbol, timeframe, event_id) - not event_id alone
        await repo.ingest(_state(event_id="e1", symbol="MNQU6"), raw_payload="{}")
        outcome = await repo.ingest(_state(event_id="e1", symbol="MNQZ6"), raw_payload="{}")
        assert outcome == IngestOutcome.STORED

    @pytest.mark.asyncio
    async def test_same_event_id_different_timeframe_is_not_a_duplicate(self, repo):
        await repo.ingest(_state(event_id="e1", timeframe=Timeframe.M5), raw_payload="{}")
        outcome = await repo.ingest(_state(event_id="e1", timeframe=Timeframe.M15), raw_payload="{}")
        assert outcome == IngestOutcome.STORED

    @pytest.mark.asyncio
    async def test_raw_payload_is_preserved(self, repo):
        raw = '{"schema_version": "1.0", "event_id": "e1", "close": 20125.75}'
        await repo.ingest(_state(event_id="e1"), raw_payload=raw)
        assert repo.raw_payload_for(Symbol("MNQU6"), Timeframe.M5, "e1") == raw

    @pytest.mark.asyncio
    async def test_duplicate_does_not_overwrite_raw_payload(self, repo):
        await repo.ingest(_state(event_id="e1"), raw_payload="original")
        await repo.ingest(_state(event_id="e1"), raw_payload="attempted-overwrite")
        assert repo.raw_payload_for(Symbol("MNQU6"), Timeframe.M5, "e1") == "original"


class TestGetLatest:
    @pytest.mark.asyncio
    async def test_no_data_returns_none(self, repo):
        assert await repo.get_latest(Symbol("MNQU6"), Timeframe.M5) is None

    @pytest.mark.asyncio
    async def test_single_event_is_latest(self, repo):
        await repo.ingest(_state(event_id="e1"), raw_payload="{}")
        latest = await repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
        assert latest.envelope.event_id == "e1"

    @pytest.mark.asyncio
    async def test_latest_is_by_occurred_at_not_ingestion_order(self, repo):
        # ingest the newer one FIRST, then the older one - get_latest must
        # still report the one with the greater occurred_at, not "whichever
        # arrived first".
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        latest = await repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
        assert latest.envelope.event_id == "e2"

    @pytest.mark.asyncio
    async def test_late_arriving_older_event_never_becomes_latest(self, repo):
        # this is the specific "out-of-order arrival must not regress latest"
        # property the roadmap's later Sprints depend on being true from the
        # start - proven here, cheaply, before persistence exists.
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        latest_before = await repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        latest_after = await repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
        assert latest_before.envelope.event_id == latest_after.envelope.event_id == "e2"

    @pytest.mark.asyncio
    async def test_different_symbol_does_not_affect_latest(self, repo):
        await repo.ingest(_state(event_id="e1", symbol="MNQU6", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", symbol="MNQZ6", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        latest = await repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
        assert latest.envelope.event_id == "e1"

    @pytest.mark.asyncio
    async def test_different_timeframe_does_not_affect_latest(self, repo):
        await repo.ingest(_state(event_id="e1", timeframe=Timeframe.M5, occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", timeframe=Timeframe.M15, occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        latest = await repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
        assert latest.envelope.event_id == "e1"


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_no_data_returns_empty_list(self, repo):
        assert await repo.get_history(Symbol("MNQU6"), Timeframe.M5) == []

    @pytest.mark.asyncio
    async def test_returns_most_recent_first(self, repo):
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e3", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        history = await repo.get_history(Symbol("MNQU6"), Timeframe.M5)
        assert [s.envelope.event_id for s in history] == ["e2", "e1", "e3"]

    @pytest.mark.asyncio
    async def test_respects_limit(self, repo):
        for i in range(5):
            await repo.ingest(_state(event_id=f"e{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}")
        history = await repo.get_history(Symbol("MNQU6"), Timeframe.M5, limit=2)
        assert len(history) == 2
        assert [s.envelope.event_id for s in history] == ["e4", "e3"]

    @pytest.mark.asyncio
    async def test_does_not_mix_symbols_or_timeframes(self, repo):
        await repo.ingest(_state(event_id="e1", symbol="MNQU6", timeframe=Timeframe.M5), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", symbol="MNQZ6", timeframe=Timeframe.M5), raw_payload="{}")
        await repo.ingest(_state(event_id="e3", symbol="MNQU6", timeframe=Timeframe.M15), raw_payload="{}")
        history = await repo.get_history(Symbol("MNQU6"), Timeframe.M5)
        assert [s.envelope.event_id for s in history] == ["e1"]


def _dt(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class TestGetRange:
    @pytest.mark.asyncio
    async def test_no_data_returns_empty_list(self, repo):
        result = await repo.get_range(
            Symbol("MNQU6"), Timeframe.M5, _dt("2026-07-18T00:00:00"), _dt("2026-07-19T00:00:00")
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_chronological_ascending_order(self, repo):
        # deliberately the OPPOSITE order convention from get_history
        await repo.ingest(_state(event_id="e1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e3", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        result = await repo.get_range(
            Symbol("MNQU6"), Timeframe.M5, _dt("2026-07-18T00:00:00"), _dt("2026-07-19T00:00:00")
        )
        assert [s.envelope.event_id for s in result] == ["e3", "e1", "e2"]

    @pytest.mark.asyncio
    async def test_range_boundaries_are_inclusive(self, repo):
        await repo.ingest(_state(event_id="e-start", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e-end", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
        result = await repo.get_range(
            Symbol("MNQU6"), Timeframe.M5, _dt("2026-07-18T13:30:00"), _dt("2026-07-18T13:40:00")
        )
        assert [s.envelope.event_id for s in result] == ["e-start", "e-end"]

    @pytest.mark.asyncio
    async def test_events_outside_range_excluded(self, repo):
        await repo.ingest(_state(event_id="e-before", occurred_at="2026-07-18T12:59:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e-inside", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
        await repo.ingest(_state(event_id="e-after", occurred_at="2026-07-18T14:01:00"), raw_payload="{}")
        result = await repo.get_range(
            Symbol("MNQU6"), Timeframe.M5, _dt("2026-07-18T13:00:00"), _dt("2026-07-18T14:00:00")
        )
        assert [s.envelope.event_id for s in result] == ["e-inside"]

    @pytest.mark.asyncio
    async def test_respects_limit(self, repo):
        for i in range(5):
            await repo.ingest(_state(event_id=f"e{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}")
        result = await repo.get_range(
            Symbol("MNQU6"), Timeframe.M5, _dt("2026-07-18T00:00:00"), _dt("2026-07-19T00:00:00"), limit=2
        )
        assert len(result) == 2
        assert [s.envelope.event_id for s in result] == ["e0", "e1"]

    @pytest.mark.asyncio
    async def test_does_not_mix_symbols_or_timeframes(self, repo):
        await repo.ingest(_state(event_id="e1", symbol="MNQU6", timeframe=Timeframe.M5), raw_payload="{}")
        await repo.ingest(_state(event_id="e2", symbol="MNQZ6", timeframe=Timeframe.M5), raw_payload="{}")
        await repo.ingest(_state(event_id="e3", symbol="MNQU6", timeframe=Timeframe.M15), raw_payload="{}")
        result = await repo.get_range(
            Symbol("MNQU6"), Timeframe.M5, _dt("2026-07-18T00:00:00"), _dt("2026-07-19T00:00:00")
        )
        assert [s.envelope.event_id for s in result] == ["e1"]
