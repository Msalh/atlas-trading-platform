# UI v2 — Market Intelligence Dashboard: Implementation Plan

**Status**: Planning only. No implementation code has been written from this plan. Builds directly on `docs/ui_v2/market-intelligence-dashboard-architecture.md` (revision 2) — read that first; this document does not repeat its rationale, only the task breakdown, contracts, and operational detail needed to execute it.

**Ground rules carried in from the architecture doc, restated because every task below is checked against them**: no modification to `atlas.rule_engine`, `atlas.setup_engine`, `atlas.research.statistical_profiling`, or `atlas.research.setup_profiling`; no new statistic/aggregation/threshold anywhere; no privileged API key in browser-shipped code; no FROZEN section ever silently relabeled to a live selection it doesn't match.

## 1. Backend tasks, dependency order

Two independent tracks converge at router registration. Tasks within a track are strictly ordered; the two tracks (A: frozen snapshot export, B: live projection) have no dependency on each other and can proceed in parallel.

### Track A — frozen snapshot export

| # | Task | Depends on | Notes |
|---|---|---|---|
| A1 | `atlas/research_export/models.py` — `SnapshotEnvelope`, `DatasetHealthSnapshot` dataclasses | — | Pure data shapes, no logic. |
| A2 | `atlas/research_export/serialization.py` — one generic `to_jsonable()` recursive converter (dataclass fields, `Enum.value`, tuple/frozenset → sorted list, `Mapping` → dict with sorted keys) + `wrap_envelope()` helper | A1 | Reads RE-1/RE-2 dataclass **types** for `dataclasses.fields()` introspection only — never imports their computation functions. |
| A3 | `atlas/research_export/snapshot_builder.py` — re-runs `run_statistical_profile.load_and_merge_states` + `build_statistical_profile`, and each of RE-2's 6 `build_*` functions, against the frozen five-file CSV set; serializes each result via A2; assembles `DatasetHealthSnapshot` from `certify_historical_dataset.py`'s real `certify()` output plus the small hand-transcribed `known_warnings` list (documented `warnings_source: "manual_transcription"`) | A2 | Imports RE-1/RE-2's public `build_*` functions as a **library call**, same as `run_statistical_profile.py`/`run_setup_profile.py` already do — this is the one place new code calls the frozen pipeline, and it calls it unmodified. |
| A4 | `scripts/export_research_snapshots.py` — thin CLI wrapping A3, writes `research/snapshots/re1-summary.v1.json`, `re2-summary.v1.json`, `dataset-health.v1.json` | A3 | Mirrors `run_statistical_profile.py`'s own CLI shape. |
| A5 | Run A4 against the frozen dataset; commit the three JSON files | A4 | The only step that touches `research/`. Checked in like the markdown reports. |
| A6 | Reproducibility test: re-run A3 in-process inside a test and assert byte-for-byte equal (after re-serializing) to the checked-in JSON from A5, and assert specific figures (row_count=97858, code_version present, checksum verifies) | A5 | Proves the snapshot is a faithful reproduction, not hand-edited drift. |
| A7 | `atlas/api/v1/research.py` — `GET /research/re1/summary`, `/research/re2/summary`, `/research/dataset-health`; loads the three JSON files once at process start (or lazily with an in-process cache), returns as-is wrapped in the response envelope (§3) | A5 | No computation, no markdown parsing, ever, at request time. |
| A8 | Tests for A7: 404/error shape if a snapshot file is missing, envelope fields present, content matches the checked-in file | A7 | |

### Track B — live projection

