"""
Integration tests against a real Postgres database (see conftest.py for how the
target database is selected / skipped). These verify the property that cannot be
tested against the in-memory double: that PostgresTradeRepository.claim_and_forward is
safe under true concurrency, not just sequential idempotency.
"""
import asyncio

BASE_ENTRY = {
    "direction": "long", "setup_tag": "BRK", "symbol": "MNQU6", "entry_price": 100,
    "sl": 90, "tp": 120, "atr": 5, "ema_distance_atr": 0.5, "regime_slope_pct": 1.0,
    "sweep_age_bars": 3, "session": "NY", "signal_time": "2026-01-01T00:00:00Z",
}


async def test_claim_and_forward_stores_a_new_entry(repo):
    calls = []

    async def forward():
        calls.append(1)
        return True, 200, None

    result = await repo.claim_and_forward("int-corr-1", BASE_ENTRY, raw_body="{}", forward=forward)

    assert result.duplicate is False
    assert result.forwarded is True
    assert len(calls) == 1


async def test_concurrent_duplicate_webhooks_only_forward_once(repo):
    """The property the advisory lock exists for: two requests for the same
    correlation_id arriving at effectively the same instant must still result in
    exactly one call to `forward`, never two - this is the actual duplicate-real-order
    risk the idempotency guard exists to prevent."""
    call_count = 0

    async def forward():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.2)  # widen the race window
        return True, 200, None

    results = await asyncio.gather(
        repo.claim_and_forward("int-corr-race", BASE_ENTRY, "{}", forward),
        repo.claim_and_forward("int-corr-race", BASE_ENTRY, "{}", forward),
    )

    assert call_count == 1
    duplicates = [r for r in results if r.duplicate]
    originals = [r for r in results if not r.duplicate]
    assert len(duplicates) == 1
    assert len(originals) == 1


async def test_retry_after_failed_forward_is_allowed(repo):
    """A failed forward attempt must not be treated as a duplicate - a retry after a
    genuine failure should be allowed to actually try PickMyTrade again."""
    async def failing_forward():
        return False, None, "simulated network error"

    first = await repo.claim_and_forward("int-corr-retry", BASE_ENTRY, "{}", failing_forward)
    assert first.duplicate is False
    assert first.forwarded is False

    async def succeeding_forward():
        return True, 200, None

    second = await repo.claim_and_forward("int-corr-retry", BASE_ENTRY, "{}", succeeding_forward)
    assert second.duplicate is False
    assert second.forwarded is True


async def test_price_update_and_exit_round_trip(repo):
    async def forward():
        return True, 200, None

    await repo.claim_and_forward("int-corr-lifecycle", BASE_ENTRY, "{}", forward)

    matched = await repo.update_price("int-corr-lifecycle", 105, 500, "2026-01-01T00:05:00Z")
    assert matched == 1

    matched = await repo.update_exit("int-corr-lifecycle", "won", 120, 2000, "2026-01-01T00:10:00Z")
    assert matched == 1

    rows = await repo.list_recent(limit=10)
    row = next(r for r in rows if r["correlation_id"] == "int-corr-lifecycle")
    assert row["status"] == "won"
    assert row["pmt_forwarded"] is True  # untouched by the lifecycle updates
