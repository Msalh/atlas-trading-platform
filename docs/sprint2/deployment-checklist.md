# Sprint 2 - Deployment Checklist

Sprint 2 adds to the *same* `atlas` backend from Sprint 1 (new routers, CORS middleware, a
new in-process status tracker - no new tables, no changed webhook behavior) plus a brand
new, separately-deployed frontend. **The backend half of Sprint 2 ships as part of the same
Railway cutover gated in `docs/sprint1/deployment-checklist.md`** - it is not independently
deployable ahead of that, since it's the same `atlas.main:app` process that still refuses to
start without `DATABASE_URL`.

## Backend (Railway) - additive to the Sprint 1 checklist
1. Complete the Sprint 1 gate first (Postgres provisioned, data migrated, row counts
   verified, integration tests run) - see `docs/sprint1/deployment-checklist.md`. Nothing in
   Sprint 2 changes that gate.
2. Set a new environment variable on the Railway web service:
   - `FRONTEND_ORIGINS` - comma-separated list of origins allowed to call the API
     cross-origin. Set this to your deployed frontend's URL once you have it (e.g.
     `https://atlas-frontend.vercel.app`). Defaults to `http://localhost:3000` if unset,
     which is correct for local dev but wrong for production - **don't forget this one**, or
     the deployed frontend's browser requests will be blocked by CORS with no server-side
     error to notice.
3. Run the backend test suite locally before pushing (unchanged process from Sprint 1):
   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -v
   ```
   Expect **31 passed** (29 from Sprint 1 plus this sprint's `test_trades_api.py`,
   `test_status_api.py`, `test_stats_api.py`, `test_repositories.py`).
4. Push. Railway redeploys `atlas.main:app` with the new routers included automatically -
   no separate deploy step for the new endpoints.
5. Post-deploy: `curl https://<your-app>.up.railway.app/api/v1/status` should return `200`
   with `database.ok: true`.

## Frontend (new: Vercel)
1. `cd frontend && npm install` (already done in this session; `package-lock.json` is
   committed so this is reproducible).
2. Set the production environment variable in Vercel's project settings:
   - `NEXT_PUBLIC_API_BASE_URL` = your Railway backend's public URL (e.g.
     `https://your-app.up.railway.app`). This is baked into the client bundle at build time
     (it's a `NEXT_PUBLIC_` var), so it must be set in Vercel before the first production
     build, not just at runtime.
3. Import the `frontend/` directory as a new Vercel project (New Project -> import the
   `mnqu6-live-dashboard` repo -> set the root directory to `frontend`). Vercel auto-detects
   Next.js and needs no other configuration.
4. Deploy. Vercel gives you a `*.vercel.app` URL.
5. Go back to the Railway backend and set `FRONTEND_ORIGINS` to that exact URL (step 2 of
   the Backend section above), then redeploy the backend so CORS allows it.
6. Verify: open the Vercel URL, confirm the dashboard loads real data (not stuck on
   "Loading…"), check the browser console for CORS errors if it doesn't.

## Local development (no Railway/Vercel needed)
This is how this sprint's UI was actually built and visually verified in this session, since
there was no Postgres available in the dev sandbox:
```bash
# Terminal 1 - backend, in-memory + seeded, no Postgres required
cd live
python scripts/dev_seed_server.py

# Terminal 2 - frontend
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```
Open `http://localhost:3000`. To develop against the real Postgres-backed backend instead,
run `uvicorn atlas.main:app --reload` (needs a real `DATABASE_URL`) instead of the seed
script - the frontend doesn't know or care which one it's talking to.

## What was and wasn't verified in this session
- Backend: all 31 pytest tests run and passing (in-memory repository, no DB needed).
- Frontend: `npm run lint` clean, `npm run build` (production build + TypeScript check)
  clean, dev server started and visually verified via screenshots against
  `scripts/dev_seed_server.py` - dashboard, trade history filtering, trade detail/timeline,
  connection status, today's stats, mobile viewport.
- **Not verified**: the frontend against a real deployed Railway backend, or against real
  Postgres data, or on Vercel - none of that infrastructure exists yet (same gate as Sprint
  1). Do the "Frontend (new: Vercel)" steps above once the Sprint 1 Postgres cutover is live,
  then re-verify against the real thing before calling this production-ready.
