"""
One-time data migration: copies every row from the Sprint 0 SQLite `trades` table
into the new Postgres `trades` table (see migrations/0001_init.sql - same columns, so
this is a straight column-for-column copy). Safe to re-run: uses
`INSERT ... ON CONFLICT (correlation_id) DO UPDATE SET <all columns>`, so running it
twice (e.g. once ahead of time, then again right before flipping the Procfile, to pick
up any trades that arrived in between) just re-applies the same values.

This only READS from the SQLite file - it never writes to or deletes it, so it is safe
to run against the live Railway volume while the Sprint 0 app is still running, and it
is safe to re-run if something goes wrong downstream.

Usage:
    DATABASE_URL=postgres://... python scripts/migrate_sqlite_to_postgres.py [path/to/live.db]

If no path is given, defaults to the LIVE_DB_PATH environment variable, falling back
to "live.db" next to this script's parent directory - matching how the Sprint 0 app
resolved its database path.
"""
import os
import sqlite3
import sys

import psycopg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrations.runner import run_migrations  # noqa: E402

COLUMNS = [
    "correlation_id", "received_at", "signal_time", "direction", "setup_tag", "symbol",
    "entry_price", "sl", "tp", "atr", "ema_distance_atr", "regime_slope_pct",
    "sweep_age_bars", "session", "status", "current_price", "unrealized_pnl",
    "last_update_at", "exit_price", "realized_pnl", "closed_at", "llm_model",
    "llm_analysis", "llm_error", "pmt_forwarded", "pmt_status_code", "pmt_error",
    "raw_entry_payload",
]


def main():
    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "LIVE_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live.db")
    )
    database_url = os.environ["DATABASE_URL"]  # required - fail loudly if not set

    if not os.path.exists(sqlite_path):
        print(f"No SQLite database found at {sqlite_path} - nothing to migrate.")
        return

    run_migrations(database_url)

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute(f"SELECT {', '.join(COLUMNS)} FROM trades").fetchall()
    sqlite_conn.close()

    print(f"Read {len(rows)} row(s) from {sqlite_path}")

    if not rows:
        print("Nothing to migrate.")
        return

    placeholders = ", ".join(f"%({c})s" for c in COLUMNS)
    update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "correlation_id")
    insert_sql = f"""
        INSERT INTO trades ({', '.join(COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT (correlation_id) DO UPDATE SET {update_clause}
    """

    with psycopg.connect(database_url, autocommit=False) as pg_conn:
        with pg_conn.cursor() as cur:
            for row in rows:
                params = {c: (bool(row[c]) if c == "pmt_forwarded" else row[c]) for c in COLUMNS}
                cur.execute(insert_sql, params)
        pg_conn.commit()

    with psycopg.connect(database_url) as pg_conn:
        count = pg_conn.execute("SELECT count(*) FROM trades").fetchone()[0]

    print(f"Postgres trades table now has {count} row(s).")
    if count < len(rows):
        print(
            "WARNING: Postgres row count is lower than the number of rows read from "
            "SQLite. This is expected only if the counts were already different before "
            "this run for unrelated reasons. Verify manually before proceeding with "
            "cutover."
        )


if __name__ == "__main__":
    main()
