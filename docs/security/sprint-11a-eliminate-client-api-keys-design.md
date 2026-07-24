# Security Hardening: Eliminate Client API Keys — Roadmap (Sprint 11A + 11B)

**Status**: Design document only. Nothing in this document has been implemented. No code written, no infrastructure modified, no commits created.

**Revision note**: originally scoped as one sprint. Per review, **split into two independent implementation sprints** — Sprint 11A (frontend-only, no backend auth changes) and Sprint 11B (backend authentication hardening, its own design review and maintenance window). This split is a hard boundary, not just an ordering preference: 11A must be able to complete, ship, and be verified stable in production with **zero** backend involvement, and 11B must not begin implementation until 11A's own monitoring period (below) has closed cleanly.

**Trigger**: the Sprint 10 deployment security investigation confirmed `NEXT_PUBLIC_API_KEY` (frontend, `confident-spirit` service) is byte-for-byte identical to the backend's `API_KEY` and to the BFF's own server-only `ATLAS_API_KEY` — a single shared secret, one instance of which is deliberately shipped into the public browser bundle. Classified High Severity, not a Sprint 10 regression (pre-existing since before UI v2), not blocking Sprint 10's own deployment.

---

## Sprint sequencing at a glance

| | Sprint 11A — Client API Key Elimination | Sprint 11B — Backend Authentication Hardening |
|---|---|---|
| **Touches** | Frontend only (`frontend/`) | Backend only (`live/atlas/api/security.py`, `config.py`, Railway env vars on `atlas-trading-platform`) |
| **Backend auth logic** | Unchanged | Changed — single shared key → multiple independently-issued keys |
| **Key rotation** | None | Yes — the actual point of the sprint |
| **Backend restart required** | No, for every step except none at all — 11A never restarts the backend | Yes — inherits Sprint 10's own account-flat/alerts-paused/maintenance-window discipline |
| **Design review** | This document | Its own, separate design review before implementation — this document sketches the shape (§7-§8 below) but does not constitute 11B's approval |
| **Gate to start** | Already approved | Does not start until 11A's monitoring period (below) closes with zero regressions |

---

## Background (applies to both sprints)

### Current architecture

Two parallel, architecturally distinct patterns coexist in the frontend today:

**Pattern A — direct browser→backend (the problem).** `frontend/src/lib/api.ts` reads `NEXT_PUBLIC_API_KEY` (Next.js inlines any `NEXT_PUBLIC_*` variable into the client bundle at build time) and attaches it as `Authorization: Bearer <key>` on every request, fetched directly against the backend's public Railway URL — no server-side hop. This predates the BFF entirely: Sprint 9 added `API_KEY` protection to the backend before any server-side proxy existed. A second, narrower instance of the same class of problem is `frontend/src/lib/ruleEngineApi.ts`'s manual-key path — not `NEXT_PUBLIC_`-prefixed (never baked into the build), but still a real credential typed into and held in browser memory, sent directly to the backend.

**Pattern B — BFF-only (the target, already built and proven).** `frontend/src/app/api/proxy/[...path]/route.ts` (server-only, never shipped to the browser) reads `ATLAS_API_KEY` and attaches it server-side. The browser calls this app's own same-origin `/api/proxy/{path}`, carrying no credential. `frontend/src/lib/proxyAllowlist.ts` is a closed, hand-authored table; `frontend/src/lib/proxyClient.ts` (`proxyGet`/`proxyPost`) is the typed browser-side helper. `frontend/src/lib/researchOpsApi.ts` (Sprint 10) is the reference implementation.

**Backend authentication** (`atlas/api/security.py`): `require_api_key` does a constant-time comparison (`hmac.compare_digest`) of the request's Bearer token against a single value, `settings.api_key` (the `API_KEY` env var). Applied at router-registration time to 14 routers. Three exceptions authenticate differently: `webhook` (own `WEBHOOK_SECRET`), `market_state` (own `MARKET_STATE_WEBHOOK_SECRET`), `health` (public). There is currently **no concept of multiple valid keys** — this single-key design is exactly what makes it Sprint 11A's job to eliminate the *client-side* exposure without touching it, and Sprint 11B's job to replace the design itself.

### Complete dependency graph — every component still depending on `lib/api.ts`

**Renders on every page (root layout, `frontend/src/app/layout.tsx`):**
- `HeaderStatusDot.tsx` → `api.status()` → `GET /api/v1/status`
- `HeaderKillSwitchDot.tsx` → `api.risk()` → `GET /api/v1/risk`

