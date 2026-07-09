"""
Developer-only cleanup: closes open trades left behind by the Pine strategy's E2E Test
Mode (see pine/MNQU6_ICT_Funded_v1.pine's "Developer Tool" section). That mode only
ever sends an "entry" webhook - never price_update or exit - because it's a one-shot
manual trigger for verifying the TradingView -> Atlas -> PickMyTrade relay path, not a
simulated position with a lifecycle. Every E2E test run therefore leaves one open
trade in Atlas's database forever, since nothing else will ever close it.

Safety, by construction:
  - Only ever touches trades whose correlation_id starts with "E2E-" - the exact,
    hardcoded prefix the Pine E2E block always builds
    ("E2E-" + syminfo.ticker + "-" + str.tostring(time)), never used by a real
    strategy signal (those use str.tostring(time) alone, with no prefix). Real trades
    are never matched, no matter what setup_tag or symbol they have.
  - Closes trades with status "test_closed", not "won"/"lost" - atlas/analytics.py and
    atlas/risk.py both only treat status in ("won", "lost") as a closed trade for
    P&L/win-rate/drawdown purposes (see _closed_trades()/compute_risk_snapshot()), so
    a "test_closed" trade is automatically excluded from every real performance
    number, while also no longer matching status='open' (so it stops showing as the
    current position). realized_pnl is set to 0.0 as an extra guard even though the
    status alone already excludes it.
  - Calls TradeRepository.update_exit() - the exact same method a real exit webhook
    uses - which only ever updates the trades table. It has no PickMyTrade call in it
    at all (only claim_and_forward, used for entries, ever calls PickMyTrade) - this
    script cannot reach PickMyTrade even by accident.
  - Defaults to a dry run: lists exactly what would be closed and does not write
    anything unless --apply is passed.

Usage:
    DATABASE_URL=postgres://... python scripts/close_e2e_test_trades.py            # dry run
    DATABASE_URL=postgres://... python scripts/close_e2e_test_trades.py --apply    # actually closes them
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg_pool import AsyncConnectionPool  # noqa: E402

from atlas.repositories.postgres import PostgresTradeRepository  # noqa: E402
from migrations.runner import run_migrations  # noqa: E402

E2E_CORRELATION_ID_PREFIX = "E2E-"
TEST_CLOSED_STATUS = "test_closed"
SCAN_LIMIT = 2000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_e2e_test_trade(correlation_id: str) -> bool:
    """The one safety check this whole script depends on - kept as its own pure,
    dependency-free function so it's directly unit-testable without a database."""
    return correlation_id.startswith(E2E_CORRELATION_ID_PREFIX)


async def main() -> None:
    apply_changes = "--apply" in sys.argv[1:]
    database_url = os.environ["DATABASE_URL"]  # required - fail loudly if not set

    run_migrations(database_url)
    pool = AsyncConnectionPool(database_url, min_size=1, max_size=2, open=False)
    await pool.open(wait=True, timeout=30)
    try:
        repository = PostgresTradeRepository(pool)
        open_trades = await repository.list_recent(limit=SCAN_LIMIT, status="open")
        e2e_open_trades = [t for t in open_trades if is_e2e_test_trade(t["correlation_id"])]

        if not e2e_open_trades:
            print(f"No open E2E test trades found (scanned {len(open_trades)} open trade(s) total).")
            return

        print(f"Found {len(e2e_open_trades)} open E2E test trade(s) out of {len(open_trades)} open trade(s) total:")
        for t in e2e_open_trades:
            print(f"  {t['correlation_id']}  setup_tag={t.get('setup_tag')}  received_at={t.get('received_at')}")

        if not apply_changes:
            print("\nDry run only - no changes made. Re-run with --apply to close these trades.")
            return

        closed_at = now_iso()
        for t in e2e_open_trades:
            await repository.update_exit(
                t["correlation_id"], TEST_CLOSED_STATUS, exit_price=None, realized_pnl=0.0, closed_at=closed_at,
            )
        print(f"\nClosed {len(e2e_open_trades)} trade(s) with status='{TEST_CLOSED_STATUS}', realized_pnl=0.0.")
        print("PickMyTrade was not contacted - update_exit only ever writes to the trades table.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
