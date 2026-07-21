# UI v2 — Deployment Runbook

**Status**: Uncommitted, for review. This is an operator checklist for deploying the already-built UI v2 system - it does not perform any deployment itself, and nothing in it has been executed. It assumes and extends `docs/staging/deployment-checklist.md` (the base backend/frontend staging process - migrations, `WEBHOOK_SECRET`, PMT safety gates) rather than duplicating it; this document adds everything specific to UI v2 (the BFF proxy, `ATLAS_API_KEY`, research snapshots, the 6 new routes, CT/freshness behavior). If you haven't run the base checklist before, do that first - Steps 1-3 below assume a Railway project already exists (or is being created for the first time alongside it).

**Deployment architecture**: **Railway-only**. Both services run in the same Railway project:
- **Backend service** (Root Directory `live`) - the FastAPI/Atlas API.
- **Frontend service** (Root Directory `frontend`) - the Next.js UI v2 app, including its own server-side BFF proxy route.
- **PostgreSQL** - a Railway-managed plugin in the same project, auto-injecting `DATABASE_URL` into the backend service.

Vercel is not part of this deployment architecture. This does not change the application architecture, the BFF pattern, the API, Rule Engine, Setup Engine, Research Engine, UI behavior, the security model, or any production-hardening decision - it changes only which platform hosts the frontend process. See `docs/ui_v2/production-hardening-plan.md` for why this doesn't affect the BFF/CORS reasoning.

**What this document is not**: a record of a deployment that happened. No git remote is configured as of this writing, so nothing below has been executed. Section 9 is a template to fill in once it is.

---

## 1. Prerequisites

Confirm each of these exists before starting. None of them can be created by an assistant acting alone - they require you, a human with account access.

