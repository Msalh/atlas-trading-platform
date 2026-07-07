# Sprint 5 - Deployment Checklist

Same situation as every sprint since Sprint 2: ships inside `atlas.main:app`, gated by the
Sprint 1 Postgres cutover. **Nothing in this sprint has been pushed or deployed**, per your
instruction.

## Backend (Railway)
1. Complete the Sprint 1 gate first if you haven't already.
2. No new environment variables - analytics reuses Sprint 4's `ACCOUNT_STARTING_BALANCE`
   and `ACCOUNT_POINT_VALUE`. If those aren't set, the equity curve still computes (it just
   starts from the same placeholder default `/api/v1/risk` would warn you about).
3. Run the test suite locally before pushing:
   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -v
   ```
   Expect **68 passed** (54 from Sprints 1-4 plus 10 new `test_analytics.py` + 4 new
   `test_analytics_api.py`).
4. Push. Railway redeploys with the three new `/api/v1/analytics/*` endpoints included.
5. Verify: `curl https://<your-app>.up.railway.app/api/v1/analytics/summary` - once you
   have real closed trades in production, confirm `total_trades` matches what you expect.

## Frontend (Vercel)
No new environment variables.
1. `npm run lint && npm run build` locally before deploying - both clean as of this sprint
   (`recharts` added as a new dependency - already in `package-lock.json`).
2. After deploying, open `/analytics` and confirm the equity curve/breakdown charts render
   with your real trade history (they'll be sparse/empty until enough real trades have
   closed - that's correct, not a bug, see the "no closed trades yet" empty states).

## Local development
```bash
# Terminal 1
cd live && python scripts/dev_seed_server.py

# Terminal 2
cd frontend && npm run dev
```
The seed data now includes 13 additional historical closed trades (on top of the 1 open /
1 won / 1 lost from earlier sprints) spanning multiple sessions, setups, and days
specifically so `/analytics` has enough shape to evaluate - see
`scripts/dev_seed_server.py::_seed_analytics_history`. Not meant to resemble real
performance.

## What was and wasn't verified in this session
- Backend: all 68 pytest tests passing, including 10 pure-function tests for the analytics
  math itself (summary ratios, equity/drawdown curve tracking, breakdown grouping and
  weekday ordering) and 4 endpoint-wiring tests.
- Frontend: `npm run lint` and `npm run build` clean (one real TypeScript error caught and
  fixed during this sprint - Recharts' `Tooltip formatter` prop expects a broader value
  type than plain `number`; fixed with an explicit `Number(value)` conversion in all three
  chart components).
- End-to-end, against `scripts/dev_seed_server.py`: screenshotted `/analytics` on both
  desktop and mobile viewports - summary cards, equity curve, drawdown chart, and all
  three breakdown charts all rendered correctly with real seeded data flowing through;
  confirmed the Dashboard and Account pages still work unchanged (no regressions from
  shared files touched this sprint - `live-updates.tsx`, `layout.tsx`, `lib/api.ts`); no
  console errors, no failed network requests.
- **Not verified**: against a real Postgres deployment, against real closed-trade history,
  or on Vercel.
- **Known minor limitation, not fixed this sprint**: the header nav (`Dashboard | Account |
  Analytics`) can visually crowd/wrap at narrow mobile widths - functional but not polished;
  not a regression specific to this sprint (the same constraint existed with fewer nav
  items since Sprint 4), and no mobile hamburger menu exists yet. Worth a small follow-up
  if mobile use becomes a priority.
