"""
Postgres connection pool + startup migration trigger. The pool is created once at
application startup (see atlas/main.py's lifespan) and closed on shutdown - not
per-request, unlike the Sprint 0 SQLite version, which opened a fresh connection (and
re-ran the whole schema script) on every single request. Reusing pooled connections is
both faster and is what makes the advisory-lock concurrency guarantee in
PostgresTradeRepository correct (the lock is scoped to a transaction on a pooled
connection, not a throwaway one).
"""
import asyncio
import logging
import time

from psycopg_pool import AsyncConnectionPool

from atlas.config import settings
from migrations.runner import run_migrations

logger = logging.getLogger("atlas.db")

# Sprint 31 - added during a Windows Phase 3 --apply investigation: a
# synchronous psql probe against the same DATABASE_URL connected instantly,
# but the async pool path produced no output and no error - a silent hang.
# AsyncConnectionPool.open(timeout=30)'s own internal timeout is not a
# guarantee that a hang here surfaces as a clean error rather than blocking
# forever, if something about how the surrounding event loop schedules the
# pool's background tasks is the actual problem. This wraps it in an
# independent, outer asyncio.wait_for() so a hang always raises within
# POOL_OPEN_HARD_TIMEOUT_SECONDS - never silently, regardless of whether the
# pool's own internal timeout mechanism fires correctly or not.
POOL_OPEN_HARD_TIMEOUT_SECONDS = 35


async def create_pool() -> AsyncConnectionPool:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Atlas requires Postgres - provision a Postgres "
            "instance (e.g. Railway's Postgres plugin) and set DATABASE_URL before "
            "starting this service. Refusing to start against no database rather than "
            "silently falling back, since that would risk losing trade data."
        )

    started = time.monotonic()
    logger.info("db pool: running migrations")
    run_migrations(settings.database_url)
    logger.info("db pool: migrations applied", extra={"elapsed_seconds": round(time.monotonic() - started, 2)})

    stage_started = time.monotonic()
    pool = AsyncConnectionPool(settings.database_url, min_size=1, max_size=10, open=False)
    logger.info("db pool: constructed (not yet open)", extra={
        "elapsed_seconds": round(time.monotonic() - stage_started, 2),
    })

    stage_started = time.monotonic()
    logger.info("db pool: opening", extra={"hard_timeout_seconds": POOL_OPEN_HARD_TIMEOUT_SECONDS})
    try:
        await asyncio.wait_for(pool.open(wait=True, timeout=30), timeout=POOL_OPEN_HARD_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as e:
        raise RuntimeError(
            f"Postgres connection pool did not open within {POOL_OPEN_HARD_TIMEOUT_SECONDS}s - "
            f"either the pool's own internal open(timeout=30) did not fire, or the surrounding "
            f"event loop is not scheduling its background tasks. See atlas/db.py's own comment "
            f"above create_pool() for context."
        ) from e
    logger.info("db pool: opened", extra={"elapsed_seconds": round(time.monotonic() - stage_started, 2)})
    return pool
