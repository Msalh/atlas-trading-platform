# Atlas AI Trading Platform - backend

A FastAPI service that sits between TradingView and PickMyTrade: it receives every entry,
price update, and exit from the Pine script, stores the full lifecycle of each trade in
Postgres, asks Claude for a quick read on entries, forwards the order-placement fields to
PickMyTrade, and serves a live-updating dashboard showing it all.

As of Sprint 1, this is a modular FastAPI application (`atlas/`) backed by PostgreSQL, with a
repository layer, an in-process event bus, and a versioned API - see
[`../docs/sprint1/`](../docs/sprint1/) for the full architecture writeup. The external webhook
contract is unchanged from the original single-file version.

As of Sprint 2, there's a real frontend at [`../frontend/`](../frontend/) (Next.js) talking
to a set of new read-only endpoints added here - see [`../docs/sprint2/`](../docs/sprint2/).

As of Sprint 3, `/api/v1/stream` pushes Server-Sent Events so the frontend updates live
instead of only polling - see [`../docs/sprint3/`](../docs/sprint3/).

As of Sprint 4, `/api/v1/risk` exposes account balance, daily loss, trailing drawdown,
exposure, and a **display-only** kill switch - see [`../docs/sprint4/`](../docs/sprint4/).
Nothing here blocks order execution or enforces anything yet.

As of Sprint 5, `/api/v1/analytics/*` exposes equity curve, drawdown, win rate, profit
factor, expectancy, average R, and session/setup/day-of-week breakdowns, computed over
closed trades - see [`../docs/sprint5/`](../docs/sprint5/).

## Event types (all POSTed to `/webhook`, distinguished by `"type"`)
- **`entry`** - a new signal fired. Forwarded to PickMyTrade first (order relay never waits
  on Claude), then stored, then sent to Claude for analysis as a background task.
  Idempotent and concurrency-safe: a duplicate delivery of the same `correlation_id` is
  never re-forwarded (see `atlas/repositories/postgres.py::claim_and_forward`).
- **`price_update`** - periodic update for an open position (current price, unrealized P&L).
  Matched to its trade by `correlation_id`. Never forwarded anywhere.
- **`exit`** - the position closed (win or loss). Matched by `correlation_id`, updates the
  trade's final status. Never forwarded - PickMyTrade already executes its own bracket exit
  independently once it has the entry order.

`correlation_id` is the entry bar's timestamp (unique per trade, since only one position is
open at a time).

Also mounted at `/api/v1/webhook`, `/api/v1/health` - the versioned surface new integrations
should use. `/webhook`, `/health`, `/` (dashboard) remain unversioned and permanent, since
that's what the existing TradingView alert already points at.

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
  main.py                FastAPI app factory, lifespan, router mounting
  config.py               all environment variable reads live here
  db.py                    Postgres connection pool + migration trigger
  events/                  EventBus, event type names, built-in subscribers
  repositories/            TradeRepository interface + Postgres/in-memory implementations
  services/                PickMyTrade relay, Claude commentary
  api/v1/                  webhook, health, dashboard, trades, status, stats, stream, risk, analytics routers
  status.py                in-process "who have we heard from recently" tracker (Sprint 2)
  risk.py                  pure account risk computation (Sprint 4) - see its module docstring
  analytics.py             pure trade analytics computation (Sprint 5) - see its module docstring
migrations/              plain-SQL schema migrations + runner
scripts/                 one-time SQLite -> Postgres data migration, dev seed server (Sprint 2)
tests/                   unit tests (in-memory repository) + tests/integration (real Postgres)
../docs/sprint1/            architecture decisions, schema, API contracts, deploy/rollback plans
../docs/sprint2/            Sprint 2 addendum: new endpoints, frontend deploy checklist
../docs/sprint3/            Sprint 3 addendum: SSE endpoint, deploy checklist
../docs/sprint4/            Sprint 4 addendum: risk endpoint, deploy checklist
../docs/sprint5/            Sprint 5 addendum: analytics endpoints, deploy checklist
../docs/monorepo-proposal.md   proposal for consolidating live/frontend/docs into one repo (not yet executed)
app.py, schema.sql       Sprint 0 version - kept, unused by the running app, as a rollback
                         reference until the Postgres cutover has been running cleanly for a
                         while (see ../docs/sprint1/rollback-plan.md)
```

## Environment variables
See [`.env.example`](.env.example) for the full list with explanations. The required ones:
- `DATABASE_URL` - Postgres connection string. The app refuses to start without it.
- `ANTHROPIC_API_KEY` - from https://console.anthropic.com/settings/keys
- `WEBHOOK_SECRET` - a password you make up; must match the Pine script's `webhookSecret` input
- `PICKMYTRADE_WEBHOOK_URL` - if unset, entries are still stored/analyzed, just not forwarded.

## Deploy (Railway)
See [`../docs/sprint1/deployment-checklist.md`](../docs/sprint1/deployment-checklist.md) for the
full ordered cutover checklist (provision Postgres, migrate data, verify, then deploy). The
short version once Postgres is provisioned and `DATABASE_URL` is set: Railway detects
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
This runs the full suite (68 tests) against an in-memory repository - no database needed.
Integration tests against a real Postgres (`tests/integration/`) are skipped automatically
unless `TEST_DATABASE_URL` is set; see the deployment checklist for how to run those before
cutover.

## Notes / limitations
- No authentication on the dashboard page itself (`/`) - anyone with the URL can view it.
  `WEBHOOK_SECRET` only protects `/webhook` from fake entries. The new `/api/v1/trades*`,
  `/api/v1/status`, `/api/v1/stats/today` endpoints are equally unauthenticated (read-only,
  no secrets in the response bodies) - revisit if that stops being true.
- The old auto-refreshing HTML page (`atlas/api/v1/dashboard.py`, still served at `/`) is
  unchanged from Sprint 0 and now superseded by the real frontend in `../frontend/` - kept
  only because nothing requires removing it yet.
- Real-time updates are now push (SSE, `/api/v1/stream`) with polling kept as a safety net,
  not the primary path - see `../docs/sprint3/architecture-decisions.md`. `/api/v1/stream`
  is unauthenticated like the rest of `/api/v1/*` and has no replay/delivery guarantee by
  design (see `../docs/sprint3/api-contracts-addendum.md`).
