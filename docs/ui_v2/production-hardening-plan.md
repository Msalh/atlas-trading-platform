# UI v2 — Production Hardening & Operator Validation Plan

**Status**: Approved with amendments (revision 2). Implementation in progress per the Stage 0–4 order in this document. UI v2 is functionally complete (4/4 stages shipped, commits `3dd5ca6`..`80c55c9`); this plan covers what's needed to trust it in production and to validate it against real operator use — not new features.

**Explicit non-goals for this phase** (carried through every section below): no new analytics, no strategy logic, no signal/recommendation language, no RE-3, no changes to Rule Engine / Setup Engine / RE-1 / RE-2 computation. This is a hardening and validation pass, not a feature-expansion sprint.

**Ground truth this plan is based on**: as of this writing there is **no live deployment** — `docs/staging/deployment-checklist.md` documents an intended Railway (backend) + Vercel (frontend) target, but no git remote is configured and no platform account access exists yet.

---

## Execution order

- **Stage 0**: establish git remote/platform access, choose deployment roots/build commands, document exact Railway/Vercel configuration. **Requires the user** — account creation and git remote configuration are not actions available to be taken unilaterally.
- **Stage 1**: snapshot packaging determinism + startup validation, CT formatter, operational freshness states, cache LRU/FIFO correction, focused tests, full suites. Fully executable now, no platform access required.
- **Stage 2**: deploy staging with the real Postgres repository and real ingestion; validate BFF auth/connectivity/security. Blocked on Stage 0.
- **Stage 3**: measure latency, TTL, coalescing, payload size, rendering with real data. Blocked on Stage 2.
- **Stage 4**: operator review on desktop and narrow viewport; triage remaining debt; produce a measured validation report. Blocked on Stage 2/3.

---

## 1. Production deployment readiness

**Backend (Railway target, per `live/Procfile`: `uvicorn atlas.main:app --host 0.0.0.0 --port $PORT`)**

Required environment variables, all validated by `atlas.config.Settings.validate_for_startup()` when `ENVIRONMENT=production` (the default) — the app refuses to start without these:
- `DATABASE_URL` — Postgres connection string (Railway auto-provisions on Postgres plugin attach)
- `API_KEY` — the shared bearer key every protected route requires, and the one the BFF's `ATLAS_API_KEY` must match
- `WEBHOOK_SECRET` — TradingView entry webhook auth
- `MARKET_STATE_WEBHOOK_SECRET` — separate secret protecting `POST /api/v1/market-state`, independent of `WEBHOOK_SECRET`
- `FRONTEND_ORIGINS` — see the corrected CORS note directly below. Required for the legacy direct-browser pages that remain in use; **not** required for the UI v2 BFF request path itself.

Optional (graceful no-op if unset): `ANTHROPIC_API_KEY`, `PICKMYTRADE_WEBHOOK_URL`, `ALERT_WEBHOOK_URL`, `CLAUDE_FAILURE_ALERT_THRESHOLD`, `RISK_ENFORCEMENT` (if `true`, additionally requires the four `ACCOUNT_*` vars or startup fails).

**Corrected: CORS and the BFF path (amendment 1)**

UI v2's actual request path is:

```
Browser  --(same-origin)-->  Next.js BFF route (app/api/proxy/[...path]/route.ts)  --(server-to-server fetch)-->  Atlas API on Railway
```

The second hop is a server-to-server HTTP request issued from Vercel's own serverless runtime, not a request the *browser* makes. Browser CORS governs only requests a browser issues directly to a cross-origin server — it has no jurisdiction over a Vercel function calling Railway, exactly as `fetch()` from any backend-to-backend caller is never subject to CORS. Concretely: even with `FRONTEND_ORIGINS` left at its `http://localhost:3000` default, the deployed BFF can still reach the deployed Atlas API just fine, because the browser never talks to Atlas directly for any UI v2 page.

`FRONTEND_ORIGINS` is real and still required, but only for the **legacy/direct-browser call sites** that predate the BFF and remain in use: `src/lib/api.ts` (trades/analytics/risk/etc. pages), `src/lib/live-updates.tsx` (the `/api/v1/stream` SSE connection, opened directly by the browser via `EventSource`), and `src/lib/ruleEngineApi.ts`'s manual-key path (the pre-UI-v2 `/rule-engine` page). Each of those issues a real cross-origin browser request to the Railway origin and will be rejected by CORS if `FRONTEND_ORIGINS` doesn't list the deployed Vercel domain. If any of those pages remain in use in production, `FRONTEND_ORIGINS` must be set correctly for *them* — but that is a distinct requirement from "the BFF can reach Atlas," which needs no CORS configuration at all.

