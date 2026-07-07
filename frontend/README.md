# Atlas frontend

Next.js (App Router, TypeScript, Tailwind, Recharts) UI for the Atlas AI Trading Platform,
added in Sprint 2. Talks to the `atlas` backend in `../live/` over REST (see
`../docs/sprint2/api-contracts-addendum.md`) plus, as of Sprint 3, a Server-Sent Events
stream (`../docs/sprint3/api-contracts-addendum.md`) for live updates - polling never stops,
it just backs off to a longer safety-net interval while SSE is connected (see
`../docs/sprint3/architecture-decisions.md`).

## Screens
- **Dashboard** (`/`) - Current Position, Trade History (filterable), Connection Status,
  Today's stats. Updates live when `/api/v1/stream` is connected (header shows
  "● live" / "○ polling").
- **Account** (`/account`, Sprint 4) - account balance, daily loss, trailing drawdown,
  current exposure/position sizing, unrealized risk, and a **display-only** kill switch
  banner. See `../docs/sprint4/api-contracts-addendum.md`. Nothing on this page blocks order
  execution or enforces anything.
- **Analytics** (`/analytics`, Sprint 5) - equity curve, drawdown chart, win rate, profit
  factor, expectancy, average R, average win/loss, and session/setup/day-of-week
  breakdowns, all computed over closed trades. See
  `../docs/sprint5/api-contracts-addendum.md`.
- **Trade Detail** (`/trades/[correlationId]`) - full trade fields + derived lifecycle
  timeline. Also live-updating.

The header shows two live indicators at all times: connection mode ("● live"/"○ polling")
and account risk ("risk ok"/"risk limit", linking to `/account`).

AI Copilot expansion, a replay engine, and broker/market-data integrations are explicitly
out of scope so far - see the backend's sprint docs for the full scope statements.

## Local development
```bash
cp .env.local.example .env.local
npm install
npm run dev
```
By default this points at `http://localhost:8000`. Run the backend either as:
- `python ../live/scripts/dev_seed_server.py` - in-memory, pre-seeded with a realistic
  spread of trades (one open position sized above the default max contracts, so the Account
  page's warning states are visible immediately; 13 additional closed trades across
  sessions/setups/days so `/analytics`'s charts have real shape), no database required.
  This is what every sprint so far was actually developed and visually verified against.
- `uvicorn atlas.main:app --reload` (from `../live/`) - the real backend, needs a real
  `DATABASE_URL` and, for the Account/Analytics pages to show real numbers, the `ACCOUNT_*`
  environment variables (see `../live/.env.example`).

## Checks
```bash
npm run lint
npm run build
```
Both are clean as of Sprint 5.

## Deploy
See `../docs/sprint5/deployment-checklist.md` (supersedes earlier sprints' for the current
process) - deploys to Vercel independently of the Railway backend, connected via the
`NEXT_PUBLIC_API_BASE_URL` environment variable. No new environment variables this sprint.

## Known minor limitation
The header nav can crowd/wrap at narrow mobile widths (no hamburger menu yet) - functional,
not polished. Not new to this sprint; worth a follow-up if mobile use becomes a priority.