| # | Task | Depends on | Notes |
|---|---|---|---|
| B1 | `atlas/live_view/models.py` — `LeftBoundaryReason` enum, `LiveEpisodeProjection`, `LiveSetupSnapshot`, `LiveWindowResult` | — | Pure data shapes. Never imported by, and never importing internals of, `atlas.research.setup_profiling` beyond its already-public `build_*` functions and `models.RegisteredFactSnapshot`/`TerminationReason` types (reused for shape consistency, not redefined). |
| B2 | `atlas/live_view/episode_projector.py` — the progressive-fetch + boundary-resolution algorithm (architecture doc §4.3), calling `filter_input_states` → `segment_by_gap` → `build_rule_engine_output_window` → `build_setup_engine_output_window` unmodified | B1 | The one place with real new logic in this plan — gets the deepest test coverage (§4). |
| B3 | `atlas/live_view/cache.py` — dict-backed cache keyed by `(symbol, timeframe, window, latest_bar_timestamp)`, bounded size (LRU, small cap — cardinality is inherently tiny), plus in-flight request coalescing (one computation per key even under concurrent requests) | B1 | No TTL logic needed — the key itself expires correctness (§5.2). |
| B4 | `atlas/api/v1/setup_engine.py` — `GET /setup-engine/latest` (zero-computation wiring around the existing `setup_engine_output_to_dict()`) | — (independent of B1-B3) | Can be built and shipped before the rest of Track B; no live-window complexity here at all. |
| B5 | `atlas/api/v1/setup_engine.py` (continued) — `GET /setup-engine/episodes/live`, composing B2 + B3 | B2, B3 | Route code is fetch → call B2/B3 → shape response; no analytics in the route itself. |
| B6 | Tests for B2's boundary-resolution algorithm — the four `left_boundary_reason` cases, the progressive-widening path, and the hard-maximum truncation path (§4) | B2 | |
| B7 | Tests for B3's cache (hit/miss on bar-timestamp change, LRU eviction, coalescing under concurrent calls) | B3 | |
| B8 | Tests for B4/B5's HTTP layer (envelope shape, `warnings` populated correctly, error handling for an unknown symbol) | B4, B5 | |

### Convergence

| # | Task | Depends on |
|---|---|---|
| C1 | Register `research.py` and `setup_engine.py` routers in `atlas/main.py`, same `dependencies=[Depends(require_api_key)]` convention every existing non-public router uses | A7, B4, B5 |
| C2 | Full backend suite + Ruff | Everything above |

## 2. Frontend tasks, dependency order

| # | Task | Depends on | Notes |
|---|---|---|---|
| F1 | `app/api/proxy/[...path]/route.ts` — the one BFF route handler, forwards `GET` requests to the Atlas backend with the server-only `ATLAS_API_KEY` attached (§6) | Backend Track A/B routes registered (C1) at least in a dev/staging environment | |
| F2 | `lib/setupEngineApi.ts`, `lib/researchApi.ts` — typed client functions, calling `/api/proxy/...` (never the Atlas backend directly), mirroring the shapes in §3 | F1 | |
| F3 | `components/FreshnessBadge.tsx`, `components/MismatchBanner.tsx` | — (pure presentational, no data dependency) | Can be built in parallel with F1/F2. |
| F4 | `lib/useLiveEpisodes.ts` — the one shared TanStack Query hook for `GET /setup-engine/episodes/live`, consumed by F7/F8/F9 | F2 | |
| F5 | Layout-level shared LIVE symbol/timeframe selector | F2 | Drives every LIVE page; FROZEN pages read the snapshot's own identity instead (architecture §7). |
| F6 | Market View page + `SetupEngineViewer.tsx` (sibling to existing `RuleEngineViewer.tsx`) | F2, F3, F5 | Simplest data shape — good first live page to validate F1's proxy end-to-end. |
| F7 | Active Setup Bundle page + `ActiveSetupBundle.tsx` | F3, F4, F5 | |
| F8 | Timeline page + `Timeline.tsx` | F3, F4, F5 | |
| F9 | Episode Inspector page + `EpisodeInspector.tsx` + `EpisodeDurationStrip.tsx` | F3, F4, F5, F2 (for the frozen overlay + mismatch check) | The one HYBRID page — built last among the LIVE pages since it depends on both tracks. |
| F10 | Research Overview page + 6 panel components | F2, F3 | |
| F11 | Dataset Health page + panel components | F2, F3 | |
| F12 | Navigation wiring across all 6 pages | F6-F11 | |
| F13 | Frontend test setup (Vitest + React Testing Library — **does not exist in `frontend/` today**, no test runner is configured; this plan proposes adding a minimal one, not assuming it) | — | See §7. |
| F14 | Component/hook tests: boundary-reason rendering (the "at least N bars" copy), `MismatchBanner`, `useLiveEpisodes` cache-key behavior | F13, F7, F9 | |

