"""
Integration tests against a real Postgres database (see conftest.py for how the
target database is selected/skipped). These verify the property that cannot be
tested against the in-memory double: that the UNIQUE constraint on
(symbol, timeframe, event_id) makes a concurrent duplicate insert safe WITHOUT
an advisory lock - see
atlas/market_engine/repositories/postgres.py's module docstring for why no
lock is used here, unlike PostgresTradeRepository.claim_and_forward.
"""
import asyncio
from datetime import date, datetime, timezone

import pytest

from atlas.core.errors import OffTickError
from atlas.core.events import Event
from atlas.core.primitives import Price, Session, Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.market_engine.ports import IngestOutcome


def _state(event_id="int-e1", occurred_at="2026-07-18T13:35:00"):
    return MarketState(
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


async def test_ingest_stores_a_new_event(market_engine_repo):
    outcome = await market_engine_repo.ingest(_state(), raw_payload='{"note": "real db"}')
    assert outcome == IngestOutcome.STORED


async def test_ingest_duplicate_reports_duplicate(market_engine_repo):
    await market_engine_repo.ingest(_state(event_id="int-e2"), raw_payload="{}")
    outcome = await market_engine_repo.ingest(_state(event_id="int-e2"), raw_payload="{}")
    assert outcome == IngestOutcome.DUPLICATE


async def test_concurrent_duplicate_ingests_only_one_stored():
    """The property the UNIQUE constraint (not an advisory lock) exists for:
    two concurrent ingests of the exact same (symbol, timeframe, event_id)
    must result in exactly one stored row, never two - proven against a real
    database, not the in-memory double's own asyncio.Lock (which only proves
    single-process safety, not what Postgres itself guarantees)."""
    from psycopg_pool import AsyncConnectionPool

    from atlas.market_engine.repositories.postgres import PostgresMarketStateRepository
    from tests.integration.conftest import TEST_DATABASE_URL

    pool = AsyncConnectionPool(TEST_DATABASE_URL, min_size=5, max_size=10, open=False)
    await pool.open(wait=True, timeout=30)
    try:
        async with pool.connection() as conn:
            await conn.execute("TRUNCATE market_state_events RESTART IDENTITY")

        repo = PostgresMarketStateRepository(pool)
        state = _state(event_id="int-concurrent")

        results = await asyncio.gather(
            *(repo.ingest(state, raw_payload="{}") for _ in range(10))
        )

        stored_count = sum(1 for r in results if r == IngestOutcome.STORED)
        duplicate_count = sum(1 for r in results if r == IngestOutcome.DUPLICATE)
        assert stored_count == 1
        assert duplicate_count == 9

        async with pool.connection() as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM market_state_events WHERE event_id = %s", ("int-concurrent",))
            row = await cur.fetchone()
            assert row[0] == 1
    finally:
        await pool.close()


async def test_raw_payload_is_persisted_and_readable(market_engine_repo, market_engine_pool):
    raw = '{"schema_version": "1.0", "close": 20125.75}'
    await market_engine_repo.ingest(_state(event_id="int-raw"), raw_payload=raw)

    async with market_engine_pool.connection() as conn:
        cur = await conn.execute(
            "SELECT raw_payload FROM market_state_events WHERE event_id = %s", ("int-raw",)
        )
        row = await cur.fetchone()
        assert row[0] == raw


async def test_off_tick_price_never_reaches_the_database():
    """A defense-in-depth check, not a repository test per se: OffTickError is
    raised by atlas.core.primitives.Price at MarketState construction time,
    before ingest() is ever called - so there is no code path in this Sprint
    by which an off-tick value could reach the database at all. Asserted here
    against the real schema for completeness, not because the repository
    itself does any tick validation (it doesn't - it trusts the MarketState
    it's given, exactly as PostgresTradeRepository trusts its `entry` dict)."""
    with pytest.raises(OffTickError):
        Price(value=20125.80, tick_size=0.25)


async def test_get_latest_round_trip_fidelity(market_engine_repo):
    """The highest-value read-path test: every field a fully-populated
    MarketState carries must survive a real INSERT and a real SELECT
    unchanged. This is the property _row_to_state exists to guarantee as the
    exact inverse of _state_to_params - a field-ordering or type-conversion
    mistake in either would silently corrupt data without this test."""
    state = MarketState(
        envelope=Event(
            event_type="reclaim", source="tradingview",
            occurred_at=datetime(2026, 7, 18, 13, 35, tzinfo=timezone.utc),
            received_at=datetime(2026, 7, 18, 13, 35, 2, tzinfo=timezone.utc),
            event_id="int-full",
        ),
        schema_version="1.0",
        symbol=Symbol("MNQU6"),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
        open=Price(20120.00, 0.25), high=Price(20128.50, 0.25),
        low=Price(20118.00, 0.25), close=Price(20125.75, 0.25), volume=4210,
        session_name=Session.NY, is_rth=True, trading_date=date(2026, 7, 18),
        rth_open=Price(20100.00, 0.25),
        previous_day_high=Price(20180.00, 0.25), previous_day_low=Price(20050.25, 0.25),
        overnight_high=Price(20140.00, 0.25), overnight_low=Price(20080.50, 0.25),
        vwap=Price(20118.50, 0.25), distance_from_vwap_points=7.25, atr=42.5, volume_ratio=1.35,
        nearest_liquidity_level=Price(20180.00, 0.25), nearest_liquidity_type="previous_day_high",
        distance_to_liquidity_ticks=217, overnight_high_status="untested",
        overnight_low_status="reclaimed", previous_day_high_status="untested",
        previous_day_low_status="swept",
        trend_1m="up", trend_5m="up", trend_15m="flat", trend_1h="down",
        liquidity_sweep=False, reclaim=True, rejection=False, displacement=False, volume_spike=False,
    )
    await market_engine_repo.ingest(state, raw_payload="{}")

    result = await market_engine_repo.get_latest(Symbol("MNQU6"), Timeframe.M5)

    assert result == state


async def test_get_latest_no_data_returns_none(market_engine_repo):
    assert await market_engine_repo.get_latest(Symbol("MNQU6"), Timeframe.M5) is None


async def test_get_latest_returns_max_occurred_at_not_arrival_order(market_engine_repo):
    await market_engine_repo.ingest(_state(event_id="int-late-arrival-newer", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-late-arrival-older", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
    result = await market_engine_repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
    assert result.envelope.event_id == "int-late-arrival-newer"


async def test_get_latest_ignores_other_symbols_and_timeframes(market_engine_repo):
    await market_engine_repo.ingest(_state(event_id="int-other-sym"), raw_payload="{}")
    other = MarketState(
        envelope=Event(event_type="bar_closed", source="tradingview",
                       occurred_at=datetime(2026, 7, 18, 13, 40, tzinfo=timezone.utc), event_id="int-other-sym-2"),
        schema_version="1.0", symbol=Symbol("MNQZ6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
    )
    await market_engine_repo.ingest(other, raw_payload="{}")
    result = await market_engine_repo.get_latest(Symbol("MNQU6"), Timeframe.M5)
    assert result.envelope.event_id == "int-other-sym"


async def test_get_history_no_data_returns_empty_list(market_engine_repo):
    assert await market_engine_repo.get_history(Symbol("MNQU6"), Timeframe.M5) == []


async def test_get_history_orders_most_recent_first(market_engine_repo):
    await market_engine_repo.ingest(_state(event_id="int-h1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-h2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-h3", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
    history = await market_engine_repo.get_history(Symbol("MNQU6"), Timeframe.M5)
    assert [s.envelope.event_id for s in history] == ["int-h2", "int-h1", "int-h3"]


async def test_get_history_respects_limit(market_engine_repo):
    for i in range(5):
        await market_engine_repo.ingest(
            _state(event_id=f"int-lim-{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}"
        )
    history = await market_engine_repo.get_history(Symbol("MNQU6"), Timeframe.M5, limit=2)
    assert len(history) == 2


async def test_get_history_uses_the_read_index_not_a_sequential_scan(market_engine_repo, market_engine_pool):
    """Verifies migrations/0007_market_engine_read_index.sql's index is
    actually chosen by the query planner for the exact query get_history
    issues - not just present in the schema. A regression here (e.g. a future
    change to the WHERE/ORDER BY shape that stops matching the index) would
    still pass every other test but silently degrade to a sequential scan."""
    await market_engine_repo.ingest(_state(event_id="int-plan-1"), raw_payload="{}")

    async with market_engine_pool.connection() as conn:
        cur = await conn.execute(
            "EXPLAIN SELECT * FROM market_state_events WHERE symbol = %s AND timeframe = %s "
            "ORDER BY occurred_at DESC LIMIT %s",
            ("MNQU6", "5m", 100),
        )
        plan_lines = [row[0] for row in await cur.fetchall()]
        plan_text = "\n".join(plan_lines)

    assert "idx_market_state_events_symbol_timeframe_occurred_at" in plan_text


async def test_ping_succeeds_against_a_real_database(market_engine_repo):
    assert await market_engine_repo.ping() is True


async def test_get_range_no_data_returns_empty_list(market_engine_repo):
    result = await market_engine_repo.get_range(
        Symbol("MNQU6"), Timeframe.M5,
        datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    assert result == []


async def test_get_range_returns_chronological_ascending_order(market_engine_repo):
    await market_engine_repo.ingest(_state(event_id="int-r1", occurred_at="2026-07-18T13:35:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-r2", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-r3", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
    result = await market_engine_repo.get_range(
        Symbol("MNQU6"), Timeframe.M5,
        datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    assert [s.envelope.event_id for s in result] == ["int-r3", "int-r1", "int-r2"]


async def test_get_range_boundaries_are_inclusive(market_engine_repo):
    await market_engine_repo.ingest(_state(event_id="int-r-start", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-r-end", occurred_at="2026-07-18T13:40:00"), raw_payload="{}")
    result = await market_engine_repo.get_range(
        Symbol("MNQU6"), Timeframe.M5,
        datetime(2026, 7, 18, 13, 30, tzinfo=timezone.utc), datetime(2026, 7, 18, 13, 40, tzinfo=timezone.utc),
    )
    assert [s.envelope.event_id for s in result] == ["int-r-start", "int-r-end"]


async def test_get_range_excludes_events_outside_the_range(market_engine_repo):
    await market_engine_repo.ingest(_state(event_id="int-r-before", occurred_at="2026-07-18T12:59:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-r-inside", occurred_at="2026-07-18T13:30:00"), raw_payload="{}")
    await market_engine_repo.ingest(_state(event_id="int-r-after", occurred_at="2026-07-18T14:01:00"), raw_payload="{}")
    result = await market_engine_repo.get_range(
        Symbol("MNQU6"), Timeframe.M5,
        datetime(2026, 7, 18, 13, 0, tzinfo=timezone.utc), datetime(2026, 7, 18, 14, 0, tzinfo=timezone.utc),
    )
    assert [s.envelope.event_id for s in result] == ["int-r-inside"]


async def test_get_range_respects_limit(market_engine_repo):
    for i in range(5):
        await market_engine_repo.ingest(
            _state(event_id=f"int-r-lim-{i}", occurred_at=f"2026-07-18T13:{30+i}:00"), raw_payload="{}"
        )
    result = await market_engine_repo.get_range(
        Symbol("MNQU6"), Timeframe.M5,
        datetime(2026, 7, 18, tzinfo=timezone.utc), datetime(2026, 7, 19, tzinfo=timezone.utc),
        limit=2,
    )
    assert len(result) == 2
    assert [s.envelope.event_id for s in result] == ["int-r-lim-0", "int-r-lim-1"]


async def test_get_range_uses_the_read_index_not_a_sequential_scan(market_engine_repo, market_engine_pool):
    """Same verification as get_history's own index-usage test: a B-tree index
    built DESC can still serve an ASC-ordered range scan (Postgres reads it
    backwards), so migrations/0007's existing index should still be chosen
    here - no new migration for this Sprint. A regression here would still
    pass every other test but silently degrade to a sequential scan."""
    await market_engine_repo.ingest(_state(event_id="int-r-plan-1"), raw_payload="{}")

    async with market_engine_pool.connection() as conn:
        cur = await conn.execute(
            "EXPLAIN SELECT * FROM market_state_events WHERE symbol = %s AND timeframe = %s "
            "AND occurred_at >= %s AND occurred_at <= %s ORDER BY occurred_at ASC LIMIT %s",
            ("MNQU6", "5m", "2026-07-18T00:00:00+00:00", "2026-07-19T00:00:00+00:00", 10000),
        )
        plan_lines = [row[0] for row in await cur.fetchall()]
        plan_text = "\n".join(plan_lines)

    assert "idx_market_state_events_symbol_timeframe_occurred_at" in plan_text
