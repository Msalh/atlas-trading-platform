# Sprint 1 - Deployment Checklist

## Before pushing this branch anywhere near production
This sprint changes the Procfile to run `atlas.main:app`, which **requires `DATABASE_URL` to
be set** - it fails to start otherwise (deliberately, see architecture-decisions.md #7-ish /
`atlas/db.py`). Do not deploy this branch until Postgres is provisioned and `DATABASE_URL` is
set on the Railway service, or the web service will go down.

## 1. Run the test suite locally
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
Expect **11 passed**. These run against an in-memory repository - no database required. This
was run in this session and confirmed passing.

## 2. Provision Postgres + migrate data
Follow `docs/sprint1/migration-plan.md` steps 1-5 in full before continuing. Do not skip the
row-count verification.

## 3. (Recommended) Run the integration tests against a real Postgres
```bash
TEST_DATABASE_URL="<a disposable postgres url>" python -m pytest tests/integration/ -v
```
These were **not executed in this development session** - there is no local Postgres or
Docker available in this sandbox. They are real, complete tests (not placeholders); running
them against an actual database is the last gate before trusting the concurrency-safety
guarantee (`claim_and_forward`'s advisory lock) in production. Use a disposable database for
this, never production - the fixture `TRUNCATE`s the `trades` table.

## 4. Set Railway environment variables
On the web service (not the Postgres add-on):
- `DATABASE_URL` - should already be present/attachable once the Postgres plugin is added to
  the same project; attach it as a reference variable if Railway doesn't do so automatically.
- `ANTHROPIC_API_KEY`, `WEBHOOK_SECRET`, `PICKMYTRADE_WEBHOOK_URL`, `CLAUDE_MODEL` - carry
  over unchanged from the current deployment. **Verify these still have real values** - a
  prior session flagged that Railway's "Suggested Variables" panel had shown some of these
  blank at one point; confirm before deploying.
- `LIVE_DB_PATH` is no longer read by the running app (only by the one-time migration
  script) - safe to leave set or remove, no behavioral effect either way.

## 5. Push and deploy
Push this branch to the GitHub repo Railway is watching. Railway detects the `Procfile`
change and redeploys automatically, now running `uvicorn atlas.main:app`.

## 6. Post-deploy verification
1. `curl https://<your-app>.up.railway.app/health` -> expect
   `{"ok": true, "database": "ok"}`. If you get `503`, the app is up but Postgres isn't
   reachable - check `DATABASE_URL`.
2. `curl https://<your-app>.up.railway.app/` -> expect the dashboard HTML, showing the
   trades that were migrated in step 2 (confirms the data actually came across).
3. Send a **test entry with a brand-new `correlation_id`** (see the curl examples
   previously in this README/history) and confirm:
   - First send -> `200` or `207` (matches whether `PICKMYTRADE_WEBHOOK_URL` is configured).
   - Second send with the **same** `correlation_id` -> `208`, `duplicate_already_forwarded: true`.
4. Check Railway's log stream for `atlas.trade_events` log lines - confirms the event bus and
   its logging subscriber are wired up correctly.
5. Leave it running for a normal trading session and confirm real TradingView-originated
   entries behave identically to before (same response codes, dashboard shows them, PMT
   relay still works if configured).

## What to verify in TradingView alerts
Nothing changes here this sprint - the webhook URL/path (`/webhook`) and payload format are
identical to Sprint 0. If you previously confirmed there's exactly one alert pointed at the
Railway URL (not at PickMyTrade directly), no further action is needed.

## If something goes wrong
See `docs/sprint1/rollback-plan.md`.
