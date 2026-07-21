# Staging Rollback Plan

This is the **staging** rollback plan - lower stakes than
`docs/sprint10/deployment-runbook.md`'s production rollback section, because a staging
database holds no real trading history and `PICKMYTRADE_WEBHOOK_URL` should be unset
(see the Safety Gates in `docs/staging/deployment-checklist.md`), so there's no real
order-execution risk to protect against here. Use this for "the staging deploy is
broken and I want it back to a known-good state," not for anything touching real money.

## If the backend deploy is broken (crash-loop, 500s, obviously wrong behavior)

1. **Railway dashboard → Deployments tab → find the last working deployment → Redeploy.**
   This is the fastest path back to a known-good state and doesn't require touching
   git at all.
2. If the issue is a missing/wrong environment variable (the most likely cause for a
   first-time deploy - see the checklist's Step 3), fix the variable in **Variables**
   and let Railway redeploy automatically rather than rolling back the code.
3. If you need to roll back the *code* (not just config), and the bad commit hasn't
   been redeployed over by a fix yet, use Railway's deployment history the same way -
   no git revert needed on your end, Railway keeps prior build artifacts.
4. **Migrations are forward-only** (`migrations/runner.py` has no `down` migration
   support, by design - see `docs/sprint1/architecture-decisions.md`), same as
   production. An application-only rollback (step 1/3 above) is safe only when the
   older code is schema-compatible with whatever migrations have already applied -
   check that before assuming a code rollback fixes things. If it isn't compatible,
   staging has a cheaper escape hatch production doesn't: wipe and restart clean (see
   "If the Postgres data looks wrong" below), rather than writing a corrective forward
   migration - there's no real trading history here to preserve. See
   `docs/ui_v2/deployment-runbook.md` §8 for the fuller production-grade treatment of
   this policy (application-only rollback vs. roll-forward, operator compatibility
   check) - it applies unchanged to this project's backend regardless of which
   Railway environment is running it.

## If the Postgres data looks wrong

Because this is staging, the simplest fix is usually **not** a careful PITR restore -
it's wiping and starting clean:

1. Stop the backend service (Railway dashboard → pause/stop) so nothing writes while
   you clean up.
2. Connect to the staging Postgres directly (Railway's dashboard has a **Connect**
   tab with a `psql` command, or use any Postgres client with the `DATABASE_URL`
   Railway shows you) and either:
   - `TRUNCATE trades, ai_notes RESTART IDENTITY;` to wipe all trade data and start
     fresh (migrations/schema stay intact), or
   - `DROP DATABASE` and recreate it, then let the backend's next startup re-run
     migrations from scratch (`migrations/runner.py` applies every migration file in
     order automatically on startup).
3. Restart the backend service.

This is explicitly **not** the procedure for the real funded-account database - see
`docs/sprint10/postgres-backup-checklist.md` for that.

## If the frontend deploy is broken

**Railway dashboard → the frontend service's Deployments tab → pick the last working
deployment → Redeploy.** Same mechanism as the backend rollback above, since both
services now live on the same platform - there's no separate dashboard or "promote to
production" step to remember. Instant, no rebuild needed if Railway already has the
prior build artifact.

## If you're not sure what's wrong

1. Run `live/scripts/smoke_test.sh` against the current deployment first - it will
   tell you specifically which check is failing (auth, health, SSE, etc.) rather than
   leaving you to guess from a vague "something's broken."
2. Check each service's own deploy logs in the Railway dashboard (backend and
   frontend are separate services with separate log streams, even though they're in
   the same project) - a `RuntimeError` from `Settings.validate_for_startup()`
   (missing `WEBHOOK_SECRET`/`API_KEY`/`MARKET_STATE_WEBHOOK_SECRET`) is by far the
   most likely cause of a backend that looks broken immediately after a fresh deploy.
3. If genuinely stuck, tearing the whole staging environment down and re-following
   `docs/staging/deployment-checklist.md` from Step 1 again is a completely reasonable
   option for a staging environment - there's no real data or real trading history at
   stake here to preserve.

## Full teardown (if you want to stop staging entirely)

1. Railway: delete the backend service, the frontend service, and the Postgres plugin
   from the project (**Settings → Danger Zone** on each) - or delete the whole
   project at once if none of it needs to survive.
2. Nothing on the TradingView/PickMyTrade side needs to change, since staging was
   never connected to either (per the Safety Gates) - this teardown has zero impact on
   your real trading setup.