## 3. API contracts

All four contracts share the envelope from the architecture doc §6. Field types below are a planning sketch (for backend/frontend agreement before code), not a schema file.

### 3.1 `GET /setup-engine/latest?symbol=&timeframe=`

```
envelope: { schema_version, source_track: "live", symbol, timeframe,
            generated_at, data_as_of, code_version, warnings: string[] }
setups: [
  { name: string,
    status: "computed" | "insufficient_data",
    detected?: boolean,
    severity?: "weak" | "normal" | "strong",
    reason?: string,
    evidence?: { supporting_facts: [...] } }
]
```

### 3.2 `GET /setup-engine/episodes/live?symbol=&timeframe=&window=`

```
envelope: { ...same as 3.1... }
window: { requested: int, actually_used: int }
setups: {
  [setup_name]: {
    current_episode: LiveEpisodeProjection | null,
    recent_episodes: LiveEpisodeProjection[],
    computability: { computable_bars, non_computable_bars, detected_true_bars,
                      detected_false_bars, insufficient_reason_counts }
  }
}
segments: [ { segment_id, start_timestamp, end_timestamp: string | null } ]
activation_events: [ { timestamp, activated_setups: string[] } ]

LiveEpisodeProjection = {
  setup_name: string,
  left_boundary_reason: "observed_activation" | "insufficient_data"
                         | "segment_start" | "query_window_start",
  activation_timestamp_observed: string | null,
  observed_start_timestamp: string,
  end_timestamp: string,
  duration_bars_observed: int,
  is_window_truncated: boolean,
  is_continuation: boolean,
  start_state: RegisteredFactSnapshot,
  end_state: RegisteredFactSnapshot
}
```

### 3.3 `GET /research/re1/summary`, `GET /research/re2/summary`

```
envelope: { schema_version, source_track: "frozen", symbol, timeframe,
            generated_at, data_as_of, code_version, warnings: string[] }
report: <the underlying StatisticalProfile / RE-2 report dataclass,
         serialized via atlas.research_export.serialization,
         unchanged in shape from the fields already documented in
         atlas.research.statistical_profiling.models / atlas.research.setup_profiling.models>
```

### 3.4 `GET /research/dataset-health`

```
envelope: { ...same shape as 3.3... }
dataset_identity: { symbol, timeframe, row_count, date_range: { start, end }, files: string[] }
segment_count: int
certification: {
  checks_run, pass_count, warning_count, fail_count, verdict: "certified" | "certified_with_warnings" | "rejected",
  checks: [ { section, check, verdict, detail } ]
}
known_warnings: [ { severity: "warning" | "fail", title, detail } ]
warnings_source: "manual_transcription"
frozen_version: { code_version, frozen_at }
```

## 4. Snapshot generation workflow

1. RE-1/RE-2 are regenerated (this only ever happens when a human explicitly re-runs and re-certifies a new baseline, e.g. a future RE-3 or a dataset expansion — never on a schedule).
2. Run `python scripts/export_research_snapshots.py` (Track A4) immediately after, against the same frozen CSV inputs.
3. The script writes `research/snapshots/re1-summary.v1.json`, `re2-summary.v1.json`, `dataset-health.v1.json`, each with a fresh `checksum`.
4. Run the reproducibility test (Track A6) locally before committing — it fails loudly if the freshly-computed serialization doesn't match what was just written (catches a snapshot-builder bug before it ships).
5. Commit the three JSON files in the same commit as the regenerated markdown reports, so `research/RE1_*.md`, `research/RE2_*.md`, and `research/snapshots/*.json` never drift relative to each other.
6. If RE-1 and RE-2 are ever regenerated independently of each other, bump only the affected snapshot's filename version (`re1-summary.v2.json`) rather than overwriting — the API route serves whichever version is current, and the schema_version inside each file remains the source of truth for consumers, not the filename alone.

