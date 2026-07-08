# Sprint 7 - Deployment Checklist

Same situation as every sprint since Sprint 2: ships inside `atlas.main:app`, gated by the
Sprint 1 Postgres cutover. **Nothing in this sprint has been pushed or deployed**, per your
instruction - local commit(s) only, no remote configured, nothing pushed.

## Backend (Railway)
1. Complete the Sprint 1 gate first if you haven't already - this sprint adds a new
   migration (`migrations/0004_ai_intelligence_fields.sql`), applied automatically on
   startup the same way `0001`-`0003` were. It only adds four nullable columns to
   `ai_notes` (`expected_r`, `historical_win_rate_pct`, `similar_trade_count`,
   `factors_json`) - no data migration needed, existing rows just read back with those
   columns `NULL`.
2. No new environment variables - entry intelligence reuses the existing
   `ANTHROPIC_API_KEY`/`CLAUDE_MODEL` and `ACCOUNT_POINT_VALUE` (already used by Sprint 4's
   risk engine and Sprint 5's analytics) for the R-multiple calculation.
3. Run the test suite locally before pushing:
   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -v
   ```
   Expect **106 passed** (91 from Sprints 1-6, net +15: 14 new in `test_intelligence.py`,
   3 new in `test_ai_api.py` for the intelligence endpoint, and `test_ai.py`'s
   `parse_entry_score`/old `run_entry_score` tests replaced by 4 tests matching the new
   structured-first flow - see architecture-decisions.md #1. `test_webhook.py`,
   `test_status_api.py`, and `test_trades_api.py` were also updated: several tests now
   seed historical similar trades first so `run_entry_score` actually exercises the
   Claude-call path instead of the zero-history shortcut, and one assertion was corrected
   to reflect that a Claude failure no longer nulls out the score - see
   architecture-decisions.md #5).
4. Push. Railway redeploys with `GET /api/v1/ai/intelligence/{correlation_id}` included and
   the new migration applied.
5. Verify: post a few real entries with the same `direction`/`setup_tag` via TradingView (or
   curl) so history accumulates, then
   `curl https://<your-app>.up.railway.app/api/v1/ai/intelligence/<correlation_id>` against
   the most recent one - confirm `similar_trade_count` and the computed numbers look right,
   and `curl .../api/v1/ai/notes?note_type=entry_score&limit=1` to confirm the same numbers
   were persisted at entry time.

## Frontend (Vercel)
No new environment variables.
1. `npm run lint && npm run build` locally before deploying - both clean as of this sprint.
2. After deploying, open a trade's detail page (`/trades/{id}`) and confirm the entry_score
   timeline entry shows the score, confidence label, similar-trade count/win-rate/expected-R
   line, and the factor chips (green = favorable, red = unfavorable, gray = inconclusive).
   Confirm the Current Position card's badge shows the new confidence labels (`High
   Confidence` / `Moderate Confidence` / `Low Confidence` / `Insufficient History`) rather
   than Sprint 6's old alignment labels.

## Local development
```bash
# Terminal 1
cd live && python scripts/dev_seed_server.py

# Terminal 2
cd frontend && npm run dev
```
Seed data now calls the real `compute_intelligence_snapshot()` for every entry_score note
(see `scripts/dev_seed_server.py::_seed_intelligence_note`) instead of hand-typed
score/label values - the numbers you see locally (score, confidence label, expected R,
historical win rate, factors) are genuinely computed from the seeded historical trades, not
fabricated for the demo. Historical trades are seeded first specifically so the three
example trades (`seed-open-1`, `seed-won-1`, `seed-lost-1`) have real history to compute
against; `seed-lost-1` still demonstrates the "Claude configuration error" case, but now
alongside a real computed score (per architecture-decisions.md #5) rather than a null one.

## What was and wasn't verified in this session
- Backend: all 106 pytest tests passing, including `atlas/intelligence.py` unit tests
  (similarity filtering/ranking, factor favorability, the confidence rubric's threshold
  boundaries, zero-history and thin-sample edge cases), updated `atlas/ai.py` orchestration
  tests (Claude skipped entirely at zero history, Claude failure leaves the structured score
  intact), and the new `GET /ai/intelligence/{correlation_id}` endpoint tests (404 for an
  unknown trade, insufficient-history response shape, confirms the endpoint never calls
  Claude or persists anything).
- Frontend: `npx tsc --noEmit`, `npm run lint`, and `npm run build` all clean.
- End-to-end, against `scripts/dev_seed_server.py` via the preview tools: the Dashboard's
  Current Position card showing a real computed confidence badge ("AI 6/10 · Moderate
  Confidence"), a trade detail page's timeline showing the full entry_score line (score,
  label, similar-trade stats, narrative, and color-coded factor chips), the `/ai` page's
  AI Notes Timeline showing several entry_score notes with genuinely different computed
  scores (2, 5, 6, 7, 8) and labels including "Insufficient History" alongside a real
  numeric score, and a direct `fetch()` against `GET /api/v1/ai/intelligence/seed-open-1`
  from the browser console confirming the on-demand endpoint returns the same numbers as
  the persisted note. Full network log reviewed - all requests 200 OK aside from a handful
  of transient connection-refused entries during a deliberate backend restart mid-session
  (not a bug).
- **Not verified**: against a real Postgres deployment, against a real Anthropic API call
  (no `ANTHROPIC_API_KEY` in this sandbox - every AI code path was exercised through the
  same graceful "not configured" fallback verified since Sprint 0, or through mocked
  responses in tests), or on Vercel/Railway.