**`/` (dashboard):** `ConnectionStatusPanel.tsx` (`status`), `CurrentPositionCard.tsx` (`currentTrade`, nests `EntryScoreBadge.tsx` → `aiNotes`), `StatsSummaryCard.tsx` (`statsToday`), `TradeHistoryTable.tsx` (`tradeList`)

**`/trades/[correlationId]`:** `TradeDetailView.tsx` (`tradeDetail`, nests `TradeTimeline.tsx`/`PmtDiagnosticsPanel.tsx` — type-only imports, no fetches)

**`/account`:** `AccountBalanceCard.tsx`, `DailyLossCard.tsx`, `DrawdownCard.tsx`, `ExposureCard.tsx`, `KillSwitchBanner.tsx` — all five independently call `api.risk()`

**`/analytics`:** `AnalyticsSummaryCards.tsx` (`analyticsSummary`), `BreakdownSection.tsx` (`breakdown`, nests `BreakdownChart.tsx` — type-only), `DrawdownChart.tsx`/`EquityCurveChart.tsx` (both `equityCurve`)

**`/activity`:** `ActivityTimeline.tsx` (`activity`)

**`/ai`:** `AICopilotPanel.tsx` (4 functions: `currentTrade`, `intelligence`, `risk`, `analyticsSummary`; nests `copilotNotes.ts` — type-only), `AiNotesTimeline.tsx` (`aiNotes`), `AiReportsPanel.tsx` (`aiReports` **and** `triggerReport` — the one mutating call across all 25 files)

**Zero exposure** on `/rule-engine` (separate `ruleEngineApi.ts` pattern), `/active-setups`, `/dataset-health`, `/episodes`, `/market-view`, `/research`, `/timeline`, all six `/research-ops/*` pages.

**Endpoint inventory**: 13 functions, 10 distinct backend paths, 12 GET + 1 POST (`triggerReport` → `POST /api/v1/ai/reports/{period}`).

---

## Part 1 — Sprint 11A: Client API Key Elimination

### Scope

- Migrate all browser traffic currently going through `lib/api.ts` to the BFF (GET and the one POST — `triggerReport` is a `lib/api.ts` consumer like any other, and "remove `lib/api.ts` entirely" requires migrating it too; it introduces no backend change, only a new BFF allowlist entry for an already-existing backend route, same as every GET migration).
- Migrate `ruleEngineApi.ts`'s manual-key path to its own already-existing proxy alternative (`fetchLatestRuleEngineOutputViaProxy`).
- Eliminate every read of `process.env.NEXT_PUBLIC_API_KEY`.
- Delete `frontend/src/lib/api.ts`.
- Remove `NEXT_PUBLIC_API_KEY` from Railway — **only after** the monitoring period below.

**Explicitly out of scope for 11A**: no backend authentication changes, no key rotation, no backend restart, at any point. Every step in this sprint is a frontend-only deploy, verified independently, with the same rollback mechanism Sprint 10 itself used (`railway up --service confident-spirit` / redeploy last-known-good — never touching `atlas-trading-platform`).

### Migration pattern (mechanical, identical for every endpoint)

