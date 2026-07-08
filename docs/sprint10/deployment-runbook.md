# Sprint 10 - Deployment Runbook

A single, practical reference for taking a change live and for responding when
something breaks in production. Supersedes scattering this information across every
prior sprint's own deployment checklist - those still document what changed *in that
sprint specifically*; this is the one doc to actually follow at deploy time or during
an incident.

## Before every deploy

1. **CI is green.** `.github/workflows/ci.yml` runs on every push/PR - both
   `backend-tests` (152+ unit tests against an in-memory repository, plus the
   integration suite against a real Postgres service container, plus a coverage gate
   at 80%) and `frontend-checks` (`tsc`, `lint`, `build`) must pass. Do not deploy off
   a red CI run, and do not deploy a commit CI hasn't run against at all.
2. **Required environment variables are set** on both Railway (backend) and Vercel
   (frontend) - see `docs/sprint9/deployment-checklist.md` for the full list
   (`DATABASE_URL`, `WEBHOOK_SECRET`, `API_KEY`, `ANTHROPIC_API_KEY`,
   `PICKMYTRADE_WEBHOOK_URL`, `FRONTEND_ORIGINS`, the four `ACCOUNT_*` variables if
   using `RISK_ENFORCEMENT=true`) plus this sprint's additions:
   - `ALERT_WEBHOOK_URL` (optional) - a Slack/Discord-compatible incoming webhook URL.
     If unset, PMT-failure and sustained-Claude-failure alerts are silently disabled -
     decide deliberately, don't leave this unset by omission.
   - `CLAUDE_FAILURE_ALERT_THRESHOLD` (optional, default `3`) - how many consecutive
     Claude failures before an alert fires.
3. **Review what's actually changing.** `git log main..<your branch>` (or the PR diff)
   - for this specific system, pay particular attention to anything touching
     `atlas/api/v1/webhook.py`, `atlas/services/pickmytrade.py`, or
     `atlas/repositories/*` (the order-relay-critical path) versus everything else
     (AI, analytics, risk display, frontend) which carries lower deploy risk.

## Deploying

### Backend (Railway)

