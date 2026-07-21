# UI v2 — Market Intelligence Dashboard: Implementation Plan

**Status**: Approved, revision 2 (amended per second review). Implementation proceeds in the order below; this document is the authoritative task/contract breakdown, built on `docs/ui_v2/market-intelligence-dashboard-architecture.md` (revision 3) — read that first for rationale.

**Ground rules carried in from the architecture doc, restated because every task below is checked against them**: no modification to `atlas.rule_engine`, `atlas.setup_engine`, `atlas.research.statistical_profiling`, or `atlas.research.setup_profiling`; no new statistic/aggregation/threshold anywhere; no privileged API key in browser-shipped code; no FROZEN section ever silently relabeled to a live selection it doesn't match; no unconditional correctness claim for a cache without a documented residual limitation.

## 1. Backend tasks, dependency order

### Track A — frozen snapshot export

| # | Task | Depends on | Notes |
|---|---|---|---|
| A1 | `atlas/research_export/models.py` — `SnapshotEnvelope` (§3.2 fields: `schema_version`, `source_computation_version`, `snapshot_exporter_version`, `source_freeze_document`, `source_report_versions`, `content_checksum`, `exported_at`, `dataset_identity`), `KnownWarning` (§3.3), `DatasetHealthPayload` | — | Pure data shapes. |
| A2 | `atlas/research_export/serialization.py` — `to_jsonable()` (generic recursive converter) + `canonical_json()` (stable key ordering, no incidental whitespace, used for checksum input **and** for the file's own on-disk formatting so a diff of the checked-in file is meaningful) | A1 | |
| A3 | `atlas/research_export/known_warnings.py` — hand-curated `KNOWN_BASELINE_WARNINGS: tuple[KnownWarning, ...]`, transcribed from `docs/market_engine/re1-phase5-freeze.md` and `re2-freeze.md`'s "Known limitations" sections, each with a stable `id`, `source_document`, `source_section` | A1 | |
| A4 | `atlas/research_export/snapshot_builder.py` — for RE-2: calls `build_setup_profiling_dataset()` **exactly once**, passes the same `dataset` to all six `build_*` functions (mirrors `run_setup_profile.py`'s own established pattern — never re-run per report); for RE-1: `build_statistical_profile()` already computes its whole result in one call. Splits each result into `payload` (deterministic) and computes `content_checksum` over `canonical_json(payload)`, then attaches the `SnapshotEnvelope`'s remaining (partly dynamic) fields separately. Assembles `DatasetHealthPayload` from `certify_historical_dataset.py`'s real `certify()` output plus A3's typed warnings. | A2, A3 | |
| A5 | `scripts/export_research_snapshots.py` — thin CLI wrapping A4 | A4 | |
| A6 | Run A5 against the frozen dataset; commit `live/research/snapshots/re1-summary.v1.json`, `re2-summary.v1.json`, `dataset-health.v1.json` | A5 | |
| A7 | Reproducibility test: rebuild `payload` fresh, `canonical_json()` it, recompute `content_checksum`, assert equality with the checked-in file's checksum; **separately** assert envelope shape (fields present, correct types) — never assert the whole file, or `exported_at`, is byte-identical across runs | A6 | The corrected test from amendment 1. |
| A8 | Single-pass test: assert `build_setup_profiling_dataset()` is called exactly once during a full RE-2 snapshot export (call-count spy) | A4 | Amendment 7. |
| A9 | Known-warnings coverage test: assert the full expected set of warning `id`s appears in the built `dataset-health` payload | A3, A4 | Amendment 8. |
| A10 | `atlas/api/v1/research.py` — `GET /research/re1/summary`, `/research/re2/summary`, `/research/dataset-health`; loads the three JSON files, returns as-is wrapped in the response envelope (architecture §6), with `code_version` in the HTTP envelope set from `source_computation_version` — **never** `snapshot_exporter_version` | A6 | |
| A11 | Tests for A10: envelope shape, `code_version` sourced correctly, error handling for a missing snapshot file | A10 | |

### Track B — live projection

| # | Task | Depends on | Notes |
|---|---|---|---|
| B1 | `atlas/live_view/models.py` — `LeftBoundaryReason`, `LiveTerminationReason` (scoped to this package, **not** RE-2's `TerminationReason` — no `dataset_end`, and `is_active`/`null` represents "still open" rather than reusing an enum member for it), `LiveEpisodeProjection` (left-boundary fields **and** right-boundary fields: `is_active`, `last_observed_timestamp`, `end_timestamp_observed`, `termination_reason`, `right_boundary_observed`), `LiveSetupSnapshot`, `LiveWindowResult` | — | |
| B2 | `atlas/live_view/episode_projector.py` — left-boundary progressive-fetch resolution (unchanged from revision 1) **plus** right-boundary determination: after locating the run containing the latest bar, check the bar immediately after it (if any exists within the window) to set `is_active`/`termination_reason`/`end_timestamp_observed`; if the run extends to the window's own latest bar with nothing after it, `is_active=true` and every right-boundary field reflects "not yet observed" | B1 | The one place with real new logic — deepest test coverage. |
| B3 | `atlas/live_view/cache.py` — key `(symbol, timeframe, window, latest_bar_timestamp, rule_engine_registry_fingerprint, setup_engine_registry_fingerprint)`, bounded size (LRU), **plus a short TTL** as the documented mitigation for the residual gap (no repository data-revision marker exists today, so a backfill/correction to a non-latest bar isn't detectable by the key alone); `invalidate_all()` exposed for any future in-process caller; in-flight coalescing | B1 | Amendment 4 — the correctness claim is now explicitly bounded, not unconditional. |
| B4 | `atlas/api/v1/setup_engine.py` — `GET /setup-engine/latest` (zero-computation wiring) | — | Independent of B1-B3. |
| B5 | `atlas/api/v1/setup_engine.py` (continued) — `GET /setup-engine/episodes/live`, composing B2 + B3 | B2, B3 | |
| B6 | Tests for B2: the four `LeftBoundaryReason` cases, the progressive-widening path, the hard-maximum truncation path, **and** the right-boundary cases (`is_active=true` with all right-boundary fields null/unobserved; each of the three `LiveTerminationReason` values on a closed run; `recent_episodes` always closed with a real `termination_reason`) | B2 | |
| B7 | Tests for B3's cache (hit/miss on bar-timestamp change, hit/miss on registry-fingerprint change, TTL expiry, LRU eviction, coalescing under concurrent calls) | B3 | |
| B8 | Tests for B4/B5's HTTP layer | B4, B5 | |

### Convergence

| # | Task | Depends on |
|---|---|---|
| C1 | Register `research.py` and `setup_engine.py` routers in `atlas/main.py`, same `dependencies=[Depends(require_api_key)]` convention every existing non-public router uses | A10, B4, B5 |
| C2 | Full backend suite + Ruff | Everything above |

## 2. Frontend tasks, dependency order

Test tooling moves into the **first** frontend stage (amendment 6) — every commit from F1 onward ships with its own focused tests, not deferred to the end.

| # | Task | Depends on | Notes |
|---|---|---|---|
| F0 | Install and configure Vitest + React Testing Library (minimal — this repo has no frontend test runner today) | — | First frontend task, not the last. |
| F1 | `app/api/proxy/[...path]/route.ts` — BFF route handler with an **explicit allowlist** (§6), `GET`-only, validated query params, no arbitrary header forwarding, upstream timeout, sanitized error bodies | Backend routes registered (C1), F0 | |
| F1t | Tests for F1: allowlisted path passes through correctly; an unapproved path is rejected; an unexpected query param is stripped/rejected; a browser-supplied `Authorization` header is never forwarded; upstream timeout produces a sanitized error, never a stack trace or the real key | F1 | Amendment 6 — ships with F1, not deferred. |
| F2 | `lib/setupEngineApi.ts`, `lib/researchApi.ts` — typed clients calling `/api/proxy/...` only | F1 | |
| F3 | `components/FreshnessBadge.tsx`, `components/MismatchBanner.tsx` | F0 | |
| F3t | Tests for F3: `FreshnessBadge` shows `source_computation_version` (not the exporter version) on FROZEN, shows `data_as_of` on LIVE; `MismatchBanner` renders the exact required copy on a mismatch and nothing on a match | F3 | |
| F4 | `lib/useLiveEpisodes.ts` — the shared TanStack Query hook | F2 | |
| F4t | Test: the same query key is produced for the same `(symbol, timeframe, window)` regardless of which page calls the hook | F4 | |
| F5 | Layout-level shared LIVE symbol/timeframe selector | F2 | |
| F6 | Market View page + `SetupEngineViewer.tsx` | F2, F3, F5 | |
| F7 | Active Setup Bundle page + `ActiveSetupBundle.tsx`, including left/right-boundary copy ("active for at least N bars", "active through last closed bar") | F3, F4, F5 | |
| F7t | Boundary-rendering tests: each `LeftBoundaryReason` renders its required copy and never a false-precision timestamp; `is_active=true` renders "active through last closed bar" and never `end_timestamp_observed`; a closed `recent_episodes` entry renders its real `termination_reason` | F7 | Amendment 3, ships with F7. |
| F8 | Timeline page + `Timeline.tsx` (open vs closed episode bar treatment) | F3, F4, F5 | |
| F9 | Episode Inspector page + `EpisodeInspector.tsx` + `EpisodeDurationStrip.tsx` | F3, F4, F5, F2 | |
| F10 | Research Overview page + 6 panel components | F2, F3 | |
| F11 | Dataset Health page + panel components, rendering `KnownWarning`'s full traceability (`source_document`/`source_section`) | F2, F3 | |
| F12 | Navigation wiring across all 6 pages | F6-F11 | |
| F13 | Integration/close-out tests (end of Stage 5, §8) — cross-page checks (shared fetch dedup, mismatch banner across pages), not the first introduction of test tooling | F0-F12 | What used to be "add test tooling" is now integration tests only. |

## 3. API contracts

### 3.1 Shared envelope

```
{ schema_version, source_track: "live" | "frozen", symbol, timeframe,
  generated_at, data_as_of, code_version, warnings: string[] }
```

`code_version` on a FROZEN response is `source_computation_version` from the snapshot's own `SnapshotEnvelope` (§3.2) — never `snapshot_exporter_version`.

### 3.2 `SnapshotEnvelope` (on-disk shape, distinct from the HTTP envelope above)

```
{
  schema_version: string,
  source_computation_version: string,   // RE-1/RE-2 code commit that computed the figures -
                                          // read from the underlying RunManifest.code_version
  snapshot_exporter_version: string,     // atlas/research_export/ code commit at export time
  source_freeze_document: string,        // e.g. "docs/market_engine/re2-freeze.md"
  source_report_versions: { [filename: string]: string },
  content_checksum: string,              // SHA256(canonical_json(payload)), excludes exported_at
  exported_at: string,                   // the one dynamic field
  dataset_identity: { symbol, timeframe, row_count, date_range: { start, end } }
}
```

### 3.3 `GET /setup-engine/latest?symbol=&timeframe=`

```
envelope: { ...3.1..., source_track: "live" }
setups: [ { name, status: "computed" | "insufficient_data",
            detected?, severity?, reason?, evidence? } ]
```

### 3.4 `GET /setup-engine/episodes/live?symbol=&timeframe=&window=`

```
envelope: { ...3.1... }
window: { requested: int, actually_used: int }
setups: {
  [setup_name]: {
    current_episode: LiveEpisodeProjection | null,
    recent_episodes: LiveEpisodeProjection[],   // always is_active=false
    computability: { computable_bars, non_computable_bars, detected_true_bars,
                      detected_false_bars, insufficient_reason_counts }
  }
}
segments: [ { segment_id, start_timestamp, end_timestamp: string | null } ]
activation_events: [ { timestamp, activated_setups: string[] } ]

LiveEpisodeProjection = {
  setup_name: string,

  // left boundary
  left_boundary_reason: "observed_activation" | "insufficient_data"
                         | "segment_start" | "query_window_start",
  activation_timestamp_observed: string | null,
  observed_start_timestamp: string,
  duration_bars_observed: int,
  is_window_truncated: boolean,

  // right boundary (new, amendment 3)
  is_active: boolean,
  last_observed_timestamp: string,
  end_timestamp_observed: string | null,     // null whenever is_active=true
  termination_reason: "became_false" | "insufficient_data" | "segment_end" | null,
  right_boundary_observed: boolean,          // true only when is_active=false

  is_continuation: boolean,
  start_state: RegisteredFactSnapshot,
  end_state: RegisteredFactSnapshot
}
```

### 3.5 `GET /research/re1/summary`, `GET /research/re2/summary`

```
envelope: { ...3.1..., source_track: "frozen" }
report: <StatisticalProfile / RE-2 report dataclass, serialized via
         atlas.research_export.serialization, unchanged in shape>
```

### 3.6 `GET /research/dataset-health`

```
envelope: { ...3.1..., source_track: "frozen" }
dataset_identity: { symbol, timeframe, row_count, date_range: { start, end }, files: string[] }
segment_count: int
certification: { checks_run, pass_count, warning_count, fail_count, verdict,
                  checks: [ { section, check, verdict, detail } ] }
known_warnings: [
  { id, severity: "warning" | "fail", title, detail, source_document, source_section }
]
frozen_version: { source_computation_version, exported_at }
```

## 4. Snapshot generation workflow

1. RE-1/RE-2 are regenerated (only when a human explicitly re-runs and re-certifies a new baseline).
2. Run `python scripts/export_research_snapshots.py` (A5) against the same frozen CSV inputs.
3. The script builds the RE-2 substrate **once** (A4/A8), serializes each report's `payload`, computes `content_checksum` over the deterministic part only, and writes the envelope's remaining fields (`source_computation_version` read from the report's own `RunManifest`, `snapshot_exporter_version` from the currently-checked-out `atlas/research_export/` commit, `exported_at` from wall-clock now).
4. Run the reproducibility test (A7) locally before committing — it compares `content_checksum` values, not whole-file bytes, so it passes even though `exported_at` legitimately differs from the previous export.
5. Commit the three JSON files in the same commit as any regenerated markdown reports, so they never drift relative to each other.
6. If RE-1 and RE-2 are ever regenerated independently, bump only the affected snapshot's filename version (`re1-summary.v2.json`) rather than overwriting.

## 5. Authentication flow

### 5.1 Primary: Backend-for-Frontend (confirmed feasible today)

`frontend/` runs `next build && next start` — a real Node server — so Route Handlers with server-only environment variables work today.

```
Browser --(same-origin fetch, no key)--> Next.js route handler (server-side)
                                              --(Authorization: Bearer ATLAS_API_KEY)--> Atlas API
```

- **New env var**: `ATLAS_API_KEY` — server-only, never referenced in a client component, reuses the same value as the backend's existing `require_api_key` secret.
- **Reused, unchanged**: `NEXT_PUBLIC_API_BASE_URL` — the proxy's own server-side fetch target (not sensitive).

### 5.2 BFF proxy allowlist (amendment 5 — corrected from a fully-generic proxy)

`app/api/proxy/[...path]/route.ts` is **not** a blanket forward-everything proxy. It checks the requested path against an explicit allowlist before doing anything else:

```
ALLOWED_PROXY_PATHS = {
  "rule-engine/latest":            { params: ["symbol", "timeframe"] },
  "setup-engine/latest":           { params: ["symbol", "timeframe"] },
  "setup-engine/episodes/live":    { params: ["symbol", "timeframe", "window"] },
  "research/re1/summary":          { params: [] },
  "research/re2/summary":          { params: [] },
  "research/dataset-health":       { params: [] },
}
```

No operational health endpoint (`/health`, `/status`) is included — no UI v2 page currently calls one (Dataset Health is explicitly scoped to the frozen research baseline, architecture §3.6); one would be added explicitly, by name, if a future page needed it, never opened generically.

Additional restrictions, all enforced in the route handler itself:
- **Method**: `GET` only.
- **Query params**: only the names listed per path are forwarded; anything else is dropped, not passed through.
- **Headers**: only `Accept`/content-negotiation headers (if any) are forwarded from the browser request; the browser's own `Authorization` header, if somehow present, is never forwarded — the server's own `ATLAS_API_KEY` always replaces it.
- **Timeout**: a fixed upstream fetch timeout (e.g. 10s); a timeout or upstream error returns a generic, sanitized error body (`{"error": "upstream request failed"}`) — never the raw exception text, stack trace, or any header value from the failed response.
- **Unapproved path**: `404`, with no indication of what paths *would* have been allowed (avoid enumeration).

### 5.3 Documented fallback (not implemented unless §5.1 proves infeasible)

Manual session key, `sessionStorage` only, never `localStorage`, labeled temporary in the UI, with a tracked follow-up to migrate to §5.1.

### 5.4 Existing pages are out of scope

`RuleEngineViewer.tsx`'s manual key-entry and the rest of the app's `NEXT_PUBLIC_API_KEY` pattern are unchanged — disclosed, deliberately-deferred debt, not retrofitted here.

## 6. Caching / performance limits

| Parameter | Value | Rationale |
|---|---|---|
| `window` default | 500 bars (≈ 41 hours at 5m) | Typical operator lookback. |
| `window` hard maximum | 5,000 bars (≈ 17 days at 5m) | Bounds worst-case cost; this project's own certifier processes 20x that in low single-digit seconds. |
| `recent_episodes` per setup | 20 | |
| Backend cache size | 32 entries (LRU) | Realistic cardinality is small; a safety cap. |
| Backend cache key | `(symbol, timeframe, window, latest_bar_timestamp, rule_engine_registry_fingerprint, setup_engine_registry_fingerprint)` | Amendment 4 — bar-timestamp keying alone doesn't detect a backfill/correction to a non-latest bar, or a mismatched code version across processes; the fingerprints close the second gap cheaply and for real. |
| Backend cache TTL | short (e.g. 60s), applied **in addition to** the key above | **Documented, bounded limitation, not an unconditional guarantee**: this project's repository layer has no data-revision marker today (`get_latest`/`get_history`/`get_range`/`ingest`/`ping` — no version field), so a backfill/correction to a non-latest historical bar within an already-cached window can be stale for up to the TTL. If a repository revision marker is ever added, it should be folded into the cache key and the TTL requirement reconsidered. |
| Explicit invalidation | `cache.invalidate_all()`, exposed for any future in-process caller | No new HTTP admin endpoint in this phase; a process restart remains the primary invalidation path today. |
| In-flight coalescing | one computation per cache key, concurrent requests await the same in-progress result | |
| Frontend polling | `pollInterval(sseConnected, baseMs)`, base 15-30s | Matches `ActivityTimeline.tsx`'s existing pattern; no new streaming mechanism. |
| Soft response-time target | < 2s for `window` ≤ 500 (cache miss), effectively instant on cache hit | |

## 7. Test strategy

**Backend** (pytest, existing convention):
- Serialization determinism, round-trip shape correctness, `Enum`/tuple/`Mapping` handling (A2).
- Reproducibility test comparing `content_checksum`, not whole-file bytes (A7).
- Single-pass substrate test (A8).
- Known-warnings coverage test (A9).
- `episode_projector.py`: all four `LeftBoundaryReason` cases, progressive widening, hard-maximum truncation, **and** all right-boundary cases — `is_active=true` with every right-boundary field correctly null/unobserved, each `LiveTerminationReason` value on a closed run, `recent_episodes` always closed with a real reason (B6).
- `cache.py`: hit/miss on bar-timestamp change, hit/miss on registry-fingerprint change, TTL expiry, LRU eviction, concurrency coalescing (B7).
- New routers: envelope shape, `code_version` sourcing, auth dependency, error handling (A11, B8).

**Frontend** (Vitest + React Testing Library — installed at F0, the **first** frontend task, not the last):
- BFF proxy: allowlist enforcement, query-param filtering, header non-forwarding, timeout/error sanitization (F1t).
- `FreshnessBadge`, `MismatchBanner` (F3t).
- `useLiveEpisodes` query-key consistency (F4t).
- Left/right-boundary rendering copy, including the negative assertions ("never shows a bare timestamp as true activation", "never shows `end_timestamp_observed` while active") (F7t).
- Each of these ships **in the same commit** as the component/hook it tests (§9), not batched at the end.

**Final-stage tests are integration/close-out only** (F13): cross-page shared-fetch dedup (one network call per polling tick across the three pages that share `useLiveEpisodes`), mismatch-banner behavior across pages — not the first introduction of test tooling.

**Cross-cutting**: at the end of each rollout stage, use the `verify` skill to drive the affected page(s) in a running instance.

**Explicitly not testing**: any RE-1/RE-2/Rule Engine/Setup Engine correctness — exercised by their own existing suites, untouched here.

## 8. Rollout stages

| Stage | Scope |
|---|---|
| 0 | Backend Track A + Track B fully built and tested, routers registered — no frontend changes yet |
| 1 | Frontend test tooling (F0) + BFF proxy with allowlist (F1, F1t) + typed clients (F2) + `FreshnessBadge`/`MismatchBanner` (F3, F3t) + Research Overview + Dataset Health (F10, F11) — lowest-risk, entirely FROZEN slice, validates the BFF pattern |
| 2 | Market View (F5 partial, F6) |
| 3 | Active Setup Bundle + Timeline (F4, F4t, F7, F7t, F8) — exercises the shared fetch/cache design under realistic multi-page load |
| 4 | Episode Inspector (F9) + full navigation (F12) |
| 5 | Integration/close-out tests (F13), acceptance-criteria review (§9) |

Each stage ends with the `verify` skill exercising the real, running pages added in that stage.

## 9. Acceptance criteria

- **No computation modified**: zero changes to `atlas/rule_engine/`, `atlas/setup_engine/service.py`'s existing functions, `atlas/research/statistical_profiling/`, `atlas/research/setup_profiling/`.
- **Snapshot reproducibility**: A7's checksum-based test passes; the whole-file-byte-identity claim is never made.
- **Provenance clarity**: the FROZEN BASELINE badge displays `source_computation_version`; `snapshot_exporter_version` never appears as the headline value.
- **Boundary semantics**: all four `LeftBoundaryReason` cases and the `is_active`/closed-episode right-boundary distinction render correctly; no bare timestamp is ever presented as a true activation or a true ending when unresolved/still-open.
- **No silent mismatch**: the exact mismatch message renders on every FROZEN panel (including Episode Inspector's overlay) when the live selection differs.
- **No privileged key in the browser**: `grep -r "ATLAS_API_KEY" frontend/.next/static/` passes empty on a production build.
- **BFF allowlist enforced**: an unapproved path returns 404 in a test; forwarded query params are limited to the declared set per path.
- **LIVE means last closed bar**: every LIVE response's `data_as_of` is the latest bar's `occurred_at`.
- **Shared fetch**: exactly one `GET /setup-engine/episodes/live` call per polling tick across the three pages that use it.
- **Cache correctness is honestly scoped**: the TTL and its rationale are documented in-repo (this file + `atlas/live_view/cache.py`'s own docstring), not silently assumed away.
- **Known warnings preserved**: A9's coverage test passes.
- **Full test suite + Ruff clean** (backend); frontend tests pass for every component/hook that has them.

## 10. Proposed commit boundaries

1. `feat(research-export): models, serialization, known warnings` (A1, A2, A3 + tests)
2. `feat(research-export): snapshot builder with single-pass substrate + checksum split` (A4, A7, A8, A9)
3. `feat(research-export): export script` (A5)
4. `docs(research): commit RE-1/RE-2 JSON snapshots` (A6 — data-only commit)
5. `feat(api): research summary and dataset-health endpoints` (A10, A11)
6. `feat(live-view): left/right boundary projection models` (B1)
7. `feat(live-view): episode projector (boundary resolution)` (B2, B6)
8. `feat(live-view): fingerprint-and-TTL cache` (B3, B7)
9. `feat(api): setup-engine latest and live episodes endpoints` (B4, B5, B8)
10. `feat(api): register research and setup-engine routers` (C1, C2 — full suite + Ruff)
11. `test(frontend): add Vitest + React Testing Library` (F0)
12. `feat(frontend): BFF proxy with explicit allowlist` (F1, F1t)
13. `feat(frontend): typed API clients, freshness badge, mismatch banner` (F2, F3, F3t)
14. `feat(frontend): research overview and dataset health pages` (F10, F11 — Stage 1)
15. `feat(frontend): market view page` (F5 partial, F6 — Stage 2)
16. `feat(frontend): shared live-episodes hook, active setup bundle, timeline` (F4, F4t, F7, F7t, F8 — Stage 3)
17. `feat(frontend): episode inspector + navigation` (F9, F12 — Stage 4)
18. `test(frontend): integration/close-out tests` (F13 — Stage 5)

Each commit runs its own scoped tests before landing; commits 10 and 18 additionally run the full-repo suite. No commit touches `atlas/rule_engine/`, `atlas/setup_engine/service.py`'s existing functions, `atlas/research/statistical_profiling/`, or `atlas/research/setup_profiling/`.
