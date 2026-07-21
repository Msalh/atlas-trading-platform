"""
Production-hardening: `_in_flight_locks` bounded-growth fix.

Covers two things the original `dict[key, asyncio.Lock] = {}` with a bare
`setdefault` could not guarantee together: (1) concurrent requests for the
same cache key still coalesce into exactly one computation, and (2) the
registry entry is removed once nobody needs it anymore, so it cannot grow
without bound as new cache keys appear (a new one on every closed bar, per
symbol/timeframe/window).
"""
import asyncio

import pytest

from atlas.api.v1 import setup_engine as se_module
from atlas.core.primitives import Symbol, Timeframe
from tests.conftest import market_state_payload


class _DummyResult:
    """Stands in for a LiveWindowResult - LiveWindowCache.put() never
    inspects its value, so any sentinel object is fine."""


@pytest.fixture(autouse=True)
def _clean_module_state():
    """The lock registry and cache are process-lifetime module globals, so
    each test needs a clean slate rather than leaking into the next."""
    se_module._in_flight_locks.clear()
    se_module._cache.invalidate_all()
    yield
    se_module._in_flight_locks.clear()
    se_module._cache.invalidate_all()


def _make_slow_build(call_log: list, release: "asyncio.Event", delay: float = 0.0):
    async def _fake_build_live_window_result(*args, **kwargs):
        call_log.append(1)
        if delay:
            await asyncio.sleep(delay)
        else:
            await release.wait()
        return _DummyResult()

    return _fake_build_live_window_result


async def test_concurrent_requests_for_same_key_coalesce_to_one_computation(
    client, market_state_repository, monkeypatch,
):
    client.post("/api/v1/market-state", json=market_state_payload())

    call_log: list = []
    release = asyncio.Event()
    monkeypatch.setattr(
        se_module.episode_projector, "build_live_window_result", _make_slow_build(call_log, release),
    )

    symbol, timeframe = Symbol("MNQU6"), Timeframe("5m")

    async def _first_call():
        result = await se_module._get_or_compute(symbol, timeframe, 20, 500, market_state_repository)
        return result

    async def _second_call():
        # Give the first call a chance to register its lock and start
        # "computing" (blocked on `release`) before this one starts.
        await asyncio.sleep(0.01)
        assert len(se_module._in_flight_locks) == 1  # second waiter finds the first's entry, doesn't create a new one
        release.set()  # let the first call's computation finish now that we've observed the shared entry
        return await se_module._get_or_compute(symbol, timeframe, 20, 500, market_state_repository)

    first_result, second_result = await asyncio.gather(_first_call(), _second_call())

    assert len(call_log) == 1  # exactly one real computation, not two
    assert first_result is second_result  # second waiter got the first's result via the cache re-check, not its own


async def test_registry_entry_is_removed_after_the_last_waiter_finishes(
    client, market_state_repository, monkeypatch,
):
    client.post("/api/v1/market-state", json=market_state_payload())

    call_log: list = []
    release = asyncio.Event()
    release.set()  # resolve immediately - this test cares about cleanup, not overlap timing
    monkeypatch.setattr(
        se_module.episode_projector, "build_live_window_result", _make_slow_build(call_log, release),
    )

    symbol, timeframe = Symbol("MNQU6"), Timeframe("5m")
    await se_module._get_or_compute(symbol, timeframe, 20, 500, market_state_repository)

    assert len(se_module._in_flight_locks) == 0  # nothing left behind once the single caller is done


async def test_many_distinct_keys_never_leave_stale_entries_behind(
    client, market_state_repository, monkeypatch,
):
    """Regression for the actual reported failure mode: a new cache key on
    every closed bar (a new `latest_bar_timestamp`) must not accumulate
    forever in `_in_flight_locks` across the life of the process."""
    call_log: list = []
    release = asyncio.Event()
    release.set()
    monkeypatch.setattr(
        se_module.episode_projector, "build_live_window_result", _make_slow_build(call_log, release),
    )

    symbol, timeframe = Symbol("MNQU6"), Timeframe("5m")
    for i in range(25):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id=f"e-coalesce-{i}", timestamp=f"2026-07-18T13:{i:02d}:00Z",
        ))
        await se_module._get_or_compute(symbol, timeframe, 20, 500, market_state_repository)

    assert len(se_module._in_flight_locks) == 0
    assert len(call_log) == 25  # a genuinely distinct key (new latest bar) every time - no false coalescing either


async def test_second_waiter_receives_the_same_lock_object_while_the_first_is_active():
    """Direct lifecycle test of the acquire/release primitives: the race the
    fix must prevent is a second concurrent caller for the same key getting
    handed a *different* lock than the one an in-progress first caller is
    holding, which would defeat coalescing entirely."""
    key = ("MNQU6", "5m", 20, "2026-07-18T13:00:00Z", "rfp", "sfp")

    first_entry = await se_module._acquire_coalescing_lock(key)
    assert first_entry.waiters == 1

    second_entry = await se_module._acquire_coalescing_lock(key)
    assert second_entry is first_entry  # same lock object, not a fresh one
    assert second_entry.waiters == 2

    await se_module._release_coalescing_lock(key, first_entry)
    assert key in se_module._in_flight_locks  # still referenced by the second waiter - not removed yet
    assert first_entry.waiters == 1

    await se_module._release_coalescing_lock(key, second_entry)
    assert key not in se_module._in_flight_locks  # last release removes the entry
