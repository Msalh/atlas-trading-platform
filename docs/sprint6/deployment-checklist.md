# Sprint 6 - Deployment Checklist

Same situation as every sprint since Sprint 2: ships inside `atlas.main:app`, gated by the
Sprint 1 Postgres cutover. **Nothing in this sprint has been pushed or deployed**, per your
instruction - this also applies to the monorepo consolidation itself (local commit only, no
remote configured, nothing pushed - see the approval message before this sprint).

## Backend (Railway)
1. Complete the Sprint 1 gate first if you haven't already - this sprint adds a new
   migration (`migrations/0003_ai_notes.sql`), applied automatically on startup the same
   way `0001_init.sql`/`0002_add_quantity.sql` were.
2. No new environment variables - AI Copilot reuses the existing `ANTHROPIC_API_KEY` and
   `CLAUDE_MODEL`. If `ANTHROPIC_API_KEY` isn't set, entry scoring/reviews/reports all
   still run (as background tasks, same as before) and record a clear
   `"ANTHROPIC_API_KEY not configured"` error on each `ai_notes` row instead of silently
   doing nothing.
3. Run the test suite locally before pushing:
   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -v
   ```
   Expect **91 passed** (68 from Sprints 1-5 plus 23 new: 10 in `test_ai.py`, 7 in
   `test_ai_api.py`, 3 new `ai_notes` tests in `test_repositories.py`, 3 new/updated
   post-trade-review tests in `test_webhook.py`, plus the pre-existing suite's AI mock
   patch targets updated to match - see architecture-decisions.md #1-3 for why those moved).
4. Push. Railway redeploys with `/api/v1/ai/*` included and the new migration applied.
5. Verify: post a real entry via TradingView (or curl), then
   `curl https://<your-app>.up.railway.app/api/v1/ai/notes` - confirm a real entry_score
   note appears within a few seconds.

## Frontend (Vercel)
No new environment variables.
1. `npm run lint && npm run build` locally before deploying - both clean as of this sprint.
2. After deploying, open `/ai` and confirm the Reports panel's "Generate daily"/"Generate
   weekly" buttons work against the real backend, and that a real trade's detail page
   (`/trades/{id}`) shows its entry score / post-trade review in the timeline once
   generated.

## Local development
```bash
# Terminal 1
cd live && python scripts/dev_seed_server.py

# Terminal 2
cd frontend && npm run dev
```
The seed data now includes entry scores and post-trade reviews on a subset of the
historical trades, plus one seeded daily and weekly report, so `/ai` has real content
immediately without needing to trigger anything. To see the live flow end-to-end (not
just seeded data), POST a real entry then exit while `/ai` is open - watch the entry score
appear within moments (background task, no page refresh needed), then the post-trade
review after the exit.

## What was and wasn't verified in this session
- Backend: all 91 pytest tests passing, including entry-score parsing edge cases
  (well-formed, out-of-range, fully malformed Claude responses), background-task
  orchestration tests (Claude failure/exception never raises, unknown-trade review is a
  no-op, report date-window filtering), and endpoint-wiring tests (202-immediately
  contract, invalid period/note_type rejection).
- Frontend: `npm run lint` and `npm run build` clean.
- End-to-end, against `scripts/dev_seed_server.py`: screenshotted the `/ai` page (Reports
  panel with real seeded daily/weekly reports, AI Notes Timeline with entry scores and
  post-trade reviews), a trade detail page showing the full real timeline in order (entry
  received → forwarded → AI entry score → position closed → post-trade review), and the
  Current Position card's live entry-score badge on the Dashboard - all confirmed against
  real (seeded) data flowing through the real REST endpoints, with SSE live-update wiring
  confirmed via the network log (no manual refresh needed to see the score badge update).
  No console errors, no failed requests other than a harmless backend-not-yet-ready race
  on the very first page load before the dev server finished starting.
- **Not verified**: against a real Postgres deployment, against a real Anthropic API call
  (no `ANTHROPIC_API_KEY` in this sandbox - every AI code path was exercised through the
  same graceful "not configured" fallback that's been verified since Sprint 0, or through
  mocked responses in tests), or on Vercel/Railway.