## 5. Authentication flow

### 5.1 Primary: Backend-for-Frontend (confirmed feasible today)

`frontend/`'s `package.json` runs `next build && next start` — a real Node server, not a static export — so Next.js Route Handlers with server-only environment variables work today with no infrastructure change.

```
Browser --(same-origin fetch, no key)--> Next.js route handler (server-side)
                                              --(Authorization: Bearer ATLAS_API_KEY)--> Atlas API
```

- **New env var**: `ATLAS_API_KEY` — server-only (no `NEXT_PUBLIC_` prefix), never referenced in any client component, never present in `.next/`'s built client bundle. Reuses the **same value** as the backend's existing shared API key (`require_api_key`'s expected secret) — this is a delivery-mechanism change for UI v2's own new pages, not a new backend auth scheme.
- **Reused, unchanged**: `NEXT_PUBLIC_API_BASE_URL` — the proxy's own server-side fetch target. This value is not sensitive (it's a hostname), so no change needed there.
- **Route handler**: one generic `app/api/proxy/[...path]/route.ts`, `GET`-only (every UI v2 endpoint is read-only), forwards the path and query string to `${NEXT_PUBLIC_API_BASE_URL}/api/v1/${path}` with the `Authorization` header attached server-side, streams the JSON response back unchanged. Every UI v2 frontend call (§2, F2) goes through this one handler — no per-endpoint proxy code.
- **Verification** (acceptance criterion, §8): `grep -r "ATLAS_API_KEY" frontend/.next/static/` after a production build returns nothing; the key never appears in any client-shipped JS.

### 5.2 Documented fallback (not expected to be needed)

If a future deployment target for this app *cannot* run a Node server (e.g. a static export to a CDN with no server-side execution), the fallback is a manual, explicitly-temporary session key:
- Held only in `sessionStorage` (cleared on tab close — never `localStorage`, never a cookie, never bundled into build output).
- Entered once per browser session via a form, mirroring `RuleEngineViewer.tsx`'s existing manual-entry UX (not reused verbatim, since that component's key lives in React state only and is scoped to one component — a session-wide variant would need a small shared context).
- Labeled in the UI itself as temporary, with a tracked follow-up to migrate to §5.1 once the deployment supports it.

This fallback is **not implemented** unless F1 (§2) proves infeasible during actual implementation — the current deployment already supports the primary pattern.

### 5.3 Existing pages are out of scope

`RuleEngineViewer.tsx`'s manual key-entry and the rest of the app's `NEXT_PUBLIC_API_KEY` pattern are unchanged by this plan — a disclosed, deliberately-deferred inconsistency (architecture doc §8, item 3), not retrofitted here.

## 6. Caching / performance limits

| Parameter | Value | Rationale |
|---|---|---|
| `window` default | 500 bars (≈ 41 hours at 5m) | Enough for a typical operator session's recent lookback without an oversized default fetch. |
| `window` hard maximum (progressive widening cap, architecture §4.3) | 5,000 bars (≈ 17 days at 5m) | Bounds worst-case per-request cost; this project's own certifier already processes 20x that (97,858 bars) in low single-digit seconds, so 5,000 bars through the same pipeline is comfortably sub-second. |
| `recent_episodes` per setup | 20 | Enough for Episode Inspector's activation history without an unbounded response. |
| Backend cache size | 32 entries (LRU) | Realistic cardinality of concurrently-interesting `(symbol, timeframe, window)` combinations is small; this is a safety cap, not a tuned production figure. |
| Backend cache key | `(symbol, timeframe, window, latest_bar_timestamp)` | No TTL needed — a new closed bar changes the key, so a stale entry is never served as current; an unchanged key is always still correct. |
| In-flight coalescing | one computation per cache key, concurrent requests await the same in-progress result | Prevents duplicate pipeline runs when Active Setup Bundle, Episode Inspector, and Timeline all mount within the same polling tick. |
| Frontend polling | same `pollInterval(sseConnected, baseMs)` pattern already established (`ActivityTimeline.tsx`); base interval per LIVE page proposed at 15-30s, matching `RuleEngineViewer.tsx`'s existing 30s manual-refresh precedent | No new streaming mechanism. |
| Soft response-time target | < 2s for `window` ≤ 500 (cache miss), effectively instant on cache hit | Operator-dashboard usability target, not a hard SLA. |