- [ ] **Git hosting/remote**: a GitHub (or equivalent) repository this project is pushed to. Railway deploys by watching a repo - it cannot deploy from an uncommitted local working tree. (`docs/staging/deployment-checklist.md` Step 0 covers creating and pushing to one if it doesn't exist yet.)
- [ ] **Railway access**: an account with permission to create/manage a project, two services, and a Postgres plugin. (You've indicated a Railway project already exists for the backend - the frontend is added as a second service in that same project, not a new project.)
- [ ] **Production Postgres**: Railway's own Postgres plugin in the same project (auto-provisions `DATABASE_URL`), the path this runbook assumes.
- [ ] **Production domain(s)**: each Railway service gets its own generated `*.up.railway.app` domain by default (or a custom domain per service, if configured). You need the backend's public domain and the frontend's public domain - they are two different URLs even though both live on Railway.
- [ ] **Required secrets**, generated in advance (e.g. `openssl rand -hex 32` for each):
  - `WEBHOOK_SECRET` (TradingView entry webhook auth)
  - `API_KEY` (the shared bearer key every protected backend route requires - this is also `ATLAS_API_KEY` on the frontend side; see §4)
  - `MARKET_STATE_WEBHOOK_SECRET` (protects `POST /api/v1/market-state`, independent of `WEBHOOK_SECRET`)
  - Optional: `ANTHROPIC_API_KEY`, `ALERT_WEBHOOK_URL` - leave unset for a first deploy unless you specifically want those features live immediately.

---

## 2. Repository/deployment roots

Two Railway services, one project, one repository:

- **Backend service root**: `live/` (Railway service Settings → Root Directory).
- **Frontend service root**: `frontend/` (a second Railway service, same repo, same project, its own Root Directory setting).
- **Backend build/start**: no separate build step - `live/Procfile` declares the start command directly: `web: uvicorn atlas.main:app --host 0.0.0.0 --port $PORT`. Railway reads this automatically once Root Directory is set to `live`.
- **Frontend build/start**: Railway auto-detects the Next.js app via Nixpacks from `frontend/package.json` (`"build": "next build"`, `"start": "next start"`) the same way it already auto-detects the Python backend. No Dockerfile is required. If you want an explicit start command rather than relying on auto-detection, add `frontend/Procfile` with `web: npm start` - this mirrors the backend's own `Procfile` convention and removes any ambiguity about how the service starts.
- **Snapshot location inside the backend artifact**: `live/research/snapshots/{re1-summary.v1.json, re2-summary.v1.json, dataset-health.v1.json}` - **inside** the `live/` root Railway builds from (production-hardening amendment 2). Confirm these three files are actually committed to git and present in the branch/commit Railway is deploying (`git ls-files live/research/snapshots/`) - if they were ever accidentally `.gitignore`'d or excluded, the backend will still start (LIVE endpoints are unaffected) but every FROZEN endpoint will 503 with `reason: "missing_file"` until fixed. This is exactly what §3.5 below is for.

---

## 3. Railway configuration — backend service

### 3.1 Environment variables

All required variables are validated by `atlas.config.Settings.validate_for_startup()` at process start when `ENVIRONMENT=production` (the default) - a missing required one is a **hard startup failure** (crash-loop), not a silent degradation.

| Variable | Required? | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Auto-injected by Railway's Postgres plugin in the same project - do not set manually. |
| `API_KEY` | Yes | The shared bearer key. **Must exactly match** the frontend service's `ATLAS_API_KEY` (§4) - the BFF proxy authenticates to this backend using that value. |
| `WEBHOOK_SECRET` | Yes | TradingView entry webhook auth - unrelated to UI v2, but still required for startup. |
| `MARKET_STATE_WEBHOOK_SECRET` | Yes | Protects `POST /api/v1/market-state`, the ingestion path every UI v2 LIVE page ultimately depends on having real data for. |
| `FRONTEND_ORIGINS` | Conditional | **Not required for the UI v2 BFF path itself** (production-hardening amendment 1 - the BFF's request to this backend is server-to-server, never subject to browser CORS, regardless of which platform hosts either side). It IS required, set to the frontend service's **public** Railway domain, if the pre-UI-v2 legacy pages remain in use (`/rule-engine`, trades/analytics/AI/activity - these fetch directly from the browser) or the SSE connection (`/api/v1/stream`, opened directly by the browser via `EventSource` on every page load, not just legacy ones - see §4.1). Set it regardless unless you are certain both of those are fully retired. |
| `ANTHROPIC_API_KEY`, `PICKMYTRADE_WEBHOOK_URL`, `ALERT_WEBHOOK_URL`, `CLAUDE_FAILURE_ALERT_THRESHOLD`, `RISK_ENFORCEMENT`, `ACCOUNT_*` | Optional | Unrelated to UI v2 - see `docs/staging/deployment-checklist.md`'s own Safety Gates section before setting any of these, especially `PICKMYTRADE_WEBHOOK_URL` (real order execution) and `RISK_ENFORCEMENT`. |

### 3.2 Which variables must match the frontend service

- Backend's `API_KEY` **must exactly equal** the frontend service's server-only `ATLAS_API_KEY`. A mismatch doesn't crash either service - it makes every UI v2 page's data fetch fail with a sanitized `401`-derived error from the BFF proxy (never the raw key, per the proxy's own error-sanitization contract). If UI v2 pages all show a generic fetch-failed error after deploy, check this first.
- Backend's `API_KEY` also (separately) equals the frontend's legacy `NEXT_PUBLIC_API_KEY`, if the legacy pages are still in use (§4).
- Backend's `FRONTEND_ORIGINS` must list the frontend service's **public** domain (not its internal one - browsers can't resolve `*.railway.internal`; see §4.1).

### 3.3 Postgres wiring

Use Railway's own Postgres plugin in the same project so `DATABASE_URL` is auto-injected into the backend service (`docs/staging/deployment-checklist.md` Step 1.4). Confirm migrations apply on first boot - the deploy log should show each migration file applying in order before `Uvicorn running on http://0.0.0.0:$PORT`.

### 3.4 Health/status endpoints

- `GET /health` (also mounted at `GET /api/v1/health`) - liveness/readiness, verifies the Postgres pool actually serves a query. Public, no API key required (Railway's own health-check prober can't send custom headers). Returns `{"ok": true, "database": "ok", "started_at": ..., "uptime_seconds": ...}` on success, `503` with `"database": "error: ..."` on failure.
- `GET /api/v1/status` - requires the API key. This is where **research snapshot readiness** is exposed (production-hardening amendments 3 and its follow-ons) - see §3.5.

### 3.5 How to confirm research snapshots are ready

```
curl -s https://<backend-service>.up.railway.app/api/v1/status \
  -H "Authorization: Bearer <API_KEY>" | python3 -m json.tool
```

Look at the `research_snapshots` object:

```json
"research_snapshots": {
  "status": "ready",
  "reason": null,
  "all_ready": true,
  "files": {
    "re1-summary.v1.json": { "status": "ready", "reason": null, "detail": null },
    "re2-summary.v1.json": { "status": "ready", "reason": null, "detail": null },
    "dataset-health.v1.json": { "status": "ready", "reason": null, "detail": null }
  }
}
```

- `status: "ready"` (and `all_ready: true`) means all three snapshot files exist, parsed correctly, matched their required schema, agreed with each other on dataset identity, and their content checksums verified against what's actually on disk - checked once at process startup, not per-request.
- Any other `status` (`"missing"` or `"invalid"`) means Research Overview and Dataset Health will 503 for every request until fixed - LIVE pages (Market View, Active Setup Bundle, Timeline, Episode Inspector) are **unaffected**, since they have no dependency on these files at all.
- Check `reason` for the stable failure code: `missing_file` (the file isn't in the deployed artifact - almost always a Root Directory or `.gitignore` problem, see §2), `json_error` (corrupted file), `schema_error` (malformed envelope), `checksum_mismatch` (the file's content doesn't match its own recorded checksum - it was edited or corrupted after export), or `dataset_identity_mismatch` (the three snapshots don't agree on symbol/timeframe/row_count/date range - all three are marked invalid together in this case, since there's no way to know which one is actually correct).
- `detail` per file is a short, sanitized, human-readable explanation - never a raw filesystem path or stack trace, safe to paste into a support ticket or Slack message as-is.
- **Fix path**: regenerate and re-commit the three files (`python scripts/export_research_snapshots.py`, run from `live/`) and redeploy. There is no way to fix a degraded snapshot state without a new deploy - this state is computed once at startup, not re-checked live.

### 3.6 Startup log expectations

A healthy first boot's log should show, in order: migrations applying, then `Uvicorn running on http://0.0.0.0:$PORT`, with no `RuntimeError` before it. The snapshot readiness check runs silently during this same startup sequence (in `atlas.main`'s `lifespan()`) and never itself prevents startup - if it will 503 the FROZEN endpoints, you won't see that from the log, only from `GET /status` (§3.5).

---

## 4. Railway configuration — frontend service

### 4.1 Environment variables

| Variable | Where it's read | Notes |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | **Both** server-side (the BFF proxy route) and client-side (browser) | Must be set to the backend service's **public** Railway URL - `https://<backend-service>.up.railway.app`, never the internal one. This is the one variable that genuinely can't be pointed at Railway's private network today: the BFF proxy route (`app/api/proxy/[...path]/route.ts`) reads this exact variable server-side for its own outbound fetch, but the *same* variable is also inlined into the client bundle and read directly by the browser - by the legacy pages' direct fetches (`lib/api.ts`, `lib/ruleEngineApi.ts`'s manual-key path) and, more importantly, by the SSE connection (`lib/live-updates.tsx`), which the root layout opens on **every** page load across the whole app, not just legacy ones. A browser cannot resolve a `*.railway.internal` hostname - it's a private network address, not public DNS. So this variable must stay public for as long as any of those browser-side call sites exist. See §4.4 for what a private-networking optimization for the BFF specifically would require. |
| `ATLAS_API_KEY` | **Server-only** | Must exactly equal the backend service's `API_KEY` (§3.2). Deliberately **not** `NEXT_PUBLIC_`-prefixed - Next.js Route Handlers never ship server-only env vars to the client bundle, which is the entire point of the BFF pattern. Every UI v2 page (Market View, Active Setup Bundle, Timeline, Episode Inspector, Research Overview, Dataset Health) reaches the backend exclusively through this key, never through a browser-visible one. |
| `NEXT_PUBLIC_API_KEY` | Client-bundled | **Legacy warning**: this key ships to the browser and is read by the pre-UI-v2 pages (`/rule-engine`, plus `lib/api.ts`'s trades/analytics/AI/activity pages, and the `/api/v1/stream` SSE connection). This is a disclosed, deliberately-unfixed inconsistency from before UI v2 - do not treat its presence in the client bundle as a UI v2 regression or as something this migration introduced; it predates UI v2 and UI v2's own pages never read it. |

### 4.2 Internal vs. public communication — which is which

Two genuinely different communication paths exist between the frontend service and the backend service, and only one of them is a candidate for Railway's private networking:

- **Server-to-server (the BFF proxy)**: the frontend service's own Next.js server process calls the backend over HTTP from `app/api/proxy/[...path]/route.ts`. This is the one path that *could*, in principle, use Railway's internal networking (`<backend-service-name>.railway.internal`, resolvable only between services in the same Railway project) instead of the public internet - lower latency, and the request never leaves Railway's network.
- **Browser-to-backend (legacy pages + SSE)**: the user's actual browser, running on their own machine, opens connections directly to the backend for the pre-UI-v2 pages and for the SSE stream. This path is **never** a candidate for internal networking - a browser is not a Railway service and cannot reach `*.railway.internal` under any configuration. It always needs the backend's public URL, and it's always subject to `FRONTEND_ORIGINS`/CORS.

### 4.3 Build settings

Root Directory: `frontend`. No custom build/install/output overrides needed - Railway's Nixpacks auto-detection handles `next build` on its own, or add `frontend/Procfile` (`web: npm start`) if you want an explicit start command instead of relying on auto-detection.

### 4.4 Optional future optimization: private networking for the BFF specifically

Today's code reads one shared variable (`NEXT_PUBLIC_API_BASE_URL`) for both the BFF's server-side fetch and every browser-side call site (§4.1) - there is currently **no way** to point the BFF at `<backend-service>.railway.internal` without also breaking the SSE connection and legacy pages, which would try to resolve that same private hostname from the browser and fail. This is not a bug and does not block Railway-only deployment - the app works correctly today using the public URL for every path, exactly as it did when the frontend was on a different platform entirely.

A future, optional enhancement - out of scope for this documentation-only migration, and not implemented in the current codebase - would add a second, server-only variable (e.g. `ATLAS_BACKEND_INTERNAL_URL`) that the BFF proxy route prefers when set, falling back to `NEXT_PUBLIC_API_BASE_URL` otherwise. That would let the BFF's own outbound calls use `http://<backend-service>.railway.internal:<port>` for a real latency win, while `NEXT_PUBLIC_API_BASE_URL` continues to serve the browser-side paths unchanged. Do not attempt this by simply setting `NEXT_PUBLIC_API_BASE_URL` itself to an internal hostname - that will break every browser-side connection in the app, not just optimize the BFF.

### 4.5 How to confirm the key is absent from browser assets/storage

After deploy, from a machine that can reach the frontend's public URL, open the deployed site, view page source / any loaded JS chunk, and search for the literal `ATLAS_API_KEY` string or the key's own value - it must not appear. This mirrors the local check already run during development:

```
grep -r "ATLAS_API_KEY" .next/static/   # run against a local production build; expect no matches
```

For the deployed artifact specifically, use the browser's DevTools → Sources panel to search all loaded JS for the key value, and DevTools → Application → Local Storage/Session Storage/Cookies to confirm nothing was ever written there (expected: nothing is, since the key never reaches the browser for any BFF-proxied request in the first place - this check confirms that's actually true in production, not just in local review).

---

## 5. First-deploy validation sequence

1. **Create PostgreSQL** - Railway project → New → Database → Add PostgreSQL (if not already provisioned).
2. **Deploy the backend** - the existing backend service, or a new one with Root Directory `live`, with the variables from §3.1 set (`Settings.validate_for_startup()` will crash-loop it without the required ones - set them before the first deploy).
3. **Verify the backend**:
   ```
   curl -s https://<backend-service>.up.railway.app/health
   curl -s https://<backend-service>.up.railway.app/api/v1/status -H "Authorization: Bearer <API_KEY>"
   ```
   Confirm `/health` returns `{"ok": true, ...}` and `/status` returns 200 with a real JSON body (not a 401, which would mean `API_KEY` isn't set or doesn't match what you're sending). Also verify snapshots per §3.5 - confirm `research_snapshots.status == "ready"` before moving on.
4. **Deploy the frontend** - a second service in the same project, Root Directory `frontend`, with the variables from §4.1 set (`ATLAS_API_KEY` matching the backend's `API_KEY`, `NEXT_PUBLIC_API_BASE_URL` set to the backend's **public** URL from step 3).
5. **Verify the frontend** loads at all: open its public Railway URL in a browser, confirm the dashboard shell renders with no console errors.
6. **Verify internal networking** is available for future use (§4.4), even though current code doesn't use it: from the Railway dashboard, confirm both services show as being in the same project and that Railway's private networking is enabled for the project (this is a one-time project-level check, not something you configure per-deploy).
7. **Verify the BFF** - from the deployed frontend's own public domain (not localhost), confirm the proxy actually reaches the backend:
   ```
   curl -s https://<frontend-service>.up.railway.app/api/proxy/setup-engine/latest?symbol=<real-symbol>&timeframe=5m
   curl -s https://<frontend-service>.up.railway.app/api/proxy/research/dataset-health
   ```
   Both should return the backend's real JSON (through the proxy, no `Authorization` header needed from curl here - the proxy attaches its own). A `404` means the path isn't on the allowlist (check for a typo); a `502` means the proxy couldn't reach the backend (check `NEXT_PUBLIC_API_BASE_URL` and that the backend service is actually up); a `503` with `{"ok": false, "error": "..."}` is the backend's own sanitized error passed through verbatim (e.g. a degraded snapshot).
8. **Test all six UI v2 routes** in a real browser against the deployed frontend URL:
   - `/market-view` - 7 facts, 4 setups, LIVE freshness badge
   - `/active-setups` - active setup cards, freshness badge
   - `/timeline` - per-setup lanes, freshness badge
   - `/episodes` - current episode + frozen duration strip + recent history, freshness badge
   - `/research` - six frozen report panels, FROZEN badge
   - `/dataset-health` - dataset identity, certification table, known warnings, FROZEN badge

   For each: confirm the page loads with no console errors, the freshness/frozen badge renders, and (for the two FROZEN pages) the mismatch banner behaves correctly if the live selector's default symbol doesn't match the frozen baseline's `MNQ1!` (this is expected, not a bug - see §6).

---

## 6. Real-repository checks

Everything through §5 can be verified against a backend with no real market data at all (LIVE pages will show their `found: false` / no-data state, which is itself correct behavior). Once real `MarketState` ingestion is flowing (TradingView webhook or manual `POST /api/v1/market-state`):

- [ ] **Latest real closed bar**: confirm `GET /api/v1/rule-engine/latest` and `GET /api/v1/setup-engine/latest` return `occurred_at` matching the actual latest bar you know was ingested (cross-check against the repository directly if possible, not just the UI).
- [ ] **`data_as_of` equality**: confirm every UI v2 envelope's `data_as_of` exactly equals that same latest-bar timestamp - not "close to it."
- [ ] **current/delayed/stale state**: with fresh data, the FreshnessBadge should read "LIVE — LAST CLOSED BAR." Stop ingestion (or wait past a few bar intervals) and confirm it transitions to "LIVE — DELAYED" and then "LIVE — STALE" at the documented thresholds (`lib/freshness.ts`: current ≤ 1.5× the timeframe's bar duration, stale > max(3×, 5 minutes)) - never silently staying on the "LAST CLOSED BAR" label.
- [ ] **Symbol/timeframe**: confirm the live selector's default (`lib/liveSelector.tsx`, currently `MNQU6`/`5m`) matches a symbol/timeframe you're actually ingesting real data for - if not, either change the default in a follow-up commit or document that operators must change it on first load.
- [ ] **CT timestamps**: spot-check a known real bar's timestamp against the badge/panel display - it should read in Central Time with an explicit "CT" suffix, correctly adjusted for whichever of CST/CDT is in effect on the date in question (`lib/format.ts`'s `formatClockCT`/`formatDateShortCT`).
- [ ] **Live episode endpoint**: `GET /api/v1/setup-engine/episodes/live?symbol=...&timeframe=...&window=500` - confirm `window.actually_used` is sane (not silently clamped to something unexpected), and if any setup has a genuinely long-running active episode, confirm the progressive window-widening behavior resolves its left boundary correctly rather than falling back to `query_window_start` for a run that should have a real observed activation (production-hardening plan §2's own open item - this is the one code path that couldn't be fully exercised with synthetic seed data during development).

---

## 7. Security checks

- [ ] **Unapproved proxy routes remain blocked**: `curl -s https://<frontend-service>.up.railway.app/api/proxy/trades` and `/api/proxy/health` should both `404` - confirm against the real deployed proxy, not just the local test suite (which mocks `fetch` and can't catch a build-time behavior difference).
- [ ] **Sanitized error responses** - trigger each of these against the real deployment (not by deliberately breaking the backend service - use whatever real, organic failure you can safely observe, e.g. a request with a wrong/expired key for the 401 case) and confirm the response body never contains the real API key, a stack trace, or an internal hostname:
  - `401` (wrong/missing key)
  - `404` (unapproved path)
  - a network timeout (temporarily point `NEXT_PUBLIC_API_BASE_URL` at an unreachable host in a **non-production** preview/staging service, never production, to observe this safely)
  - an HTML gateway error page (hard to trigger deliberately without risk - if Railway ever returns a real 502/504 gateway page organically, capture it once as evidence rather than trying to force it)
- [ ] **No secret in assets, responses, logs, or storage** - repeat §4.5's check against the live deployment, and additionally check both Railway services' own log output (Railway's dashboard, per service) for the key ever appearing in a request log line, error log, or stack trace.

---

## 8. Rollback

- **Backend rollback**: Railway dashboard → the backend service's Deployments tab → select the last known-good deployment → Redeploy. No git revert needed - Railway retains prior build artifacts. If the issue is a bad/missing environment variable rather than bad code, fix the variable and let Railway redeploy automatically instead of rolling back.
- **Frontend rollback**: Railway dashboard → the frontend service's Deployments tab → select the last known-good deployment → Redeploy. Same mechanism as the backend, now that both services live on the same platform - there is no separate "Vercel promote to production" step to remember.
- **Database compatibility**: rolling the backend back to an older commit is only safe if no migration introduced in the newer commit is required by data already written under the newer version. UI v2's own backend work (research export, live-view projection, the snapshot readiness check) introduced **no new database migrations or schema changes** - it reads existing `MarketState` data and static snapshot files only, so a UI v2-only rollback carries no database-compatibility risk. Verify this holds for whatever specific commit range you're rolling across before assuming it's always true.
- **Snapshot rollback as one atomic set**: the three research snapshot files (`live/research/snapshots/*.json`) must always be rolled back together, never individually - they are cross-validated as a set (production-hardening amendment: dataset-identity consistency, §3.5) specifically because an inconsistent mix (e.g. an old `re1-summary.v1.json` alongside a new `re2-summary.v1.json`) is exactly the failure mode that check exists to catch, and it will correctly mark **all three** invalid with `reason: "dataset_identity_mismatch"` if you roll back only one. Always roll back to a single prior commit's full set of three files together (`git checkout <commit> -- live/research/snapshots/`), never mix-and-match.
- **Key rotation steps**: to rotate `API_KEY`/`ATLAS_API_KEY`:
  1. Generate a new value.
  2. Set it in the backend service's `API_KEY` **and** the frontend service's `ATLAS_API_KEY` (and `NEXT_PUBLIC_API_KEY`, if the legacy pages are still in use) at the same time - a window where they disagree will make every UI v2 page fail with a sanitized auth error until both sides are updated.
  3. Redeploy both services (Railway picks up a variable change automatically for most services, but a manual redeploy is the reliable way to force a `NEXT_PUBLIC_*` value to actually rebuild into the client bundle immediately - server-only `ATLAS_API_KEY` takes effect on the frontend service's next restart).
  4. Confirm via §3.5/§5.3 that both sides now agree before considering rotation complete.

---

## 9. Evidence template

Fill this in once a real deployment happens. Nothing below is filled in yet - this deployment has not occurred.

| Field | Value |
|---|---|
| Backend service URL | *(not yet deployed)* |
| Frontend service URL | *(not yet deployed)* |
| Railway project name | |
| Backend git commit | |
| Frontend git commit | |
| Deployment timestamp (CT) | |
| `GET /health` result | |
| `GET /status` → `research_snapshots.status` | |
| Backend test results (`pytest -q`) | |
| Ruff result | |
| Frontend test results (`npm test`) | |
| Frontend production build result | |
| Measured cache-hit latency (`window=500`) | |
| Measured cache-miss latency (`window=500`) | |
| Measured `GET /setup-engine/episodes/live?window=500` payload size | |
| Screenshots (Market View / Active Setup Bundle / Timeline / Episode Inspector / Research Overview / Dataset Health) | |
| Screenshots (narrow viewport) | |
| Known blockers / open items | |