**Frontend (Vercel target)**
- `NEXT_PUBLIC_API_BASE_URL` — used by the BFF proxy route (server-side, not subject to CORS as above) to reach the Atlas API; also still read by the legacy direct-fetch code paths listed above, where it **is** subject to CORS since those requests originate in the browser.
- `ATLAS_API_KEY` — server-only, must exactly match the backend's `API_KEY`. **Validation task**: confirm this is set in Vercel's server-side env (not the `NEXT_PUBLIC_` bucket) and is absent from the client bundle (Section 5 covers the actual grep check).
- `NEXT_PUBLIC_API_KEY` — still read by the pre-UI-v2 pages (`/rule-engine`, trades/analytics/etc.). Out of scope for UI v2 itself, but note it as a **separate, already-disclosed inconsistency**: this key does ship to the browser today, by design of the older pattern, and those same pages are also the ones that need `FRONTEND_ORIGINS` set for CORS. Deploying UI v2 doesn't fix either of these, and this plan doesn't propose to.

**Server-only `ATLAS_API_KEY` validation**
Beyond "is it set": confirm at deploy time that (a) the BFF proxy's `Authorization: Bearer ${ATLAS_API_KEY}` header actually authenticates against the deployed backend's `API_KEY` (a 401 in the proxy's own sanitized-error path would otherwise look identical to "key not set" — need to distinguish these two failure modes during validation, e.g. by checking the *upstream* status the proxy is passing through), and (b) a request through the proxy without the browser needing to know the key at all works end-to-end from a real browser tab (not just curl with the header set manually).

**BFF-to-Atlas connectivity**
Validate the deployed Vercel frontend can actually reach the deployed Railway backend: DNS resolves, TLS is valid, no Railway private-networking restriction blocks the public request path the proxy uses (a request from a Vercel serverless function, not from the browser — confirm this is public-internet reachable, not internal-only; this is a network-reachability question, unrelated to CORS per the correction above). Confirm the proxy's `AbortSignal.timeout(10_000)` is a sane bound for real network latency between Vercel and Railway (not just local-loopback latency, which is what all testing to date has used).

**Deterministic research snapshot packaging (amendment 2 — production deployment blocker)**

Chosen strategy: **relocate the canonical snapshot output location into `live/`** (the Preferred option), so it ships inside whatever Railway build root is selected regardless of that choice, and so the runtime path resolves relative to a known module location rather than the process's current working directory or a `../research` relative climb.

- `research/snapshots/*.json` move to `live/research/snapshots/*.json` (implemented in Stage 1 — see `atlas/api/v1/research.py` and `scripts/export_research_snapshots.py`).
- Runtime path resolution changes from a `parents[N]` climb relative to `__file__` to a shorter, still `__file__`-relative path now that the snapshots live inside the same package tree — never dependent on `os.getcwd()`.
- `scripts/export_research_snapshots.py` writes to the new location; the old `research/` directory at the repo root is removed once the move is verified.
- Startup validation (next subsection) checks existence, JSON/schema envelope, and content checksum for all three files, and only trusts a path resolved this way — never an assumption that Railway happens to include files outside the selected build root.
- If Railway's root directory is ever changed to the repository root instead of `live/` (the Alternative strategy), this path resolution continues to work unchanged, since it's relative to the Python package, not to whichever directory the process happened to start from.

**Startup snapshot validation with degraded availability (amendment 3)**

Do not rely on snapshot problems only surfacing on the first Research request. At startup, `atlas.main`'s `lifespan()` now validates, for each of the three snapshots:
1. File exists at the resolved path
2. File parses as JSON and matches the expected `{envelope, payload}` schema shape
3. `envelope.content_checksum` matches a checksum recomputed over the deterministic payload (reusing `atlas.research_export.serialization`'s own `canonical_json`/`content_checksum` functions — the same ones that produced the checksum at export time)

This does **not** crash the whole service on failure — LIVE endpoints (`/rule-engine/latest`, `/setup-engine/latest`, `/setup-engine/episodes/live`) have no dependency on snapshot files and must keep working even if all three snapshots are missing or invalid. Instead:
- A per-file and aggregate status is computed once at startup and held in `app.state`: `ready` | `missing` | `invalid` per snapshot, with a short reason string for `missing`/`invalid`.
- FROZEN endpoints (`/research/re1/summary`, `/re2/summary`, `/dataset-health`) return a structured `503` with the specific reason (existing `SnapshotNotFoundError` path extended to also cover schema/checksum failures, not just a missing file) if their snapshot isn't `ready`.
- The existing operational status surface (`GET /status`) is extended with the snapshot readiness state, **not** the frozen `/dataset-health` response — Dataset Health continues to describe only the research baseline's own certification/warnings/segment content, never operational/deployment state, per the existing FROZEN/operational boundary.
- The frontend's Research Overview and Dataset Health pages already render `ApiFetchError`'s message inline on any non-2xx response (existing `isError` path); this phase confirms that path renders a clear, specific "research snapshots unavailable: <reason>" message for the degraded case, not a generic error string.

**Startup failure behavior — corrected**
- Missing secrets (`API_KEY`, `WEBHOOK_SECRET`, `MARKET_STATE_WEBHOOK_SECRET`) → **hard startup failure**, unchanged, correct, fail-closed.
- Missing/invalid snapshots → **explicit degraded startup**, service starts, LIVE endpoints fully operational, FROZEN endpoints structured-503, degraded state visible via `GET /status`. This is now a deliberate, implemented behavior, not an unaddressed gap.

---

## 2. Real live-repository validation

Everything shipped so far was validated against a throwaway in-memory `InMemoryMarketStateRepository`, seeded by hand with synthetic bars matching test-fixture shapes. That's a different code path from the real `PostgresMarketStateRepository` wired in `atlas/main.py`'s actual `lifespan()`, and it has never been exercised. **Blocked on Stage 0/2** (requires a real deployed backend against real Postgres).

- Point the deployed staging backend at the actual production-shaped Postgres repository with real ingested market data, not the in-memory double.
- Re-verify `GET /rule-engine/latest`, `GET /setup-engine/latest`, and `GET /setup-engine/episodes/live` against genuinely closed real bars — confirm `data_as_of`/`occurred_at` reflect an actual real timestamp, not a synthetic one, and that the 7 facts / 4 setups compute the same qualitative shapes (computed/insufficient_data mix) they did against synthetic data.
- Verify symbol/timeframe handling with the real, currently-live contract symbol (not `MNQU6`, which was this validation's synthetic placeholder) and confirm the live selector's default in `lib/liveSelector.tsx` matches something operators will actually use, or document that they'll need to change it on first load.
- Verify progressive window-widening (`atlas/live_view/episode_projector.py`'s `_resolve_window`) against a **genuinely long-running active episode**, if and when one actually occurs in production — this is the one code path that cannot be manufactured with a handful of seeded bars; the widening-loop bug fixed earlier in this engagement (stale cross-iteration episode objects) was only caught by testing exactly this scenario, and the fix has not yet been observed against real, organically-occurring long-duration data. If no long-running episode occurs naturally within a reasonable validation window, construct one deliberately in staging by ingesting enough real historical bars to force `left_boundary_reason=query_window_start` with `is_window_truncated=true`, and confirm the UI copy ("Active for at least N bars — activation occurred before the loaded window") renders correctly against that real, not synthetic, truncation.

---

## 3. Freshness and timezone validation

**Timezone — resolved now (amendment 4), not deferred**

All market timestamps in UI v2 render in `America/Chicago` explicitly, using the IANA zone name (not a fixed UTC offset), via new `formatClockCT`/`formatDateShortCT` helpers in `lib/format.ts` that pass `timeZone: "America/Chicago"` to the native `Intl`/`toLocaleString` formatting call. This is implemented in Stage 1:
- The IANA zone, not a fixed offset, is what makes daylight-saving handling automatic: the JS runtime's bundled ICU timezone database applies the correct CST/CDT offset for the given instant, with no manual DST arithmetic and no new dependency.
- Every formatted time carries an explicit `CT` label appended by the formatter itself, so no call site can forget it.
- Market View (`RuleEngineFactsPanel`, `SetupEngineViewer`), Active Setup Bundle, Timeline, Episode Inspector, and `FreshnessBadge` all switch to the CT formatters — the same function, not five independent implementations.
- Research Overview and Dataset Health's date displays also switch, since the frozen research reports' own CT hour/session-boundary conventions (documented in the RE-1/RE-2 research notes) and the LIVE timestamps must share the same timezone basis, per this amendment.
- The pre-UI-v2 `/rule-engine` page keeps the existing browser-local `formatClock`/`formatDateShort` — out of scope, a disclosed, unchanged inconsistency, consistent with that page's other pre-UI-v2 patterns.
- Focused tests assert formatting against a UTC instant that falls in CST (winter, UTC-6) and one that falls in CDT (summer, UTC-5), confirming the same formatter produces the correct wall-clock hour for both without any test-side DST logic — the runtime does it.

**Operational freshness states — resolved now (amendment 5), not deferred**

A reachable API with an old `data_as_of` must not continue displaying an unqualified LIVE badge. A new, shared, pure classification function (frontend, since two of the five states — `disconnected` and the fetch-failure half of `no_data`/`stale` distinction — can only be observed client-side from the fetch outcome itself) computes one of five states from `(dataAsOf, timeframe, queryOutcome)`:

| State | Meaning | Trigger |
|---|---|---|
| `current` | Badge reads "LIVE — LAST CLOSED BAR" | age of `data_as_of` ≤ 1.5× the timeframe's bar duration |
| `delayed` | A visibly softer warning treatment, still shows the real timestamp | age > 1.5× bar duration and ≤ `max(3× bar duration, 5 minutes)` (reuses the existing `isStale` threshold formula as the delayed→stale boundary) |
| `stale` | A visibly stronger warning treatment | age > `max(3× bar duration, 5 minutes)` |
| `no_data` | Distinct neutral state, not an error | response resolved with `found: false` — nothing has ever been ingested for this symbol/timeframe |
| `disconnected` | Distinct error state | the fetch itself failed (any `ApiFetchError`) — `data_as_of` cannot even be evaluated |

This reuses the existing threshold formula from `ruleEngineApi.ts::isStale` and the existing `TIMEFRAME_DURATION_MINUTES` table (centralized into the new module so both consumers share one source of truth) rather than inventing new numbers — no new trading-relevant analytics, purely an operational/UX classification of data recency. Thresholds and the state machine are documented in code and covered by focused tests, including boundary cases at exactly the 1.5×/3× cutoffs.

The UI never displays "LIVE — LAST CLOSED BAR" for anything other than `current`; `delayed`/`stale`/`no_data`/`disconnected` each get a visibly distinct, honestly-labeled treatment instead, so a reachable-but-stale backend can never be mistaken for a live feed.

- **Do not fold operational health into Dataset Health**: reconfirmed — freshness states live in the LIVE-side components (`FreshnessBadge` and its consumers) and, at the aggregate level, `GET /status`, never inside `/dataset-health`'s payload. Dataset Health keeps showing only the frozen research baseline's own health (certification, known warnings, segment count).

---

## 4. Performance and caching

All caching claims made in the architecture/implementation-plan docs (`atlas/live_view/cache.py`) have not been measured against real latency — validate with actual numbers, not estimates. **Blocked on Stage 2/3** (requires a real deployed backend under real load).

- **Cache-hit vs cache-miss latency for `window=500`**: measure real wall-clock time for a cold `GET /setup-engine/episodes/live?window=500` (full progressive-widening resolution against real repository data) versus a warm cache hit on the identical key. Record both numbers.
- **TTL behavior**: the real constant is `DEFAULT_TTL_SECONDS = 60.0` (`atlas/live_view/cache.py`) — confirm empirically that a request issued just under 60s after a prior one still hits cache, and one issued just after re-computes, against the real deployed cache instance (not a unit test's mocked clock).
- **Eviction correctness — resolved now (amendment 6), not deferred**: the cache is implemented as **true LRU** as of Stage 1 — `get()` now promotes a hit to most-recently-used, matching its own docstring's claim rather than contradicting it. A regression test proves a promoted entry survives an eviction round that would otherwise have dropped it under plain FIFO-by-insertion. Section 3 (staging) still measures whether eviction meaningfully triggers at real production key cardinality, but the implementation itself is no longer inconsistent with its documentation regardless of that measurement.
- **In-flight coalescing under concurrent requests**: confirm the per-key `asyncio.Lock` in `atlas/api/v1/setup_engine.py`'s `_get_or_compute` actually coalesces concurrent requests against the real deployed single-process backend — fire several genuinely concurrent requests (not sequential) for the same `(symbol, timeframe, window)` and confirm only one computation runs (observable via backend logs — `episode_projector.build_live_window_result` should log/execute once, not N times).
- **Response size and browser rendering cost**: measure the real JSON payload size for `GET /setup-engine/episodes/live?window=500` against real data (recall the RE-2 snapshot alone is hundreds of KB — the live-episodes response could be substantial too, especially with `recent_episodes` populated for all 4 setups), and measure actual browser paint/rendering time for Timeline and Active Setup Bundle against that real payload size, not the small hand-crafted fixtures used in every test so far.
- Document all of the above as **actual measured numbers** in the Stage 4 validation report — not "should be fast," not estimated from code reading.

---

## 5. Security validation

**Blocked on Stage 2** for the "real deployed proxy" items; the platform-error validation sub-item is corrected below to run safely against staging rather than production.

- **Unapproved BFF paths remain blocked in production**: re-run the existing allowlist tests' *intent* against the real deployed proxy (not just the unit tests, which mock `fetch`) — confirm a real request to e.g. `/api/proxy/trades` or `/api/proxy/health` 404s in production exactly as it does in the test suite, with no path found that slipped through a build-time difference between dev and prod Next.js behavior.
- **`ATLAS_API_KEY` absence, four surfaces**:
  1. Client assets — `grep -r "ATLAS_API_KEY" frontend/.next/static/` (already confirmed clean in this engagement's own build; re-confirm against the actual production build artifact Vercel deploys, not just a local build).
  2. Responses — confirm no response body, including error bodies, ever echoes the key (the proxy's sanitized-error path was built for this; validate against real upstream 401/timeout/500s per the corrected item below).
  3. Logs — check Railway's and Vercel's actual log output for the key ever appearing (e.g. in a stack trace, a debug log line, a framework's own request logging).
  4. Browser storage — confirm nothing writes the key to `localStorage`/`sessionStorage`/cookies (expected: nothing does, since the key never reaches the browser at all for BFF-proxied requests — validate this is actually true by inspecting real browser storage after using the app, not just by code review).
- **Sanitized behavior for backend timeout/401/404/500 — corrected (amendment 7)**: do **not** intentionally trigger uncontrolled real production `500`s to validate this. Instead, use **staging or a controlled mock upstream** to validate, for each of: `401`, `404`, a JSON `500`, an HTML `502`/`504` gateway response (matching what a real platform gateway timeout page looks like — not JSON, which the proxy's existing `res.json()` parse-failure path needs to be confirmed against), a network timeout, and a malformed/non-JSON response. Production validation is limited to confirming the sanitization contract holds for whatever real errors are organically observed during Stage 2/3 (e.g. a real transient network blip), never to deliberately destabilizing the live service to manufacture a 500.

---

## 6. Operator validation checklist

A human operator (not automated tests) should sit down with the real deployed dashboard against real data and confirm the items below. **Blocked on Stage 2/4.**

- **Market View readability**: can an operator glance at the 7 facts / 4 setups and correctly state the current market structure without needing to ask a clarifying question about what a value means.
- **Active Setup Bundle semantics**: does "Active for at least N bars — activation occurred before the loaded window" read as intended to someone who hasn't been following this engagement's design docs — i.e. does it correctly communicate "we don't know exactly when this started" without sounding like an error.
- **Episode Inspector usefulness**: is the historical duration-distribution comparison actually useful at a glance, or does it need a caption/legend improvement now that it's rendered against real distribution shapes (percentiles from real data can look very different from the small hand-crafted test fixtures used throughout this engagement).
- **Timeline clarity**: with real data and real episode counts (potentially many more episodes per setup than the 1–3 used in every test so far), confirm the lane-of-blocks layout stays legible — this is the component most likely to look different at real scale than in the tests that built it. Validate whether the `overflow-x-auto` scroll behavior on long lanes is actually usable, not just non-crashing.
- **LIVE vs FROZEN distinction**: confirm the badge distinction (FreshnessBadge's visual treatments, now including the five freshness states) reads clearly enough that an operator never mistakes frozen research data — or stale/disconnected live data — for a genuinely current live feed, especially on Episode Inspector where LIVE and FROZEN appear on the same screen.
- **Symbol/timeframe mismatch behavior**: confirm the mismatch banner's real-world trigger (today, by default, the live selector's `MNQU6` placeholder vs. the frozen baseline's real `MNQ1!` — validate this against whatever the real production live symbol actually is) reads as informative rather than alarming, and that operators understand they need to either accept the frozen baseline is for a different symbol or that no action is needed.
- **Desktop and narrow-screen usability**: re-run the responsive check (already done at 375px in this engagement, but only against synthetic single-digit episode counts) against real data volume on both desktop and a narrow viewport — particularly Timeline and the Research Overview JSON panels, which are the two components most likely to degrade with real-scale content.

---

## 7. Known debt triage

Classify only where still open — several items below are now resolved by Stage 1 rather than merely classified.

| Item | Source | Status / classification |
|---|---|---|
| Duplicated selector controls (one input per LIVE/HYBRID page, all bound to the same shared context, rather than one header-level control) | Design choice, Stage 2–4 (prior phase) | Open — cosmetic/DX, low priority, no functional impact |
| Simplified Timeline visualization (block-per-episode lane, not a pixel-scaled Gantt chart) | Design choice, Stage 3 (prior phase) | Open — reassess after Section 6's real-data operator check |
| Old `/rule-engine` page's manual-API-key-entry auth pattern, and the broader `NEXT_PUBLIC_API_KEY` client-bundled-key pattern used by pre-UI-v2 pages | Pre-existing, Sprint 16 | Open — security-relevant but explicitly out of UI v2's scope; standalone hardening item |
| Narrow `researchApi.ts` typing (RE-1/RE-2 report bodies stay `unknown` except the specific slices consumed) | Design choice (prior phase) | Not debt — re-classify only if a future page needs a currently-untyped slice |
| `FRONTEND_ORIGINS` defaulting to localhost-only | Found in Section 1 | Open, but re-scoped by amendment 1 — required only for legacy direct-browser pages, not the BFF path; must still be set correctly if those pages stay in use |
| Snapshot files loaded lazily with no startup-time existence/schema/checksum check | Found in Section 1 | **Resolved in Stage 1** — startup validation with degraded-state reporting implemented |
| No CT-forcing timezone conversion anywhere in the frontend | Found in Section 3 | **Resolved in Stage 1** — explicit `America/Chicago` formatters |
| Cache eviction is FIFO-by-insertion, not true LRU, despite being named/documented as LRU | Found in Section 4 | **Resolved in Stage 1** — true LRU promotion implemented |
| No frontend-visible "stale ingestion" or "backend disconnected" state distinct from a generic fetch-error message | Found in Section 3 | **Resolved in Stage 1** — five-state freshness classification implemented |
| Real Railway gateway error pages (e.g. 502/504 HTML) not explicitly tested against the proxy's non-JSON-response handling | Found in Section 5 | Open — validate against staging/mock upstream per amendment 7, not production |
| Any further issues discovered during Stage 2–4 execution | — | Add here as found, classify at that time |

---

## 8. Close-out criteria for this phase

- No new analytics, no new derived statistics, no new aggregation
- No strategy logic, no trading decisions
- No signal/recommendation language introduced anywhere
- RE-3 not started
- No changes to Rule Engine, Setup Engine, RE-1, or RE-2 computation
- Full frontend test suite, backend test suite, and Ruff remain green after every Stage 1 change
- Production build remains green
- Stage 1 fully executed and verified against real code/tests (not blocked on platform access)
- Stages 2–4 executed if and when platform access exists; otherwise explicitly reported as blocked, not silently skipped
- Section 7's triage table is complete and each item has an explicit status, even if that status is "open, deferred"

---

### Shared-fetch guarantee (carried forward, unchanged)

Concurrently mounted consumers of `useLiveEpisodes` (same `(symbol, timeframe, window)` query key) share one request and one cache entry **within a single page** — e.g. if a future page ever mounted both `ActiveSetupBundle` and `Timeline` together, react-query would dedupe them to one request. Separate route pages (Active Setup Bundle at `/active-setups`, Timeline at `/timeline`, Episode Inspector at `/episodes`) are not normally mounted simultaneously in a single-page-at-a-time router, so there is no cross-page request-sharing to validate — the guarantee that matters in practice is same-page-multiple-consumer dedup, which is what `useLiveEpisodes.sharedFetch.test.tsx` actually tests.
