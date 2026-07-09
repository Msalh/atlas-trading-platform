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


async def test_update_pmt_diagnostics_round_trips_through_real_postgres(repo):
    """pmt_relay_diagnostics is stored as a JSON string in a TEXT column
    (update_pmt_diagnostics does the json.dumps) but must come back as a real dict on
    every read path - dict_row does not auto-decode TEXT columns the way it would a
    native JSON/JSONB column, so get_by_correlation_id must decode it explicitly (see
    _decode_trade in atlas/repositories/postgres.py). Asserting direct dict equality
    here (not json.loads(row[...])) is deliberate: if the decode step regresses and
    this field comes back as a raw string again, this comparison fails outright rather
    than the test papering over it with a redundant manual decode."""
    async def forward():
        return True, 200, None

    await repo.claim_and_forward("int-corr-diagnostics", BASE_ENTRY, "{}", forward)

    diagnostics = {
        "url": "https://pmt.example.com/hook", "method": "POST",
        "payload": {"token": "***1234"}, "status_code": 200,
        "response_body": "OK", "exception": None, "duration_ms": 42.5,
    }
    matched = await repo.update_pmt_diagnostics("int-corr-diagnostics", diagnostics)
    assert matched == 1

    row = await repo.get_by_correlation_id("int-corr-diagnostics")
    assert row["pmt_relay_diagnostics"] == diagnostics
    assert isinstance(row["pmt_relay_diagnostics"], dict)


async def test_update_pmt_diagnostics_decoded_consistently_across_all_read_paths(repo):
    """Same decode must apply on list_recent and get_open_trade too, not just
    get_by_correlation_id - these are three separate SELECT * queries, each needing
    its own _decode_trade call."""
    async def forward():
        return True, 200, None

    await repo.claim_and_forward("int-corr-diag-multi", BASE_ENTRY, "{}", forward)
    diagnostics = {"url": "https://pmt.example.com/hook", "status_code": 200, "response_body": "OK"}
    await repo.update_pmt_diagnostics("int-corr-diag-multi", diagnostics)

    recent_rows = await repo.list_recent(limit=10)
    recent_row = next(r for r in recent_rows if r["correlation_id"] == "int-corr-diag-multi")
    assert recent_row["pmt_relay_diagnostics"] == diagnostics

    open_row = await repo.get_open_trade()
    assert open_row is not None
    assert open_row["pmt_relay_diagnostics"] == diagnostics


async def test_pmt_relay_diagnostics_is_none_when_never_set(repo):
    """The common case - most trades never have diagnostics written at all (duplicate,
    risk-enforcement block, or simply never forwarded) - must decode to None, not an
    empty string or a json.loads crash on NULL."""
    async def forward():
        return True, 200, None

    await repo.claim_and_forward("int-corr-no-diagnostics", BASE_ENTRY, "{}", forward)

    row = await repo.get_by_correlation_id("int-corr-no-diagnostics")
    assert row["pmt_relay_diagnostics"] is None


async def test_update_pmt_diagnostics_no_matching_trade_returns_zero(repo):
    matched = await repo.update_pmt_diagnostics("int-corr-does-not-exist", {"status_code": 200})
    assert matched == 0


async def test_e2e_trade_closed_as_test_closed_leaves_no_open_position(repo):
    """The core safety property scripts/close_e2e_test_trades.py depends on: closing a
    trade with status='test_closed' (rather than 'won'/'lost') removes it from
    get_open_trade() - the actual method used to close E2E test trades, exercised here
    against a real database rather than assumed."""
    async def forward():
        return True, 200, None

    e2e_entry = {**BASE_ENTRY, "setup_tag": "E2E_TEST"}
    await repo.claim_and_forward("E2E-MNQU6-1720000000000", e2e_entry, "{}", forward)

    assert (await repo.get_open_trade())["correlation_id"] == "E2E-MNQU6-1720000000000"

    await repo.update_exit("E2E-MNQU6-1720000000000", "test_closed", None, 0.0, "2026-01-01T00:00:00Z")

    assert await repo.get_open_trade() is None

    rows = await repo.list_recent(limit=10)
    closed_row = next(r for r in rows if r["correlation_id"] == "E2E-MNQU6-1720000000000")
    assert closed_row["status"] == "test_closed"
    assert closed_row["realized_pnl"] == 0.0
