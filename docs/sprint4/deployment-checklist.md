# Sprint 4 - Deployment Checklist

Same situation as Sprints 2-3: ships inside `atlas.main:app`, gated by the Sprint 1 Postgres
cutover. **Nothing in this sprint has been pushed or deployed**, per your instruction.

## Backend (Railway)
1. Complete the Sprint 1 gate first if you haven't already - this sprint adds a new
   migration (`migrations/0002_add_quantity.sql`), which `atlas/db.py` applies
   automatically on startup the same way `0001_init.sql` was applied, no manual step needed.
2. **Set the account risk environment variables before trusting `/account` in production**:
   - `ACCOUNT_STARTING_BALANCE` - your real starting/current funded-account balance basis.
   - `ACCOUNT_DAILY_LOSS_LIMIT` - your prop firm's actual daily loss limit, in dollars.
   - `ACCOUNT_TRAILING_DRAWDOWN_LIMIT` - your actual trailing drawdown limit, in dollars.
   - `ACCOUNT_MAX_CONTRACTS` - your actual max position size.
   - `ACCOUNT_POINT_VALUE` - dollars per point per contract for the traded instrument
     (MNQ = `2.0`; change if you ever trade a different instrument through this system).

   Until all four of the first group are set, `/api/v1/risk` returns
   `account_configured: false` and the frontend shows a persistent warning banner - this is
   intentional (see architecture-decisions.md #2), not a bug to silence by setting fake
   values.
3. Run the test suite locally before pushing:
   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -v
   ```
   Expect **54 passed** (40 from Sprints 1-3 plus 10 new `test_risk.py` + 4 new
   `test_risk_api.py`).
4. Push. Railway redeploys with `/api/v1/risk` included and the new migration applied.
5. Verify: `curl https://<your-app>.up.railway.app/api/v1/risk` - confirm
   `account_configured: true` and the balance figures match what you expect.

## Frontend (Vercel)
No new environment variables - `/account` calls the same `NEXT_PUBLIC_API_BASE_URL` already
configured.
1. `npm run lint && npm run build` locally before deploying - both clean as of this sprint.
2. After deploying, open `/account` and confirm: no "placeholder defaults" warning (if you
   set the backend env vars in step 2 above), and the header's risk dot matches the page
   (green "risk ok" / red "risk limit").

## Local development
```bash
# Terminal 1
cd live && python scripts/dev_seed_server.py

# Terminal 2
cd frontend && npm run dev
```
The seed data intentionally includes an open position sized at 6 contracts against the
default `ACCOUNT_MAX_CONTRACTS=5`, so the "exceeds max" badge and both banner states
(unconfigured + kill switch, when you also force a large loss) are visible without extra
setup. To see the kill switch actually trigger:
```bash
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -d '{
  "type":"entry","correlation_id":"loss-test","symbol":"MNQU6","strategy_name":"TEST",
  "data":"SELL","quantity":2,"price":21500,"tp":21400,"sl":21550,"token":"x",
  "direction":"short","setup_tag":"BRK","entry_price":21500,"atr":30,
  "ema_distance_atr":0.4,"regime_slope_pct":1.0,"sweep_age_bars":2,"session":"NY",
  "signal_time":"2026-07-07T19:00:00Z"
}'
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -d '{
  "type":"exit","correlation_id":"loss-test","outcome":"LOSS",
  "exit_price":21620,"realized_pnl":-1500
}'
```
Then open `/account` - daily loss limit breach and the red kill-switch banner should both
show, live (via SSE), no refresh needed.

## What was and wasn't verified in this session
- Backend: all 54 pytest tests passing, including 10 pure-function tests for the risk math
  itself (balance/high-water-mark/drawdown/kill-switch/exposure across long, short, missing-
  quantity, and multi-day scenarios) and 4 endpoint-wiring tests.
- Frontend: `npm run lint` and `npm run build` clean.
- End-to-end, against `scripts/dev_seed_server.py`: screenshotted the Account page in both
  the "within limits, unconfigured" state and the "kill switch triggered + unconfigured"
  state (after forcing a real loss via curl) - **this caught a real bug** (the unconfigured
  banner was hiding the kill-switch banner instead of showing alongside it), which was fixed
  and re-verified in the same session, not left for later.
- **Not verified**: against a real Postgres deployment, or with real
  `ACCOUNT_*` values set (only the "unconfigured" default path was exercised end-to-end
  visually - the "configured" path is covered by `test_risk_api.py` but not screenshotted,
  since it requires setting env vars the dev seed server doesn't currently expose a quick
  toggle for).
