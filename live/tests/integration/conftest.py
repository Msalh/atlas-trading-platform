"""
Fixtures for integration tests that exercise the real PostgresTradeRepository against
an actual Postgres database. These are skipped automatically unless TEST_DATABASE_URL
is set, since this may not be available on every development machine - see
docs/sprint1/deployment-checklist.md for how to run these against a disposable
Postgres before cutting Railway over to the new backend.

TEST_DATABASE_URL must point at a database that is safe to TRUNCATE - never point
this at production.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# A skipif marker on a conftest.py module doesn't propagate to sibling test modules -
# pytest only honors `pytestmark` inside an actual test module. To skip this whole
# directory (including never invoking the `pool`/`repo` fixtures below, which would
# otherwise try to connect with conninfo=None and fail loudly instead of skipping)
# when there's no database to test against, tell pytest not to collect the test files
# here at all.
collect_ignore_glob = [] if TEST_DATABASE_URL else ["test_*.py"]


@pytest.fixture
async def pool():
    from psycopg_pool import AsyncConnectionPool

    from migrations.runner import run_migrations

    run_migrations(TEST_DATABASE_URL)
    p = AsyncConnectionPool(TEST_DATABASE_URL, min_size=2, max_size=5, open=False)
    await p.open(wait=True, timeout=30)
    async with p.connection() as conn:
        # CASCADE is required, not optional, as of Sprint 6: ai_notes has a foreign
        # key to trades.correlation_id (migrations/0003_ai_notes.sql), and Postgres
        # refuses to TRUNCATE a table referenced by an FK unless the referencing
        # table is truncated in the same statement. CASCADE also resets ai_notes'
        # own identity sequence (RESTART IDENTITY applies to every table actually
        # truncated, not just the one named) - self-healing if a future migration
        # adds another table with an FK to trades, rather than needing this fixture
        # updated by hand every time.
        await conn.execute("TRUNCATE trades RESTART IDENTITY CASCADE")
    yield p
    await p.close()


@pytest.fixture
async def repo(pool):
    from atlas.repositories.postgres import PostgresTradeRepository

    return PostgresTradeRepository(pool)
