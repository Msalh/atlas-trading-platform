"""Migration-free PostgreSQL lifecycle for the TraderNow read-only service."""

from __future__ import annotations

import asyncio

from psycopg_pool import AsyncConnectionPool

POOL_OPEN_HARD_TIMEOUT_SECONDS = 35
_READ_PROBE = "SELECT 1 FROM market_state_events LIMIT 1"


async def create_read_only_pool(database_url: str) -> AsyncConnectionPool:
    """Open a pool whose sessions reject writes; never imports migration code."""
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required by the TraderNow read-only service"
        )

    pool = AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"options": "-c default_transaction_read_only=on"},
    )
    try:
        await asyncio.wait_for(
            pool.open(wait=True, timeout=30),
            timeout=POOL_OPEN_HARD_TIMEOUT_SECONDS,
        )
        await verify_read_only_access(pool)
    except Exception:
        await pool.close()
        raise
    return pool


async def verify_read_only_access(pool: AsyncConnectionPool) -> None:
    """Prove session read-only mode and SELECT access to the sole required table."""
    async with pool.connection() as connection:
        read_only = await connection.execute("SHOW transaction_read_only")
        row = await read_only.fetchone()
        if row is None or str(row[0]).lower() != "on":
            raise RuntimeError("database session is not transaction read-only")
        await connection.execute(_READ_PROBE)
