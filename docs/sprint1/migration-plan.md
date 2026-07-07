# Sprint 1 - SQLite -> Postgres Migration Plan

## Why now
See `docs/sprint1/architecture-decisions.md` #1. Short version: Railway's SQLite volume has
no backups, SQLite serializes writers, and migrating later (after months of trade history and
a live frontend depending on query shapes) is more disruptive than migrating now.

## What moves
The single `trades` table, column-for-column (see `docs/sprint1/database-schema.md` for the
exact type mapping). No data transformation, no column renames, no dropped columns.

## How the copy works
`scripts/migrate_sqlite_to_postgres.py`:
1. Reads every row from the SQLite `trades` table at the given path (read-only - never
   writes to or deletes the SQLite file).
2. Ensures the Postgres schema exists (runs `migrations/` via the same runner the app uses).
3. Upserts every row into Postgres by `correlation_id` (`ON CONFLICT ... DO UPDATE`).
4. Prints a row-count comparison so you can visually confirm nothing was dropped.

Because it's an upsert keyed on `correlation_id` and never touches the source file, it is
**safe to run more than once** - run it once ahead of time, verify, then run it again
immediately before the actual cutover to pick up anything that arrived in between, with zero
risk of duplicating rows.

## Ordered cutover steps
1. **Provision Postgres on Railway** (New -> Database -> PostgreSQL, in the same project as
   the web service). Railway auto-injects `DATABASE_URL` as a reference variable you attach
   to the web service - this has no effect on the currently-running Sprint 0 SQLite app.
2. **Get the SQLite file off the Railway volume.** Either `railway run` a shell against the
   service and read `/data/live.db` directly, or use Railway's volume browser / `railway ssh`
   to copy it locally. (If you don't have an easy way to pull the file, ask before improvising
   - this is trade history, worth being careful with.)
3. **Run the migration script locally** against the downloaded SQLite file and the new
   `DATABASE_URL`:
   ```bash
   DATABASE_URL="<railway postgres url>" python scripts/migrate_sqlite_to_postgres.py /path/to/downloaded/live.db
   ```
   Confirm the printed row count matches what you expect.
4. **Run the integration tests against the same Postgres database** (a throwaway/staging one
   if you have it, otherwise the real one - they only ever touch a `trades` table and
   `TRUNCATE` it, so don't point this at the just-migrated production database unless you're
   fine with it being truncated first):
   ```bash
   TEST_DATABASE_URL="<a disposable postgres url>" python -m pytest tests/integration/ -v
   ```
5. **Re-run the migration script** one more time right before the next step, to pick up any
   trades that arrived since step 3.
6. **Deploy this branch** (Procfile now points at `atlas.main:app`) with `DATABASE_URL` set
   on the Railway service. Railway redeploys automatically on push.
7. **Verify** per `docs/sprint1/deployment-checklist.md`'s post-deploy section.
8. **Leave the SQLite volume and `app.py`/`schema.sql` in place, untouched**, for at least
   one full trading week as a rollback reference (see `docs/sprint1/rollback-plan.md`) before
   considering their removal in a later sprint.

## What is explicitly NOT part of this migration
- No change to the webhook payload shape TradingView sends.
- No change to PickMyTrade's payload shape.
- No change to the dashboard's visual appearance.
- No strategy/Pine changes.