1. Push to the branch Railway is configured to auto-deploy from (or trigger a manual
   deploy from the Railway dashboard, if auto-deploy isn't configured).
2. Railway runs `uvicorn atlas.main:app --host 0.0.0.0 --port $PORT` (per `Procfile`).
   The app runs its startup sequence before accepting traffic:
   `Settings.validate_for_startup()` (refuses to start without `WEBHOOK_SECRET`/
   `API_KEY`, or if `RISK_ENFORCEMENT=true` without the four account variables) →
   migrations auto-apply (`migrations/runner.py`) → the connection pool opens.
3. **If the deploy crash-loops**, check Railway's deploy logs first for a
   `RuntimeError` from `validate_for_startup()` - this is by far the most likely cause
   of a clean-looking deploy that immediately fails to start, and the error message
   names exactly which variable is missing.
4. Watch Railway's health check (`GET /api/v1/health`) go green. If it's using the
   readiness signal correctly, Railway won't route traffic to the new instance until
   this passes.

### Frontend (Vercel)

1. Push to the branch Vercel is configured to auto-deploy from, or trigger manually.
2. `npm run build` runs as part of Vercel's build step - this will fail the deploy
   outright if `tsc`/lint/the production build itself has an error (matching what CI
   already checked, as a second independent gate).
3. Vercel deploys are atomic and instantly reversible (see Rollback below) - there's
   no equivalent "crash-loop" risk here the way there is for the backend.

## After every deploy

1. `curl https://<your-app>.up.railway.app/api/v1/health` - confirm `{"ok": true,
   "database": "ok", ...}` and that `uptime_seconds` is small (confirms this really is
   the new process, not a stale response from a cached edge/proxy).
2. `curl -H "Authorization: Bearer <API_KEY>" https://<your-app>.up.railway.app/api/v1/status`
   - confirm the response shape looks right and, if this deploy followed real trading
     activity recently, that `tradingview`/`pickmytrade`/`claude` timestamps are
     recent and not suspiciously stale.
3. Open the deployed frontend, confirm the dashboard loads, the SSE connection status
   dot goes live (green), and a trade detail page renders without console errors.
4. If this deploy touched the webhook/PMT relay path specifically (see "review what's
   changing" above), watch the very next real TradingView signal go through end to
   end - don't consider a relay-path deploy verified until you've seen at least one
   real entry get `pmt_forwarded: true`.
5. Check Railway's log stream for any `ERROR`/`CRITICAL` level structured log lines in
   the first few minutes (see `atlas/logging_config.py` - every log line is JSON, so
   this is filterable by `"level":"ERROR"` in Railway's log search, not just visual
   scanning).

## Rollback

### Backend (Railway)
Railway keeps prior deploys - use the dashboard's **Deployments** tab to redeploy the
last known-good build. This does **not** roll back the database schema - migrations
are forward-only (`migrations/runner.py` has no `down` migration support, by design,
see `docs/sprint1/architecture-decisions.md`). If the bad deploy included a migration
that needs undoing, that requires a manually-written rollback SQL script, not an
automated one - write and test it before running it against production, the same
discipline as any other manual production SQL.

### Frontend (Vercel)
Vercel's dashboard → **Deployments** → pick the previous deployment → **Promote to
Production**. Instant, no build step re-run needed - this is the fastest rollback path
in the whole system, use it liberally if a frontend deploy looks wrong.

## Incident response

### PickMyTrade forward failures
- **Signal:** an alert on `ALERT_WEBHOOK_URL` (Sprint 10, `atlas/alerting.py`) fires on
  every single failed forward - no debouncing, since these are rare at this strategy's
  trade volume. Also visible via `GET /api/v1/status`'s `pickmytrade.last_error` field,
  and in the structured logs (`event_type: "trade.entry.forward_failed"`).
- **What it means:** the trade was received and stored (it's in `GET /api/v1/trades`),
  but the order was **not** relayed to your broker. This is a missed trade, not a
  data-loss incident.
- **Immediate action:** check PickMyTrade's own status/dashboard for an outage. If
  `PICKMYTRADE_WEBHOOK_URL` itself might have changed or expired, verify it against
  PickMyTrade's current webhook URL for your account. There is no automatic retry
  (`atlas/services/pickmytrade.py` is deliberately a single attempt, no retry - see
  its module docstring) - a missed trade during an outage stays missed unless you
  manually place the order yourself once you notice.
- **If `RISK_ENFORCEMENT=true`:** also check whether this was actually a kill-switch
  block, not a PickMyTrade outage - the `pmt_error` field distinguishes them
  (`"blocked by risk engine: ..."` vs an actual HTTP/connection error). A block is
  working as intended, not an incident.

### Sustained Claude failures
- **Signal:** an alert fires once the consecutive-failure count crosses
  `CLAUDE_FAILURE_ALERT_THRESHOLD` (default 3), across entry scoring/post-trade
  review/reports combined (`atlas/alerting.py::ClaudeFailureTracker`) - not on every
  single failure, since one-off Claude hiccups are expected and already tolerated.
  A second alert fires on recovery.
- **What it means:** AI commentary (entry scores, reviews, reports) is degraded or
  absent. **Order execution is completely unaffected** - this is true by construction,
  not just in practice (see `atlas/ai.py`'s module docstring: AI is always scheduled as
  a background task, never on the response-critical path).
- **Immediate action:** check Anthropic's status page for a platform-wide outage.
  Check `ANTHROPIC_API_KEY` hasn't expired/been rotated. No action is required to keep
  trading running normally - this is a "fix when convenient," not a "drop everything."

### Database connection issues
- **Signal:** `GET /api/v1/health` returns `503` with `database: "error: ..."`.
  Railway's own health-check-driven restarts should already be attempting to recover
  automatically if this is transient.
- **Immediate action:** check Railway's Postgres service status directly (separate
  from the `atlas.main:app` service). If the database itself is down, nothing in
  `atlas/` can route around that - the webhook will fail every entry until it's back
  (each failure is visible as a `500` webhook response, not silently swallowed - see
  `atlas/api/v1/webhook.py`'s outermost `except Exception` handler).
- **If this persists:** this is the scenario the backup/PITR checklist
  (`docs/sprint10/postgres-backup-checklist.md`) exists for - don't reach for a
  restore unless the instance is actually unrecoverable, but know where that doc is
  before you need it.

### A bad deploy itself (crash-loop, obviously broken behavior)
- Roll back immediately (see Rollback above) - don't debug in production while real
  webhook traffic is potentially being mishandled.
- `Settings.validate_for_startup()` crash-loops are the most likely "deploy looks
  broken" cause and are the fastest to diagnose (the error names the missing
  variable) - check those logs before assuming a code bug.
