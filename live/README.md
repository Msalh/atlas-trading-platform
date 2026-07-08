# Atlas AI Trading Platform - backend

A FastAPI service that sits between TradingView and PickMyTrade: it receives every entry,
price update, and exit from the Pine script, stores the full lifecycle of each trade in
Postgres, asks Claude for a quick read on entries, and forwards the order-placement fields
to PickMyTrade.

As of Sprint 1, this is a modular FastAPI application (`atlas/`) backed by PostgreSQL, with a
repository layer, an in-process event bus, and a versioned API - see
[`../docs/sprint1/`](../docs/sprint1/) for the full architecture writeup. The external webhook
contract is unchanged from the original single-file version.

As of Sprint 2, there's a real frontend at [`../frontend/`](../frontend/) (Next.js) talking
to a set of new read-only endpoints added here - see [`../docs/sprint2/`](../docs/sprint2/).

As of Sprint 3, `/api/v1/stream` pushes Server-Sent Events so the frontend updates live
instead of only polling - see [`../docs/sprint3/`](../docs/sprint3/).

As of Sprint 4, `/api/v1/risk` exposes account balance, daily loss, trailing drawdown,
exposure, and a kill switch status - see [`../docs/sprint4/`](../docs/sprint4/) (display-only
at the time; see Sprint 9 below for enforcement).

As of Sprint 5, `/api/v1/analytics/*` exposes equity curve, drawdown, win rate, profit
factor, expectancy, average R, and session/setup/day-of-week breakdowns, computed over
closed trades - see [`../docs/sprint5/`](../docs/sprint5/).

As of Sprint 6, `/api/v1/ai/*` exposes the AI Copilot: live entry scores, post-trade
reviews, and on-demand daily/weekly reports, all stored in a real `ai_notes` table (one
row per AI pass) and run strictly as background tasks - see
[`../docs/sprint6/`](../docs/sprint6/). AI never blocks or affects order execution.

As of Sprint 7, entry scoring is structured-first: `atlas/intelligence.py` computes a
confidence score, expected R, and historical win rate from similar past trades
deterministically, *before* Claude is ever called - Claude only explains the numbers, never
invents its own. See [`../docs/sprint7/`](../docs/sprint7/) and `GET
/api/v1/ai/intelligence/{correlation_id}`.

As of Sprint 9 (security hardening, following Sprint 8's pre-production engineering audit -
see [`../docs/sprint9/`](../docs/sprint9/)): every endpoint except `/webhook` and `/health`
requires a shared API key; the webhook payload is schema-validated; the webhook secret is
never persisted; the kill switch can now actually block PickMyTrade forwarding behind
`RISK_ENFORCEMENT=true`; the legacy HTML dashboard is removed. The app refuses to start in
production without `WEBHOOK_SECRET`/`API_KEY` set.

## Event types (all POSTed to `/webhook`, distinguished by `"type"`)
- **`entry`** - a new signal fired. Forwarded to PickMyTrade first (order relay never waits
  on AI), then stored, then AI entry scoring runs as a background task (`atlas/ai.py`).
  Idempotent and concurrency-safe: a duplicate delivery of the same `correlation_id` is
  never re-forwarded (see `atlas/repositories/postgres.py::claim_and_forward`).
- **`price_update`** - periodic update for an open position (current price, unrealized P&L).
  Matched to its trade by `correlation_id`. Never forwarded anywhere.
- **`exit`** - the position closed (win or loss). Matched by `correlation_id`, updates the
  trade's final status. Never forwarded - PickMyTrade already executes its own bracket exit
  independently once it has the entry order. An AI post-trade review also runs as a
  background task after this.

`correlation_id` is the entry bar's timestamp (unique per trade, since only one position is
open at a time).

Also mounted at `/api/v1/webhook`, `/api/v1/health` - the versioned surface new integrations
should use. `/webhook` and `/health` remain unversioned and permanent, since that's what the
existing TradingView alert already points at. (The legacy `/` HTML dashboard was removed in
Sprint 9 - see the Sprint 9 note above.)

## Response codes on POST /webhook
All in the 2xx range, so TradingView never interprets a partial failure as a delivery
failure and retries it (which would risk a duplicate order on top of the original problem):
- **200** - fully normal (entry forwarded OK, or a price_update/exit applied OK)
- **207** - entry was stored, but the PickMyTrade forward failed or is unconfigured - check
  `pmt_error`. Deliberately not hidden as a plain 200.
- **208** - duplicate entry - this `correlation_id` was already forwarded previously,
  nothing was re-sent to PickMyTrade, the existing record is untouched.

