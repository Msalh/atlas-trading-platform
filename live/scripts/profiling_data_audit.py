"""
Sprint 24D. Read-only data-availability audit for the Sprint 24C historical
profiler - answers "is there enough real MarketState history in the
configured database to run the profiler meaningfully?" before
profile_market_state_range is ever called.

Never modifies or deletes a stored row - every query here is a SELECT.
Distinct-symbol/timeframe discovery and basic counting (row counts,
earliest/latest occurred_at, CLOSED/FORMING counts, distinct trading_date
count, exact-duplicate-timestamp count, non-monotonic-timestamp count) use
direct SQL against market_state_events, since
atlas.market_engine.ports.MarketStateRepository's Protocol has no method to
enumerate distinct series at all - there is nothing to "bypass" by using SQL
for pure counting/discovery that carries no fact/setup domain logic. Gap
counting and "longest contiguous segment" instead reuse the REAL profiler's
own atlas.profiling.service.segment_by_gap over
PostgresMarketStateRepository.get_range's real MarketState objects - not
reimplemented here, per Sprint 24D's explicit "do not bypass the real
profiler with ad hoc SQL that recomputes facts" instruction (segmentation is
data-quality plumbing, not a fact/setup computation, but this script still
prefers the real function over a second implementation wherever one exists).

Usage:
    DATABASE_URL=postgres://... python scripts/profiling_data_audit.py

Prints one report block per stored (symbol, timeframe) combination and exits
0 whether or not any qualifying real data was found - this script only
reports, it never decides whether to run the profiler.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.rows import dict_row  # noqa: E402

from atlas.core.primitives import Symbol, Timeframe  # noqa: E402
from atlas.db import create_pool  # noqa: E402
from atlas.market_engine.repositories.postgres import PostgresMarketStateRepository  # noqa: E402
from atlas.profiling.models import DEFAULT_EXCLUDED_SYMBOLS  # noqa: E402
from atlas.profiling.service import segment_by_gap  # noqa: E402

_DISCOVER_SQL = """
    SELECT symbol, timeframe, COUNT(*) AS total_rows,
           MIN(occurred_at) AS earliest, MAX(occurred_at) AS latest,
           COUNT(*) FILTER (WHERE bar_status = 'closed') AS closed_rows,
           COUNT(*) FILTER (WHERE bar_status = 'forming') AS forming_rows,
           COUNT(DISTINCT trading_date) AS distinct_trading_dates
    FROM market_state_events
    GROUP BY symbol, timeframe
    ORDER BY symbol, timeframe
"""

_DUPLICATE_AND_NONMONOTONIC_SQL = """
    WITH ordered AS (
        SELECT occurred_at, bar_status,
               LAG(occurred_at) OVER (ORDER BY occurred_at, id) AS prev_occurred_at
        FROM market_state_events
        WHERE symbol = %s AND timeframe = %s
    )
    SELECT
        COUNT(*) FILTER (WHERE occurred_at = prev_occurred_at) AS exact_duplicates,
        COUNT(*) FILTER (WHERE occurred_at < prev_occurred_at) AS non_monotonic
    FROM ordered
"""


async def _audit_one(pool, repository, symbol_ticker, timeframe_value, row):
    print(f"\n=== {symbol_ticker} / {timeframe_value} ===")
    print(f"  total_rows: {row['total_rows']}")
    print(f"  earliest_occurred_at: {row['earliest']}")
    print(f"  latest_occurred_at: {row['latest']}")
    print(f"  closed_rows: {row['closed_rows']}")
    print(f"  forming_rows: {row['forming_rows']}")
    print(f"  distinct_trading_dates: {row['distinct_trading_dates']}")
    is_smoketest = symbol_ticker in DEFAULT_EXCLUDED_SYMBOLS
    print(f"  is_smoketest_symbol: {is_smoketest}")

    try:
        symbol = Symbol(symbol_ticker)
        timeframe = Timeframe(timeframe_value)
    except ValueError as e:
        print(f"  WARNING: symbol/timeframe not constructible as domain types ({e}) - "
              f"cannot run real repository queries or segmentation for this series.")
        return

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_DUPLICATE_AND_NONMONOTONIC_SQL, (symbol_ticker, timeframe_value))
        dup_row = await cur.fetchone()
    print(f"  exact_duplicate_timestamps: {dup_row[0]}")
    print(f"  non_monotonic_timestamps: {dup_row[1]}")

    closed_states = [
        s for s in await repository.get_range(
            symbol, timeframe,
            datetime(1970, 1, 1, tzinfo=timezone.utc), datetime(2100, 1, 1, tzinfo=timezone.utc),
            limit=1_000_000,
        )
        if s.bar_status.value == "closed"
    ]
    if not closed_states:
        print("  raw_cadence_gaps: n/a (no CLOSED rows)")
        print("  longest_contiguous_segment: 0")
        return
    try:
        segments = segment_by_gap(closed_states)
    except Exception as e:  # noqa: BLE001 - report, never crash the audit
        print(f"  WARNING: segment_by_gap raised ({e}) - a duplicate/non-monotonic "
              f"timestamp is already reported above; this series cannot be segmented "
              f"until that is understood.")
        return
    longest = max((len(s) for s in segments), default=0)
    print(f"  raw_cadence_gaps: {max(0, len(segments) - 1)}")
    print(f"  longest_contiguous_segment: {longest} bars")


async def main():
    if not os.environ.get("DATABASE_URL"):
        print(
            "DATABASE_URL is not set in this environment - cannot audit any database.\n"
            "This is not a finding of 'zero real data'; it means this session has no "
            "configured connection to inspect. Set DATABASE_URL (the same value the "
            "running Atlas service uses) and re-run this script."
        )
        return

    pool = await create_pool()
    try:
        repository = PostgresMarketStateRepository(pool)
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_DISCOVER_SQL)
            rows = await cur.fetchall()

        if not rows:
            print("market_state_events contains zero rows for any symbol/timeframe.")
            return

        print(f"Found {len(rows)} distinct (symbol, timeframe) combination(s).")
        for row in rows:
            await _audit_one(pool, repository, row["symbol"], row["timeframe"], row)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
