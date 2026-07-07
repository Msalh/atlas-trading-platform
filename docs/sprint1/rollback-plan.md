# Sprint 1 - Rollback Plan

## Why this is safe to roll back
Nothing in this sprint deletes or modifies the Sprint 0 code path:
- `app.py` and `schema.sql` are untouched and still fully functional as a standalone SQLite
  app - they're just no longer what the `Procfile` points at.
- The SQLite volume on Railway is never written to by anything in this sprint - the
  migration script only reads from it.
- The new Postgres database is additive - rolling back does not require deleting it.

So rollback is a **one-line revert**, not a data-recovery exercise.

## If the deploy fails to start (e.g. `DATABASE_URL` missing/misconfigured)
Railway will show the service as crashed with the `RuntimeError` message from
`atlas/db.py` in the logs (`"DATABASE_URL is not set..."` or a connection failure).

**Fastest fix:** correct the `DATABASE_URL` variable and let Railway redeploy - no code
change needed if the issue is just a missing/wrong env var.

**If that's not quick to diagnose:** revert the Procfile line:
```
web: uvicorn app:app --host 0.0.0.0 --port $PORT
```
and push. Railway redeploys the old Sprint 0 app against the still-intact SQLite volume,
picking up exactly where it left off before this sprint's deploy - any trades that arrived
during the brief outage window are still in the Sprint 0 flow's normal path (TradingView will
have gotten a connection error and, depending on its retry behavior, may or may not redeliver
- check the Pine alert log after recovering).

Alternative, even faster: Railway's dashboard has a **"redeploy previous deployment"** button
under the Deployments tab - use that instead of a git revert if you need to move fast.

## If the deploy starts fine but behaves incorrectly
1. Compare against `docs/sprint1/api-contracts.md` - if response shapes/codes don't match,
   that's a real bug, not a rollback situation; check Railway logs for the specific request.
2. If trade data looks wrong/missing on the dashboard, check whether the migration step
   (`scripts/migrate_sqlite_to_postgres.py`) actually ran and its printed row count matched -
   re-run it (safe to re-run, see migration-plan.md).
3. If PickMyTrade forwarding stopped working, check `PICKMYTRADE_WEBHOOK_URL` is still set on
   the Railway service - environment variables are per-service and this sprint didn't touch
   that variable, but it's worth confirming nothing reset it.

## Full rollback (abandon the Postgres cutover entirely)
1. Revert the `Procfile` change (see above).
2. Leave `DATABASE_URL` set or remove it - the Sprint 0 app never reads it, so it's inert
   either way.
3. The SQLite volume is exactly as it was, since nothing in this sprint wrote to it - the
   Sprint 0 app resumes with full history intact.
4. No data was lost: the new Postgres database still has everything migrated as of the last
   migration script run, if you want to retry the cutover later.

## When it's safe to actually delete the Sprint 0 files
Not as part of this sprint. Recommend keeping `app.py`, `schema.sql`, and the SQLite volume
for at least one full week of clean production operation on the new Postgres-backed service
before removing them in a later sprint's cleanup task.