## Layout
```
atlas/                  application package
  main.py                FastAPI app factory, lifespan, router mounting, auth/rate-limit/
                         security-header wiring (Sprint 9)
  config.py               all environment variable reads live here, plus
                         Settings.validate_for_startup() (Sprint 9)
  db.py                    Postgres connection pool + migration trigger
  events/                  EventBus, event type names, built-in subscribers
  repositories/            TradeRepository interface + Postgres/in-memory implementations
  services/                PickMyTrade relay, raw Claude API access + AI Copilot prompt builders
  api/security.py          shared API key dependency (Sprint 9)
  api/v1/                  webhook, health, trades, status, stats, stream, risk, analytics, ai
                         routers, plus webhook_models.py (Pydantic payload schema, Sprint 9)
  rate_limit.py            slowapi Limiter instance (Sprint 9)
  status.py                in-process "who have we heard from recently" tracker (Sprint 2)
  risk.py                  pure account risk computation (Sprint 4) - see its module docstring
  intelligence.py          pure historical similarity/confidence computation (Sprint 7)
  analytics.py             pure trade analytics computation (Sprint 5) - see its module docstring
  ai.py                    AI Copilot background-task orchestration (Sprint 6/7) - see its module docstring
migrations/              plain-SQL schema migrations + runner
scripts/                 one-time SQLite -> Postgres data migration, dev seed server (Sprint 2) -
                         intentionally unauthenticated, local-only, never calls
                         validate_for_startup()
tests/                   unit tests (in-memory repository) + tests/integration (real Postgres)
../docs/sprint1/            architecture decisions, schema, API contracts, deploy/rollback plans
../docs/sprint2/            Sprint 2 addendum: new endpoints, frontend deploy checklist
../docs/sprint3/            Sprint 3 addendum: SSE endpoint, deploy checklist
../docs/sprint4/            Sprint 4 addendum: risk endpoint, deploy checklist
../docs/sprint5/            Sprint 5 addendum: analytics endpoints, deploy checklist
../docs/sprint6/            Sprint 6 addendum: AI Copilot endpoints, deploy checklist
../docs/sprint7/            Sprint 7 addendum: AI intelligence engine, deploy checklist
../docs/sprint9/            Sprint 9: security hardening design, deploy checklist, security notes
../docs/monorepo-proposal.md   monorepo consolidation proposal - approved and executed (local commit
                             only, not yet pushed - see the repo's own root commit message)
```

## Environment variables
See [`.env.example`](.env.example) for the full list with explanations. The required ones:
- `DATABASE_URL` - Postgres connection string. The app refuses to start without it.
- `ANTHROPIC_API_KEY` - from https://console.anthropic.com/settings/keys
- `WEBHOOK_SECRET` - a password you make up; must match the Pine script's `webhookSecret` input.
  As of Sprint 9, the app refuses to start in production (the default) without this set.
- `API_KEY` - a second, separate shared secret (Sprint 9) required on every non-webhook,
  non-health endpoint (`Authorization: Bearer <API_KEY>`, or `?api_key=` for `/api/v1/stream`
  specifically - browsers' EventSource can't set custom headers). Also required to start in
  production.
- `PICKMYTRADE_WEBHOOK_URL` - if unset, entries are still stored/analyzed, just not forwarded.
- `RISK_ENFORCEMENT` (Sprint 9) - `true`/`false`, default `false`. When `true`, requires all
  four `ACCOUNT_*` variables also be set (see below) or the app refuses to start.
- `ENVIRONMENT` - `production` (default) or `development`. Only `development` tolerates a
  missing `WEBHOOK_SECRET`/`API_KEY`, for local testing only.

## Deploy (Railway)
See [`../docs/sprint1/deployment-checklist.md`](../docs/sprint1/deployment-checklist.md) for the
original ordered cutover checklist (provision Postgres, migrate data, verify, then deploy), and
[`../docs/sprint9/deployment-checklist.md`](../docs/sprint9/deployment-checklist.md) for what
changed since (auth, rate limiting, kill switch enforcement). The short version once Postgres
is provisioned and `DATABASE_URL`/`WEBHOOK_SECRET`/`API_KEY` are set: Railway detects
`Procfile` and runs `uvicorn atlas.main:app --host 0.0.0.0 --port $PORT` automatically.

## Point TradingView at it
Unchanged from before: Notifications tab -> Webhook URL -> `https://your-app.up.railway.app/webhook`,
message left as the default `{{strategy.order.alert_message}}`. Nothing on the TradingView side
needs to change for this sprint.

## Run tests locally
```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
This runs the full suite (152 tests) against an in-memory repository - no database needed.
Integration tests against a real Postgres (`tests/integration/`) are skipped automatically
unless `TEST_DATABASE_URL` is set; see the deployment checklist for how to run those before
cutover.

## Notes / limitations
- As of Sprint 9, every endpoint except `/webhook` (its own shared-secret scheme) and
  `/health` (deliberately public) requires the `API_KEY` bearer token - see
  `../docs/sprint9/security-notes.md` for the full design and its remaining residual risks
  (this is a single shared key for a single-user tool, not per-user auth).
- Real-time updates are push (SSE, `/api/v1/stream`) with polling kept as a safety net, not
  the primary path - see `../docs/sprint3/architecture-decisions.md`. `/api/v1/stream`
  requires `API_KEY` like everything else, passed as `?api_key=` since browsers' EventSource
  can't set custom headers - and still has no replay/delivery guarantee by design (see
  `../docs/sprint3/api-contracts-addendum.md`).
- EventBus/SystemStatus/SSE all assume a single backend process (documented in
  `atlas/events/bus.py`) - a real horizontal-scaling constraint, not addressed this sprint.
