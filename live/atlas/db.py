"""
Postgres connection pool + startup migration trigger. The pool is created once at
application startup (see atlas/main.py's lifespan) and closed on shutdown - not
per-request, unlike the Sprint 0 SQLite version, which opened a fresh connection (and
re-ran the whole schema script) on every single request. Reusing pooled connections is
both faster and is what makes the advisory-lock concurrency guarantee in
PostgresTradeRepository correct (the lock is scoped to a transaction on a pooled
connection, not a throwaway one).
"""
import logging

from psycopg_pool import AsyncConnectionPool

from atlas.config import settings
from migrations.runner import run_migrations

logger = logging.getLogger("atlas.db")


async def create_pool() -> AsyncConnectionPool:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Atlas requires Postgres - provision a Postgres "
            "instance (e.g. Railway's Postgres plugin) and set DATABASE_URL before "
            "starting this service. Refusing to start against no database rather than "
            "silently falling back, since that would risk losing trade data."
        )
    run_migrations(settings.database_url)
    pool = AsyncConnectionPool(settings.database_url, min_size=1, max_size=10, open=False)
    await pool.open(wait=True, timeout=30)
    logger.info("Postgres connection pool opened (migrations applied)")
    return pool
