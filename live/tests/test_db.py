"""
Sprint 31 - tests for atlas.db.create_pool()'s diagnostic addition (staged
logging + an independent hard timeout around pool.open()), added during a
Windows Phase 3 --apply investigation where the async pool path hung with
no error. Does not touch a real Postgres - AsyncConnectionPool itself is
replaced with fakes, since this only needs to prove the WRAPPING behavior
around whatever the pool does (bounded timeout, correct return value), not
the pool's own internals.
"""
import asyncio

import pytest

from atlas import db


class _HangingPool:
    def __init__(self, *args, **kwargs):
        pass

    async def open(self, wait=True, timeout=30):
        await asyncio.sleep(100)  # never completes within any real test run


class _FastPool:
    def __init__(self, *args, **kwargs):
        self.opened = False

    async def open(self, wait=True, timeout=30):
        self.opened = True


class TestCreatePoolHardTimeout:
    @pytest.mark.asyncio
    async def test_a_hang_in_pool_open_raises_within_the_hard_timeout_not_forever(self, monkeypatch):
        monkeypatch.setattr(db, "POOL_OPEN_HARD_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(db, "AsyncConnectionPool", _HangingPool)
        monkeypatch.setattr(db, "run_migrations", lambda url: None)
        monkeypatch.setattr(db.settings, "database_url", "postgres://fake/for-test")

        with pytest.raises(RuntimeError, match="did not open within"):
            await db.create_pool()

    @pytest.mark.asyncio
    async def test_a_fast_pool_open_succeeds_and_returns_the_pool(self, monkeypatch):
        monkeypatch.setattr(db, "AsyncConnectionPool", _FastPool)
        monkeypatch.setattr(db, "run_migrations", lambda url: None)
        monkeypatch.setattr(db.settings, "database_url", "postgres://fake/for-test")

        pool = await db.create_pool()
        assert isinstance(pool, _FastPool)
        assert pool.opened is True

    @pytest.mark.asyncio
    async def test_no_database_url_still_raises_immediately_unchanged(self, monkeypatch):
        monkeypatch.setattr(db.settings, "database_url", "")
        with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
            await db.create_pool()