## 7. Test strategy

**Backend** (pytest, this project's existing, extensively-used convention — no new tooling needed):
- `atlas/research_export/serialization.py`: determinism (same input → byte-identical output across two runs), round-trip shape correctness for one representative dataclass from each of RE-1/RE-2, correct `Enum`/tuple/`Mapping` handling.
- `atlas/research_export/snapshot_builder.py`: the reproducibility test (§4 step 4 / Track A6) — freshly-computed output equals the checked-in JSON.
- `atlas/live_view/episode_projector.py`: the four `left_boundary_reason` cases with hand-built `MarketState`/`RuleEngineOutput`/`SetupEngineOutput` fixtures (the same fixture style already established in `tests/test_setup_profiling.py`), the progressive-widening path resolving on a second fetch, and the hard-maximum-reached truncation path.
- `atlas/live_view/cache.py`: hit/miss on a changed `latest_bar_timestamp`, LRU eviction at capacity, coalescing (two concurrent calls for the same key trigger exactly one computation — an `asyncio` concurrency test).
- New routers (`research.py`, `setup_engine.py`): envelope shape, `warnings` population, 404/error handling, auth dependency present (same `require_api_key` test pattern already used for existing routers).

**Frontend** (Vitest + React Testing Library — **new to this repo**, proposed minimal addition, not full coverage):
- `MismatchBanner`: renders the exact required copy when live/frozen identity differs, renders nothing when they match.
- The "active for at least N bars" / "activation occurred before..." copy renders correctly for each `left_boundary_reason`, and specifically that `query_window_start`/`segment_start` never render a bare timestamp as if it were the true activation.
- `useLiveEpisodes`: same query key across the three consuming pages (a static/type-level check plus one integration test), so React Query's cache dedupes as designed.
- The BFF proxy route handler: forwards correctly, never leaks the key into a response header or error body.

**Cross-cutting**: at the end of each rollout stage (§8), use the `verify` skill to actually drive the affected page(s) in a running instance rather than trusting tests alone — matching this project's own established practice of confirming real behavior before calling a slice done, not just "tests pass."

**Explicitly not testing**: any RE-1/RE-2/Rule Engine/Setup Engine correctness — those are exercised by their own existing, extensive test suites, untouched here.

## 8. Rollout stages

| Stage | Scope | Why this order |
|---|---|---|
| 0 | Backend Track A + Track B fully built and tested, routers registered, **no frontend changes yet** | Proves the new backend surface end-to-end (via direct API calls / the `verify` skill) before any UI depends on it. |
| 1 | Frontend auth (F1) + Research Overview + Dataset Health (F2, F3, F10, F11) | Lowest-risk frontend slice — entirely FROZEN, static-snapshot-backed, validates the BFF proxy pattern before any live-computation page depends on it. |
| 2 | Market View (F5, F6) | Simplest LIVE page — validates the proxy pattern against a live, per-request backend route. |
| 3 | Active Setup Bundle + Timeline (F4, F7, F8) | Both consume the shared live-episodes fetch; shipping them together exercises the cache/coalescing design (§6) under realistic multi-page load. |
| 4 | Episode Inspector (F9) + full navigation (F12) | Last, since it's the one HYBRID page depending on both tracks and the mismatch-banner logic. |
| 5 | Frontend test setup + tests (F13, F14), close-out review against acceptance criteria (§9) | Confirms the whole surface, not just each stage in isolation. |

Each stage ends with the `verify` skill exercising the real, running pages added in that stage — not just passing tests — before moving to the next.

## 9. Acceptance criteria

- **No computation modified**: `git diff` against `atlas/rule_engine/`, `atlas/setup_engine/service.py`'s existing functions, `atlas/research/statistical_profiling/`, `atlas/research/setup_profiling/` shows zero changes throughout this work (only new, additive packages/files).
- **Snapshot reproducibility**: Track A6's test passes — the checked-in JSON is byte-for-byte what the frozen pipeline currently produces.
- **Boundary semantics**: for each of the four `left_boundary_reason` values, a real or fixture-driven example renders the correct UI copy — in particular, `query_window_start` and `segment_start` never display a timestamp as the true activation, and always display "active for at least N bars" with the correct qualifying clause.
- **No silent mismatch**: with the live selector set to a symbol/timeframe other than `MNQ1!`/`5m`, Research Overview, Dataset Health, and Episode Inspector's distribution overlay all show the exact mismatch message from architecture §7, and render no frozen figures underneath it.
- **No privileged key in the browser**: the `grep` check from §5.1 passes on a production build.
- **LIVE means last closed bar**: every LIVE response's `data_as_of` is populated and is the latest bar's `occurred_at`, never a wall-clock timestamp; the UI displays it, not just a generic "live" dot.
- **Shared fetch**: Active Setup Bundle, Episode Inspector, and Timeline mounted together trigger exactly one `GET /setup-engine/episodes/live` network call per polling tick (verified via the browser network panel during the Stage 3/4 `verify` pass), not three.
- **Dataset Health stays scoped**: no live ingestion/API health metric appears on the Dataset Health page; it remains fully sourced from `research/snapshots/dataset-health.v1.json`.
- **Full test suite + Ruff clean** (backend), same standard every prior sprint in this project has held to.

## 10. Proposed commit boundaries

Small, independently-reviewable commits, mirroring the dependency order in §1/§2 (the same granularity RE-1/RE-2 already used throughout this project):

1. `feat(research-export): add atlas.research_export models + serialization` (A1, A2 + tests)
2. `feat(research-export): snapshot builder + export script` (A3, A4 + tests)
3. `docs(research): commit RE-1/RE-2 JSON snapshots` (A5, A6 — data-only commit)
4. `feat(api): research summary and dataset-health endpoints` (A7, A8)
5. `feat(live-view): live episode projection models + boundary resolution` (B1, B2 + tests — the highest-scrutiny commit, given amendment 1's precision requirements)
6. `feat(live-view): bar-keyed cache with in-flight coalescing` (B3 + tests)
7. `feat(api): setup-engine latest and live episodes endpoints` (B4, B5, B8)
8. `feat(api): register research and setup-engine routers` (C1, C2 — full suite + Ruff)
9. `feat(frontend): BFF proxy route handler + typed API clients` (F1, F2)
10. `feat(frontend): freshness badge, mismatch banner, shared live-episodes hook` (F3, F4)
11. `feat(frontend): research overview and dataset health pages` (F5 partial, F10, F11 — Stage 1)
12. `feat(frontend): market view page` (F6 — Stage 2)
13. `feat(frontend): active setup bundle and timeline pages` (F7, F8 — Stage 3)
14. `feat(frontend): episode inspector page + navigation` (F9, F12 — Stage 4)
15. `test(frontend): add Vitest + component tests` (F13, F14 — Stage 5)

Each commit runs its own scoped tests before landing; commits 8 and 15 additionally run the full-repo suite. No commit in this sequence touches `atlas/rule_engine/`, `atlas/setup_engine/service.py`'s existing functions, `atlas/research/statistical_profiling/`, or `atlas/research/setup_profiling/`.
