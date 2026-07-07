# Sprint 3 - Deployment Checklist

Same situation as Sprint 2: this sprint's backend half (`/api/v1/stream`) ships inside the
same `atlas.main:app` process gated by the Sprint 1 Postgres cutover
(`docs/sprint1/deployment-checklist.md`). Nothing here is independently deployable ahead of
that gate. **Per your instruction, nothing in this sprint has been pushed or deployed.**

## Backend (Railway) - additive, no new environment variables
1. Complete the Sprint 1 gate first if you haven't already.
2. Run the test suite locally before pushing:
   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -v
   ```
   Expect **40 passed** (31 from Sprints 1-2 plus this sprint's `test_stream.py` and the two
   new `EventBus.unsubscribe` tests in `test_event_bus.py`).
3. Push. Railway redeploys `atlas.main:app` with `/api/v1/stream` included automatically.
4. **Verify SSE actually reaches the client through Railway's edge/proxy** - this is the one
   real risk specific to this sprint. Some reverse proxies buffer streaming responses by
   default, which would make the connection "work" (200 OK) but never deliver events until
   the connection closes. The route already sets `X-Accel-Buffering: no` and
   `Cache-Control: no-cache` to discourage this, but confirm after deploying:
   ```bash
   curl -N https://<your-app>.up.railway.app/api/v1/stream
   ```
   You should see `event: connected` immediately, then a `: keepalive` line within 15
   seconds even with no trade activity. If the connection hangs with no output at all for
   15+ seconds, something in the network path is buffering - investigate before relying on
   this in production (the frontend will silently fall back to polling either way, so this
   is a performance/latency issue, not a correctness one).

## Frontend (Vercel) - no new environment variables
The frontend connects to `${NEXT_PUBLIC_API_BASE_URL}/api/v1/stream` using the same base URL
already configured in Sprint 2. Nothing additional to set.
1. `npm run lint && npm run build` locally before deploying - both clean as of this sprint.
2. After deploying, open the site and check the header: "● live" means SSE connected
   through to the deployed backend; "○ polling" means it didn't (check the browser console
   for a CORS or connection error, and re-check step 4 above on the backend side).

## Local development (unchanged process, now with live updates)
```bash
# Terminal 1
cd live && python scripts/dev_seed_server.py

# Terminal 2
cd frontend && npm run dev
```
Open `http://localhost:3000` - header should show "● live" within a second or two. To see a
live update happen, POST a new entry while the dashboard is open:
```bash
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" -d '{
  "type":"entry","correlation_id":"manual-test-1","symbol":"MNQU6","strategy_name":"TEST",
  "data":"BUY","quantity":1,"price":21600,"tp":21650,"sl":21580,"token":"x",
  "direction":"long","setup_tag":"BRK","entry_price":21600,"atr":30,
  "ema_distance_atr":0.4,"regime_slope_pct":1.0,"sweep_age_bars":2,"session":"NY",
  "signal_time":"2026-07-07T18:00:00Z"
}'
```
Current Position, Trade History, Connection Status, and Today's stats should all update
within roughly a second, with no page refresh.

## What was and wasn't verified in this session
- Backend: all 40 pytest tests passing, including 7 new SSE-specific tests
  (`tests/test_stream.py`) that exercise connect/publish/keepalive/disconnect/unsubscribe/
  queue-overflow behavior directly against the generator.
- Frontend: `npm run lint` and `npm run build` clean.
- End-to-end, against `scripts/dev_seed_server.py`: SSE connects (header shows "● live"),
  a real webhook POST triggers an instant UI update across all four live-updating
  surfaces (screenshotted), stopping the backend flips the indicator to "○ polling"
  (screenshotted), and restarting it reconnects automatically back to "● live" (confirmed via
  DOM inspection after the preview screenshot tool hit a transient timeout).
- **Not verified**: SSE through a real Railway deployment/proxy (see step 4 above - this is
  the one genuinely new risk this sprint introduces and must be checked after the Sprint 1
  gate clears and this is actually deployed), or on Vercel.
