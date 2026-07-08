# Sprint 9 - Deployment Checklist

**Nothing in this sprint has been pushed or deployed** - per your instruction, this
work stays local and uncommitted until you approve it.

## Backend (Railway)

1. No new migration this sprint - the `trades`/`ai_notes` schema is unchanged.
2. **New required environment variables** (the app will refuse to start without
   these in production - see `atlas/config.py::Settings.validate_for_startup`):
   - `WEBHOOK_SECRET` - already required in practice since Sprint 1; now actually
     enforced at startup instead of silently tolerated when blank.
   - `API_KEY` - **new**. A separate shared secret from `WEBHOOK_SECRET`. Generate a
     long random value (e.g. `openssl rand -hex 32`) and set it distinctly from the
     webhook secret - they protect different things and should not be reused.
3. **New optional environment variables:**
   - `ENVIRONMENT` - defaults to `production`. Only set to `development` for local
     testing; never for a real deployment (this is what allows a blank
     `WEBHOOK_SECRET`/`API_KEY`, which you do not want in production).
   - `RISK_ENFORCEMENT` - defaults to `false`. See security-notes.md's Remaining Risks
     #1 before deciding whether to enable this - it requires all four `ACCOUNT_*`
     variables to also be set, or the app refuses to start.
4. Install the two new dependencies (already added to `requirements.txt`):
   ```
   pydantic>=2.0.0
   slowapi>=0.1.9
   ```
5. Run the test suite locally before pushing:
   ```bash
   pip install -r requirements-dev.txt
   pytest tests/ -v
   ```
   Expect **152 passed** (106 from Sprints 1-7, +46 new this sprint across five new
   files - `test_auth.py`, `test_config_validation.py`, `test_webhook_validation.py`,
   `test_risk_enforcement.py`, `test_rate_limiting.py` - plus one secret-persistence
   test added to `test_webhook.py`; one existing test updated from a 400 to a 422
   expectation, see architecture-decisions.md #6).
6. Push. Railway redeploys. **The app will not start** unless `WEBHOOK_SECRET` and
   `API_KEY` are both set in Railway's environment variables - if you see a crash-loop
   after this deploy, check those first.
7. Verify:
   ```bash
   # Should be 401 without a key
   curl -i https://<your-app>.up.railway.app/api/v1/status

   # Should be 200 with the right key
   curl -i https://<your-app>.up.railway.app/api/v1/status \
     -H "Authorization: Bearer <your API_KEY>"

   # Should still be 200 with no key at all (deliberately public)
   curl -i https://<your-app>.up.railway.app/api/v1/health

   # Should be gone entirely (404) - the legacy dashboard was removed
   curl -i https://<your-app>.up.railway.app/
   ```
8. Confirm `/docs`, `/redoc`, `/openapi.json` all 404 (disabled in production).

## Frontend (Vercel)

1. **New environment variable:** `NEXT_PUBLIC_API_KEY` - must exactly match the
   backend's `API_KEY`. Being a `NEXT_PUBLIC_*` variable, this is bundled into
   client-side JavaScript and is not a secret from anyone who views page source (see
   security-notes.md's Remaining Risks #2) - it protects against casual/automated
   discovery of a public URL, not a determined attacker who already has the deployed
   frontend's bundle.
2. `npm run lint && npm run build` locally before deploying - both clean as of this
   sprint (the production build also exercises `next.config.ts`'s new CSP headers
   config, so a broken CSP policy would fail the build step, not just runtime).
3. After deploying, open the browser console on every page and confirm there are no
   CSP violation errors - see security-notes.md's Remaining Risks #4. This is the one
   piece of this sprint that genuinely could not be fully verified without a real
   deployment.
4. Confirm the dashboard still loads and updates live (SSE) against the real backend -
   the `?api_key=` query-parameter fallback for `/api/v1/stream` specifically needs a
   real browser `EventSource` connection to verify, not just a curl check.

## Local development

```bash
# Terminal 1 - unaffected by this sprint; still zero-config, no auth required
cd live && python scripts/dev_seed_server.py

# Terminal 2 - unaffected; NEXT_PUBLIC_API_KEY should stay unset for this workflow
cd frontend && npm run dev
```
`scripts/dev_seed_server.py` deliberately never calls `Settings.validate_for_startup()`
and its routers are not behind `require_api_key` - it remains the same zero-config
local harness it always was. Leave `NEXT_PUBLIC_API_KEY` unset in `frontend/.env.local`
for this workflow; the frontend simply won't send an `Authorization` header, which the
dev server doesn't check anyway.

To test the *real* `atlas.main:app` locally (not the dev harness) against a real or
local Postgres:
```bash
export DATABASE_URL=postgres://...
export WEBHOOK_SECRET=local-test-secret
export API_KEY=local-test-api-key
export ENVIRONMENT=development   # or omit both secrets' requirement by setting this
uvicorn atlas.main:app --reload
```

## What was and wasn't verified in this session

- Backend: all 152 pytest tests passing, including 46 new Sprint 9 regression tests
  covering every objective in the sprint brief (startup validation, secret
  non-persistence, authentication, payload validation, kill-switch on/off, rate
  limiting). Directly verified via a real `TestClient` against `atlas.main:app` (not
  just the dev harness): security headers present on every response, `/docs` disabled
  in production, `/api/v1/trades` returns 401/401/200 for no-key/wrong-key/right-key,
  `/api/v1/health` stays public.
- Frontend: `npx tsc --noEmit`, `npm run lint`, and `npm run build` all clean,
  including the new `next.config.ts` headers configuration.
- End-to-end, against `scripts/dev_seed_server.py` via the preview tools: confirmed
  `GET /` now 404s (dashboard removed), confirmed the dashboard/timeline/AI pages all
  still render correctly against the (deliberately unauthenticated) dev harness with no
  console errors and no regressions from Sprints 1-7's functionality.
- **Not verified**: against a real Postgres deployment, a real Railway/Vercel
  deployment, a real `ANTHROPIC_API_KEY`, or a real `PICKMYTRADE_WEBHOOK_URL` (none
  available in this sandbox). The frontend's CSP has not been verified against a real
  production Next.js runtime - see security-notes.md's Remaining Risks #4.