1. Add the path to `proxyAllowlist.ts` (`GET: { params: [...] }`, or `POST: { bodyFields: [...] }` for `triggerReport` only).
2. Write a typed client function in a new domain-scoped module — interface + hand-written runtime type guard + `proxyGet`/`proxyPost`, matching `researchOpsApi.ts`'s shape exactly.
3. Swap the consuming component's import from `@/lib/api` to the new module — no change to rendered output, loading/error/empty states, or data shape.
4. Existing component tests carry over unchanged (only the mocked URL changes, from the backend's public URL to `/api/proxy/{path}`).
5. Remove the now-unused function from `lib/api.ts` only once its last caller is migrated.

### Migration groups, ordered by risk and effort

| Group | Scope | Endpoints | Effort | Why this position |
|---|---|---|---|---|
| **0** | `HeaderStatusDot`, `HeaderKillSwitchDot` | `status`, `risk` | Very low | **Do first.** Renders on *every page*, including all six Research Ops pages. Largest risk reduction per unit of effort in the whole sprint. |
| **1** | `/rule-engine`'s manual-key path | `rule-engine/latest` | Very low | The safe proxy call (`fetchLatestRuleEngineOutputViaProxy`) already exists in the file; only the page's call site needs to switch. |
| **2** | Dashboard (`ConnectionStatusPanel`, `CurrentPositionCard`+`EntryScoreBadge`, `StatsSummaryCard`, `TradeHistoryTable`) | `status`, `trades/current`, `stats/today`, `trades`, `ai/notes` | Low-medium | High-traffic root page, still all read-only |
| **3** | Account (5 components) | `risk` (already allowlisted from Group 0) | Low | Genuine consolidation opportunity: 5 independent `risk()` calls could become one shared query key |
| **4** | Analytics (`AnalyticsSummaryCards`, `BreakdownSection`+`BreakdownChart`, `DrawdownChart`, `EquityCurveChart`) | `analytics/summary`, `analytics/breakdown`, `analytics/equity-curve` | Low-medium | Read-only, page-scoped |
| **5** | Activity (`ActivityTimeline`) | `activity` | Very low | Trivial |
| **6** | AI (`AICopilotPanel`, `AiNotesTimeline`, `AiReportsPanel`) | `trades/current`, `ai/intelligence`, `risk`, `analytics/summary`, `ai/notes`, `ai/reports`, **`ai/reports/{period}` (POST)** | Highest | **Do last, deliberately.** The only POST in the entire migration — the first production POST the allowlist would carry since `research/promotion/decide` was added-then-removed as scope leakage in Sprint 10 Slice A.1. Confirm the BFF doesn't introduce a second, inconsistent rate limit or bypass the backend's existing 5/min limit before this ships. Still zero backend change — the route already exists; only its BFF reachability is new. |

### Group independence — order, not a dependency chain

The numbering above is an **execution order** (risk/effort-driven), not a technical dependency chain. Concretely:

- **Groups 0-5 can ship independently, in any order, and independently of Group 1** (the `/rule-engine` manual-key migration touches a completely separate file/pattern from `lib/api.ts` and has no relationship to Groups 0/2-6 beyond sharing this roadmap). Nothing about Group 3 requires Group 2 to exist first, and so on — each group's own files are disjoint from every other group's.
- **Group 6 is scheduled last on purpose, not by necessity** — it is the only group introducing a POST proxy path, and gets extra care as a result (see its own row above). It could technically ship earlier without breaking anything else; the ordering is a risk-management choice, not a blocking dependency.

**One real dependency exists, and it is not between groups — it is between "every group" and the variable-removal step**: `NEXT_PUBLIC_API_KEY` cannot be removed from Railway until **every** remaining consumer has been migrated, with no exception for scope or difficulty. This means:

- Groups 0-6 **and** Group 1 (the `/rule-engine` migration) must all be complete — the monitoring period and variable removal are gated on the full set, not just the `lib/api.ts` groups.
- **If Group 6 is delayed for any reason** (its own review takes longer, a problem is found, priorities shift), **the monitoring period does not start and the Railway variable removal does not proceed** — even if Groups 0-5 and Group 1 are all fully shipped and verified. A partially-migrated state is a valid, stable, safe place to pause (each shipped group already reduced real exposure), but it is explicitly **not** a state from which the variable can be removed. The acceptance-criteria grep (`process.env.NEXT_PUBLIC_API_KEY` returns zero matches) is the literal, unambiguous gate — it either passes for the whole codebase or it doesn't; there is no partial-credit path to variable removal.

### Removing `lib/api.ts`

Only after every group above lands and is verified in production:

1. Confirm zero remaining imports: `grep -rl 'from "@/lib/api"' frontend/src` returns empty.
2. Confirm zero remaining reads of the env var: `grep -rn "process.env.NEXT_PUBLIC_API_KEY" frontend/src` returns empty.
3. Delete `frontend/src/lib/api.ts` in the same change as the Group 6 migration that empties its last caller.
4. Give type-only imports (`Factor`/`TimelineEvent` in `TradeTimeline.tsx`, `PmtRelayDiagnostics` in `PmtDiagnosticsPanel.tsx`, `BreakdownGroup` in `BreakdownChart.tsx`, `IntelligenceSnapshot`/`RiskResponse` in `copilotNotes.ts`) a new home alongside their migrated group's own typed client module before deleting the file they currently come from.
5. Full frontend suite, ESLint, TypeScript, production build — standard gate, unchanged from every Sprint 10 slice.

### Monitoring period (new — before Railway variable removal)

Once `lib/api.ts` is deleted and the codebase reads `NEXT_PUBLIC_API_KEY` nowhere, **the Railway variable itself stays in place for 24-72 hours** before removal. During this window, verify:

- **Zero authentication regressions** — every migrated page continues to load correctly across the monitoring window, not just at the moment of deploy.
- **Zero unexpected 401s** — `railway logs --service atlas-trading-platform --filter "@httpStatus:401"` (or equivalent) shows no new pattern of failures correlated with the migration; a pre-existing, unrelated 401 rate (if any) is not itself a blocker, but any *new* 401 pattern is investigated before proceeding.
- **Zero BFF failures** — `/api/proxy/*` requests continue returning expected status codes (200/404/503 as designed), no unexpected 502s indicating the BFF can't reach the backend.

Only after this window closes clean does variable removal (below) proceed. This period exists because deleting the *code path* that reads a variable is verifiable instantly (grep), but confirming nothing *external* or missed still depends on the variable's continued presence benefits from real elapsed time in production, not just a point-in-time check.

### Removing `NEXT_PUBLIC_API_KEY` from Railway

The one Railway environment-variable change in Sprint 11A — performed only after the monitoring period closes clean:

1. Re-confirm via live bundle inspection (fetch every loaded JS chunk from production, search for the key value and for `NEXT_PUBLIC_API_KEY`) that it no longer appears anywhere in the deployed bundle — the same method that originally found this issue, re-run as closing proof.
2. Remove `NEXT_PUBLIC_API_KEY` from the `confident-spirit` service's Railway variables.
3. Redeploy the frontend (`railway up --service confident-spirit` — frontend-only, zero backend interaction, zero maintenance-window requirement).
4. Confirm no regression: full frontend smoke test against production.

### Sprint 11A deployment plan

- Every group (0-6) is its own independent frontend-only deploy, verified with a per-group production smoke test before the next group begins — same discipline as Sprint 10's own page-by-page verification.
- No downtime at any point: each group is additive on the backend allowlist side (server already exists and is unaffected) and a same-shape data-layer swap on the frontend side, verified by the existing test suite before every deploy.
- A problem in one group never blocks or requires reverting an already-shipped group, since each touches a disjoint set of files.

### Sprint 11A rollback

- **Per-group**: Railway dashboard → `confident-spirit` → Deployments → redeploy last known-good (or `railway redeploy --service confident-spirit`). Always available, zero backend coordination, since 11A never touches the backend.
- **Allowlist entries are inert if unused** — a Group-N allowlist addition left in place after a Group-N rollback is harmless.
- **Variable-removal rollback**: re-add `NEXT_PUBLIC_API_KEY` with its last value, redeploy frontend-only.

### Sprint 11A acceptance criteria

1. `grep -rn "process.env.NEXT_PUBLIC_API_KEY" frontend/src` returns zero matches.
2. The live production browser bundle contains no backend credential (verified by fetching every loaded JS chunk and searching for the key value and for `NEXT_PUBLIC_API_KEY`/`ATLAS_API_KEY`/`API_KEY`).
3. All frontend API traffic flows exclusively through `/api/proxy/*` or `/api/stream` (verified via network-request inspection against every page in a real browser session).
4. `lib/api.ts` no longer exists in the repository; `ruleEngineApi.ts`'s manual-key path is confirmed unused.
5. The 24-72 hour monitoring period closed with zero authentication regressions, zero unexpected 401s, zero BFF failures.

**Sprint 11A does not, by itself, satisfy** "direct browser access to authenticated backend endpoints is eliminated" in the deepest sense — a `curl` with the (still-shared) `API_KEY` value would still succeed directly against the backend, bypassing the BFF entirely, since the backend's own auth boundary is unchanged. That's Sprint 11B's job.

### Sprint 11A success metrics

Acceptance criteria (above) determine whether the implementation is **technically complete** — each is a binary pass/fail check against the code or the deployed artifact at a point in time. Success metrics are a separate concept: they measure whether the migration **achieved its operational goal** across the full effort, including how it was executed, not just its end state.

- **100% of authenticated frontend requests flow through the BFF** — every one of the 10 migrated endpoints (Groups 0-6) and the `rule-engine/latest` migration (Group 1), with no exceptions left on the old direct-fetch path.
- **0 executable usages of `process.env.NEXT_PUBLIC_API_KEY`** — same measurement as acceptance criterion 1, restated here as an operational outcome: the elimination is total, not "reduced to an edge case."
- **0 direct browser requests to authenticated backend endpoints** — verified across the full page sweep (acceptance criterion 3's network-inspection method), not just the pages that were the primary target of any one group.
- **0 authentication regressions during the monitoring period** — no migrated page broke, flickered into an error state, or required a hotfix during the 24-72 hour window.
- **0 rollback events during the migration** — no group required invoking the rollback procedure (§ Sprint 11A rollback) at any point across all 7 groups plus the variable-removal step. A rollback isn't a failure of the *plan* (the rollback mechanism existing and working is itself a success condition) — but zero invocations needed is the actual operational bar this migration is aiming for, given every group was designed to be small and independently verifiable specifically to make a rollback unnecessary in the first place.

These are reported alongside the acceptance criteria at Sprint 11A's close, but judged differently: a technically-complete migration (all acceptance criteria pass) that needed three rollbacks along the way met the bar for "done" but not for "went well" — worth distinguishing in the sprint's own retrospective, not just its pass/fail gate.

---

## Part 2 — Sprint 11B: Backend Authentication Hardening

**Does not begin implementation until Sprint 11A's monitoring period has closed with zero regressions.** Requires its own, separate design review beyond what's sketched here — this section establishes the shape and scope boundary, not a pre-approved implementation plan.

### Scope

- Multiple backend service keys — replace `require_api_key`'s single-value `hmac.compare_digest(token, settings.api_key)` with a set-based comparison against any of several independently-issued, independently-revocable keys.
- Service-specific credentials — the BFF gets its own key, distinct from the operator/manual-`curl` key, distinct from any future consumer's key.
- Secret separation — no two purposes share one secret value.
- Multi-key validation — constant-time comparison against every configured key, never a shortcut that leaks which key (if any) matched via timing.
- Backend key rotation — a real procedure, safe because multiple valid keys can coexist during a rotation window.
- Final removal of legacy `API_KEY` sharing — once the BFF holds its own distinct value, `API_KEY` stops being the same value `ATLAS_API_KEY` holds.

**Explicitly requires**: its own design review, its own maintenance window, the same account-flat/alerts-paused/health-baseline/recorded-rollback-target discipline Sprint 10's own backend deployment used — this is a backend-touching, backend-restarting change, categorically different from every step in 11A.

### Secret separation design (sketch, for 11B's own review)

- Extend `Settings` to hold a set of valid keys (e.g. `settings.api_keys: frozenset[str]`, sourced from one or more env vars), and `_check()` in `atlas/api/security.py` to accept if the presented token constant-time-matches *any* configured key.
- Introduce a distinct `BFF_SERVICE_KEY` (backend) / matching `ATLAS_API_KEY` value (frontend, unchanged name, still server-only) — generated independently from `API_KEY`, never derived from or equal to it.
- `API_KEY` itself becomes reserved for direct, non-BFF authenticated access (manual `curl` operator use, the deployment runbook's own smoke-test procedures) — still valid, but no longer the value any running service holds.
- Any future service credential (mobile app, third-party integration, another internal tool) gets its own distinct entry in the same set — never reuses an existing one, making future revocation surgical rather than requiring a coordinated all-consumers rotation.

### Key-rotation procedure (sketch, for 11B's own review)

1. Generate the new value for the specific key being rotated.
2. Add the new value to the backend's key set **alongside** the old one — both valid simultaneously (only possible once the set-based design above exists).
3. Update the one consuming service's own credential to the new value, redeploy that service only.
4. Confirm authentication succeeds with the new value.
5. Remove the old value from the backend's set, redeploy the backend.
6. This removes the "both sides must change atomically or every call fails" window `docs/ui_v2/deployment-runbook.md` §8.7 currently warns about under the single-shared-key design.

### Sprint 11B deployment/rollback (sketch)

Backend-touching, so inherits Sprint 10's own backend deployment discipline in full: confirm account flat, confirm alerts paused, confirm maintenance window, record the pre-change deployment ID, health-baseline check immediately before, monitor startup/webhook/PickMyTrade/risk/market-state logs continuously during and after cutover, rollback via redeploying the recorded last-known-good backend deployment (never `railway down`, never an improvised in-production fix) if startup fails, health checks fail, or errors don't stabilize promptly.

### Sprint 11B acceptance criteria (sketch)

1. The backend accepts multiple independently-valid keys, verified by presenting two different valid values and confirming both succeed.
2. A revoked key is rejected immediately after removal from the set, with no backend restart required to take effect (or, if a restart is required by the chosen implementation, that this is explicitly documented and accounted for in the rotation procedure above).
3. `API_KEY` and `ATLAS_API_KEY` are confirmed to hold different values in production (the same byte-for-byte comparison method used in the Sprint 10 investigation, now expected to return `false`).
4. A direct, credentialed `curl` against a `require_api_key`-gated endpoint still succeeds with a valid key (confirming the backend's own auth boundary works correctly under the new design) while confirming the *specific* value formerly known as the shared secret, if intentionally retired, no longer authenticates.

---

## Summary

Two independent sprints. **11A**: seven migration groups (0-6), all frontend-only, ending in a 24-72 hour monitoring period before the one Railway variable removal — zero backend involvement throughout. **11B**: backend authentication redesign — multi-key support, service-specific credentials, real rotation — gated on 11A's clean monitoring period, requiring its own separate design review and its own maintenance window before implementation begins. No code has been written for either sprint. No infrastructure has been modified. No commits exist. Waiting for approval before 11A implementation begins.
