# UI v2 — Market Intelligence Dashboard: Architecture

**Status**: Design approved, revision 3 (amended per second review). Implementation is now in progress, in the dependency order this document and its companion implementation plan (`docs/ui_v2/market-intelligence-dashboard-implementation-plan.md`) establish. Nothing in this document authorizes changing any Rule Engine, Setup Engine, RE-1, or RE-2 computation — every number the dashboard shows already exists, already has a defined meaning, and is already produced by frozen or existing code.

## 1. Objective and non-goals

**Objective**: expose the existing Rule Engine, Setup Engine, RE-1, and RE-2 outputs through a professional operator dashboard — a visualization layer, nothing else.

**Explicit non-goals** (carried through every section below without exception):
- No trading decisions, no recommendations, no probabilities, no forecasting, no AI-generated signals, no strategy logic.
- No new statistical measures, no new aggregation, no new thresholding. If a number isn't already computed by an existing, unmodified function, it does not appear.
- No modification to `atlas.rule_engine`, `atlas.setup_engine`, `atlas.research.statistical_profiling` (RE-1), or `atlas.research.setup_profiling` (RE-2). Every one of those packages is read from, never written to or altered.

This same discipline is already established in the codebase: `RuleEngineViewer.tsx` deliberately renders a `trend_5m` value as plain neutral text with no color-coding implying good/bad, "since this viewer reports facts; judging them is explicitly out of scope." Every new component in this design follows that same posture: a `detected=True` setup is displayed as an **active structural state**, never as a signal, alert, or suggestion.

## 2. The one architectural decision everything else follows: two data-freshness tracks

| Track | Sections | Source | Changes when? |
|---|---|---|---|
| **LIVE** | Market View, Active Setup Bundle, Episode Inspector (current episode), Timeline | Live production repository + existing Rule/Setup Engine evaluation functions, called fresh on every request | Every new closed bar |
| **FROZEN** | Research Overview, Dataset Health, Episode Inspector (historical distribution overlay) | The certified 97,858-bar RE-1/RE-2 baseline, frozen per `docs/market_engine/re1-phase5-freeze.md` and `docs/market_engine/re2-freeze.md` | Only when a future RE-3 (or a new RE-1/RE-2 baseline) is explicitly run and frozen |

Every screen carries a visible **LIVE** or **FROZEN BASELINE (as of `<date>`, computation `<source_computation_version short-sha>`)** badge (§6, §5.2) — the mechanism that prevents the dashboard from ever implying the frozen research baseline reflects "now," reinforced by §8's symbol/timeframe mismatch rule.

### 2.1 "LIVE" means the last received, closed bar — not a tick feed

Every LIVE response is only as fresh as the most recent 5-minute bar the repository has ingested and Rule/Setup Engine has evaluated. There is no sub-bar, tick-by-tick update anywhere in this design. A LIVE response's `data_as_of` field (§6) is the `occurred_at` of the latest closed bar it used, and the UI displays that timestamp directly (e.g. "LIVE · as of 14:35 CT"), not just a generic pulsing dot.

An active (still-open) episode gets the identical framing at the episode level (§4.2): its right boundary is never presented as a true ending, only as "active through last closed bar."

### 2.2 Why the LIVE track is not "new analytics"

`build_statistical_profile()` and `build_setup_profiling_dataset()` are pure, source-agnostic functions — `list[MarketState]` in, a computed result out, with no knowledge of whether that list came from a CSV file or a repository query. Pointing that same unmodified pipeline at a **live** window (the repository's existing `get_history`/`get_range` methods) instead of a frozen CSV is the same kind of re-pointing, not a new capability.

**Two boundaries this design draws precisely, in both directions**: RE-2's `SetupEpisode` was designed and frozen against a dataset where the *entire* available history is loaded — both its `is_left_censored` and `termination_reason` fields describe facts about a *complete* dataset. A live dashboard instead loads a *bounded, arbitrary suffix* of a much longer, still-growing live segment, and the "current" episode for an active setup has, by definition, no true right boundary yet. Reusing RE-2's fields for either concept would silently redefine what they mean. §4 introduces a separate, additive projection model — with its own left-boundary AND right-boundary semantics — specifically so this never happens.

## 3. Section-by-section design

### 3.1 Market View — LIVE

**Shows**: the 7 registered Rule Engine facts, the 4 registered Setup Engine setups, current active/detected states, computability state for each.

**Data source**: `GET /rule-engine/latest` (exists today, unchanged) + a new `GET /setup-engine/latest` (new route, zero new computation — wires the already-existing `atlas.setup_engine.service.setup_engine_output_to_dict()` the exact same way `rule_engine.py` already wires `rule_engine_output_to_dict()`), both wrapped in the shared response envelope from §6.

**Frontend**: extends the existing `RuleEngineViewer.tsx` pattern with a sibling `SetupEngineViewer.tsx`, plus a combined `MarketViewPage`. Uses the shared LIVE symbol/timeframe selector (§8).

### 3.2 Active Setup Bundle — LIVE

**Shows**: every setup simultaneously active right now, each one's episode duration so far, its activation timestamp (when observed — §4.1), and whether the current bar is the activation bar or a continuation bar.

**Data source**: the shared `GET /setup-engine/episodes/live` endpoint (§6.2), fetched once via one shared frontend hook and reused by this section, §3.3, and §3.4 (§9).

**Frontend**: `ActiveSetupBundle.tsx` — one card per setup. A setup with an unresolved left boundary shows "active for at least N bars" instead of a false-precision activation timestamp; every active card reads "active through last closed bar," never a bare end timestamp (§4.2).

### 3.3 Episode Inspector — HYBRID (live current-episode + frozen distribution overlay)

**Shows**: the current episode (live), the historical duration distribution for that setup (frozen, from RE-2), the current episode's boundary/censoring status, and recent activation history.

- **Current episode** (live): the `LiveEpisodeProjection` for the selected setup (§4) — left-boundary reason, right-boundary/`is_active` status, and duration. When the left boundary is unresolved, the panel reads "active for at least N bars — activation occurred before the loaded window" (query-truncated) or "...before available data begins" (a genuine segment boundary). While `is_active=true`, the panel reads "active through last closed bar" and never shows `end_timestamp_observed` (null) as if it were a real end.
- **Historical duration distribution** (frozen): `SetupProfile.entries[setup].all_episodes_duration` / `.fully_observed_duration` from the frozen RE-2 snapshot (§5), rendered as a distribution strip with the live duration-so-far plotted on the same axis — an explicit comparison against history, never a prediction. This panel carries its own mismatch check (§8): a symbol/timeframe mismatch replaces the strip with the mismatch message, never silently shown against the wrong baseline.
- **Recent activation history** (live): the last N *closed* episodes for the selected setup from the same shared live fetch, each preserving its real `termination_reason` (§4.2) — these are historical, well-understood episodes, not the currently-open one.

**Frontend**: `EpisodeInspector.tsx`, a setup-selector plus three stacked panels.

### 3.4 Timeline — LIVE

**Shows**: activation events, continuations, segment boundaries, gap markers, over a selectable recent window.

**Data source**: the same shared `GET /setup-engine/episodes/live` fetch as §3.2/§3.3. Segment boundaries and gap markers come directly from `atlas.profiling.service.segment_by_gap` applied to the live window.

**Frontend**: `Timeline.tsx` — one lane per setup. A bar whose left edge has an unresolved boundary renders with a distinct visual treatment (faded/hatched left edge); the currently-active episode's bar (if any) renders with an open/unterminated right edge (e.g. a subtle animated or dashed cap), distinct from every closed episode's bar, which has a definite right edge. `ActivationEvent` ties render as a single vertical marker spanning every tied setup's lane, alphabetically labeled with no ordering implied. Segment/gap boundaries render as a distinct visual break, never mistakable for "nothing was active here."

### 3.5 Research Overview — FROZEN

**Shows**: RE-1 summary, RE-2 summary, time concentration, overlap matrix, clustering summary, transition summary.

**Data source**: `GET /research/re1/summary`, `GET /research/re2/summary` — both read pre-generated, checked-in JSON snapshots (§5) with **no computation, and no markdown parsing, on request**.

**Frontend**: `ResearchOverviewPage`, six panels. The whole page's identity is manifest-locked (§8) and its freshness badge shows `source_computation_version` (§5.2), not the exporter's own version.

### 3.6 Dataset Health — FROZEN

**Shows**: dataset identity, computability, segment count, known warnings, frozen version.

**Data source**: `GET /research/dataset-health` (§6.4), reading the checked-in `dataset-health.v1.json` snapshot only.

**Frontend**: `DatasetHealthPage` — dataset identity, the certification report's PASS/WARNING/FAIL table, segment count, every disclosed limitation as a typed, traceable `KnownWarning` (§5.3), and the frozen `source_computation_version` linking to the exact commit. This section is explicitly about the **research baseline's** health, not live system health — `GET /status`/`GET /health` remain the surface for live ingestion/API health, not duplicated or folded in here.

## 4. Live projection model — new package, outside RE-2

RE-2's frozen `SetupEpisode` is never modified. A new, additive package projects live-window episode state into its own model, with **both** left-boundary and right-boundary semantics distinct from RE-2's frozen ones.

```
atlas/live_view/
    __init__.py           - scope docstring: additive live-window projection, never
                            imported by or modifying atlas.research.setup_profiling
    models.py              - LeftBoundaryReason, LiveTerminationReason,
                            LiveEpisodeProjection, LiveSetupSnapshot, LiveWindowResult
    episode_projector.py    - progressive-backward-fetch + left-boundary resolution,
                            plus right-boundary (is_active / termination) determination,
                            calling RE-2's own segment_by_gap / build_rule_engine_output_window
                            / build_setup_engine_output_window as a library, unmodified
    cache.py                - the bar-and-fingerprint-keyed cache with a bounded TTL (§9)
```

### 4.1 Left-boundary semantics

`LeftBoundaryReason` (enum):

| Value | Meaning | `activation_timestamp_observed` | `is_window_truncated` |
|---|---|---|---|
| `observed_activation` | The bar immediately before the run's start is a computable, `detected=False` bar — a genuine, fully-observed activation edge. | known | `false` |
| `insufficient_data` | The bar immediately before the run's start is `InsufficientData` — RE-2's own frozen semantics already treat this as a legitimate new-episode start, so the timestamp is just as definite; flagged separately for operator visibility into a data-quality-adjacent boundary. | known | `false` |
| `segment_start` | The run's start bar is the true first bar of its live-window `segment_by_gap` segment — a genuine market-data gap immediately precedes it. The true prior activation (if any) predates all available data, not just this query. | `null` | `false` |
| `query_window_start` | The run's start bar is the first bar the endpoint actually fetched, and it is **not** a segment boundary. The true activation could be arbitrarily further back. | `null` | `true` |

Resolution algorithm (episode_projector.py): fetch an initial window, evaluate, and if the active run's start is the first loaded bar and not a segment boundary, progressively widen (double, or a fixed increment) up to a hard maximum before falling back to `query_window_start`. Worst-case cost is bounded by the hard maximum, not unbounded backward scanning.

### 4.2 Right-boundary semantics

Distinguishes a still-open episode from a closed one — absent from the original design, added here because the left-boundary model alone left "is this still going" implicit.

`LiveTerminationReason` (enum, scoped to `atlas.live_view` — deliberately **not** RE-2's own `TerminationReason`: a live window has no `dataset_end` concept, and needs a genuine "still open" state RE-2's frozen model never has, since every historical `SetupEpisode` is closed by construction):

- `became_false` — the bar after the run's last active bar is a computable `False`.
- `insufficient_data` — the bar after the run's last active bar is `InsufficientData`.
- `segment_end` — the run is active through its own segment's last bar (a gap follows within the window) — right-censored in the same spirit as RE-2's own concept, but scoped to what the live window can actually observe.
- (absent / `null`) — the run is still active as of the latest evaluated bar. This is not a value in the enum; it is represented by `is_active=true` with `termination_reason=null`, so "still open" can never be confused with a real, named termination reason.

`LiveEpisodeProjection` right-boundary fields (added to the left-boundary fields already specified in the previous revision):

- `is_active: bool` — is this run still open as of the latest evaluated bar?
- `last_observed_timestamp: str` — the last bar of this run actually present in the loaded data, always populated (true whether the run is open or closed).
- `end_timestamp_observed: str | None` — the real end timestamp. **`null` whenever `is_active=true`** — never presented as a true ending. Equal to `last_observed_timestamp` once genuinely closed.
- `termination_reason: "became_false" | "insufficient_data" | "segment_end" | None` — `null` whenever `is_active=true`.
- `right_boundary_observed: bool` — `true` only when `is_active=false` (a closed, fully-understood-within-the-window episode); `false` while still open, since "boundary" has no meaning yet for an ongoing run.

**UI rule**: while `is_active=true`, every surface (§3.2–§3.4) renders "active through last closed bar," never `end_timestamp_observed` (which is `null`) and never treats `last_observed_timestamp` as a stated end. `recent_episodes` (§6.2) — the closed, historical entries — always carry their real `termination_reason` and `end_timestamp_observed`, unmodified from what was actually observed.

## 5. Research snapshot export — new package, outside RE-1/RE-2

No `serialization.py` is added to `atlas.research.statistical_profiling` or `atlas.research.setup_profiling`. A new, additive package reads their frozen dataclasses and serializes them.

```
atlas/research_export/
    __init__.py
    serialization.py       - one generic, recursive, deterministic to_jsonable() converter
                            (dataclass -> dict via dataclasses.fields(); Enum -> .value;
                            tuple/frozenset -> sorted list; Mapping -> dict with sorted
                            keys); canonical_json() (stable key ordering, no floating
                            whitespace) for checksum computation
    models.py               - SnapshotEnvelope (provenance fields, §5.2), KnownWarning
                            (§5.3)
    known_warnings.py        - the hand-curated, typed KNOWN_BASELINE_WARNINGS tuple
    snapshot_builder.py       - orchestration: load/merge the frozen CSVs and build the
                            RE-1/RE-2 aligned substrate EXACTLY ONCE per export (§5.4),
                            serialize the deterministic payload, compute the content
                            checksum, attach export metadata

scripts/export_research_snapshots.py

live/research/snapshots/
    re1-summary.v1.json
    re2-summary.v1.json
    dataset-health.v1.json
```

Every snapshot file has two top-level parts, kept structurally separate so reproducibility is checkable without depending on run-to-run-identical wall-clock output (§5.1):

```
{
  "envelope": { ...provenance + export metadata, §5.2... },
  "payload": { ...the deterministic report content, §5.1... }
}
```

### 5.1 Deterministic payload and the reproducibility test

`envelope.exported_at` (when this specific export run happened) is the **only** field in a snapshot file expected to differ between two runs of the exporter against the same frozen inputs — everything under `payload` must be byte-identical, because it is a pure function of already-frozen, already-certified code and data.

```
content_checksum = SHA256(canonical_json(payload))
```

computed **excluding** `envelope.exported_at` and excluding `content_checksum` itself (it cannot check itself). The reproducibility test:
1. Rebuilds `payload` fresh from the frozen CSVs via `snapshot_builder`.
2. Serializes it via `canonical_json()`.
3. Computes a fresh checksum and asserts it equals the checked-in file's `envelope.content_checksum`.
4. Separately asserts the envelope's *shape* (every required field present, correct type) — never requires `exported_at` (or any other export-metadata field) to match between runs.

A snapshot file is never required to be byte-for-byte identical to a previous export as a whole; only its `payload` (via the checksum) is held to that standard.

### 5.2 Provenance fields (envelope)

One ambiguous `code_version` is not used. Every snapshot's envelope carries:

| Field | Meaning |
|---|---|
| `schema_version` | This envelope/payload contract's own version. |
| `source_computation_version` | The git commit of the RE-1/RE-2 **code that computed the figures** — read directly from the underlying `RunManifest.code_version` already embedded in the frozen dataclass being serialized, never re-derived. **This is what the dashboard's FROZEN BASELINE badge displays.** |
| `snapshot_exporter_version` | The git commit of `atlas/research_export/` itself at export time — the code that merely serialized the (already-computed) figures to JSON. Shown only in detail/debug views, never as the headline badge value. |
| `source_freeze_document` | e.g. `docs/market_engine/re1-phase5-freeze.md` — the document that certifies this baseline is frozen. |
| `source_report_versions` | Which `research/RE1_*.md` / `RE2_*.md` files this snapshot mirrors, and their own embedded `code_version` (normally identical to `source_computation_version`, checked explicitly rather than assumed). |
| `content_checksum` | §5.1. |
| `exported_at` | Wall-clock export time — the one genuinely dynamic field. |
| `dataset_identity` | symbol, timeframe, row_count, date_range — read from the same `RunManifest`. |

### 5.3 Typed, traceable warnings

`known_warnings.py` defines a `KnownWarning` dataclass and a hand-curated `KNOWN_BASELINE_WARNINGS: tuple[KnownWarning, ...]` constant, kept outside RE-1/RE-2 but no longer a bare `{severity, title, detail}` shape:

```
KnownWarning = {
  id: str,                 # stable, e.g. "trend-1m-lookback-limit"
  severity: "warning" | "fail",
  title: str,
  detail: str,
  source_document: str,     # e.g. "docs/market_engine/re1-phase5-freeze.md"
  source_section: str,      # e.g. "Known limitations, item 1"
}
```

A focused test asserts the full expected set of warning `id`s is present in `dataset-health.v1.json` — a warning silently dropped during a future refactor fails the build, not just a human reading the JSON.

### 5.4 Snapshot builder: single evaluation pass

`snapshot_builder.py` calls `atlas.research.setup_profiling.service.build_setup_profiling_dataset()` **exactly once** per export run, and passes the same resulting `dataset` object to all six of RE-2's `build_*` report functions — mirroring the pattern `scripts/run_setup_profile.py` already established (it builds `dataset` once, then loops `REPORT_WRITERS` over it). The complete Rule/Setup Engine evaluation pipeline is never re-run per report. A test asserts this call count directly (a spy/counter on `build_setup_profiling_dataset` recording exactly one invocation for a full six-report export). RE-1's `build_statistical_profile()` already computes its entire `StatisticalProfile` in one call internally, so no equivalent risk exists on that side — noted for completeness, not because it needed a fix.

## 6. Typed response contracts

Every response — LIVE or FROZEN — shares one envelope shape:

| Field | LIVE meaning | FROZEN meaning |
|---|---|---|
| `schema_version` | contract version | contract version |
| `source_track` | `"live"` | `"frozen"` |
| `symbol` / `timeframe` | the requested live selection | the snapshot's own locked identity (§8) |
| `generated_at` | when this response was computed (now) | `envelope.exported_at` from the snapshot |
| `data_as_of` | `occurred_at` of the latest closed bar used (§2.1) | the frozen dataset's own end timestamp (fixed) |
| `code_version` | current running backend commit | `source_computation_version` (§5.2) — **not** `snapshot_exporter_version` |
| `warnings` | e.g. `["window truncated for sustained_displacement_streak"]` | carried-forward `KnownWarning`s relevant to this response |

### 6.1 `GET /setup-engine/latest`

Envelope (`source_track: "live"`) + `setups: [{name, status: "computed" | "insufficient_data", detected?, severity?, reason?, evidence?}]` — the existing `setup_engine_output_to_dict()` shape, unchanged, wrapped in the envelope.

### 6.2 `GET /setup-engine/episodes/live`

Envelope + `window: {requested, actually_used}` + per setup:
- `current_episode: LiveEpisodeProjection | null` (§4)
- `recent_episodes: LiveEpisodeProjection[]` — always closed (`is_active=false`), always carrying a real `termination_reason`
- `computability`: `ComputabilityProfile`-shaped summary for the window

Plus window-level `segments: [{segment_id, start_timestamp, end_timestamp | null}]` and `activation_events: [{timestamp, activated_setups}]` for §3.4's Timeline.

### 6.3 `GET /research/re1/summary`, `GET /research/re2/summary`

Envelope (`source_track: "frozen"`) + the underlying `StatisticalProfile` / RE-2 report dataclasses, serialized via `atlas.research_export.serialization`, unchanged in shape.

### 6.4 `GET /research/dataset-health`

Envelope (`source_track: "frozen"`) + dataset identity, `segment_count`, `certification: {...}`, `known_warnings: KnownWarning[]` (§5.3), `frozen_version: {source_computation_version, exported_at}`.

## 8. Symbol/timeframe behavior across tracks

- **LIVE sections** share **one** selector, defined once at a layout level.
- **FROZEN sections** are **manifest-locked**: they always render the identity embedded in their own snapshot envelope (today, always `MNQ1!` / `5m`) — never the live selector's value.
- Every FROZEN panel, and Episode Inspector's frozen distribution-overlay sub-panel specifically, compares the live selector's `(symbol, timeframe)` against the snapshot's own. On a mismatch:

  > Frozen research baseline is available for MNQ1! / 5m.
  > Current live selection: `<live symbol>` / `<live timeframe>`.

  No partial rendering of frozen numbers under a mismatched banner, and no automatic switching of either selector.

## 9. Shared live fetch and caching

**Frontend**: Active Setup Bundle, Episode Inspector, and Timeline all consume `GET /setup-engine/episodes/live` through **one** TanStack Query hook (`useLiveEpisodes(symbol, timeframe, window)`) with a shared, deterministic query key.

**Backend cache** (`atlas/live_view/cache.py`) — corrected: `(symbol, timeframe, window, latest_bar_timestamp)` alone is **not** sufficient for correctness. A backfill or correction to a bar *inside* the window that isn't the *latest* bar changes the correct result without changing that key. The cache key is therefore:

```
(symbol, timeframe, window, latest_bar_timestamp,
 rule_engine_registry_fingerprint, setup_engine_registry_fingerprint)
```

- `rule_engine_registry_fingerprint` / `setup_engine_registry_fingerprint`: a hash over each registry's `(name, definition_version)` pairs — cheap, real, available today (both registries are static tuples with per-fact/per-setup `version` strings already). Protects against silently serving a stale result if a future multi-process deployment runs mismatched code versions; in a single-process deployment these can only change on a restart, which already clears the in-process cache, so this is a correctness-by-construction addition, not a workaround for an observed failure mode.
- **This project has no repository-level data revision or "last modified" marker today** (`get_latest`/`get_history`/`get_range`/`ingest`/`ping` — no version field). The bar-and-fingerprint key therefore still cannot detect a backfill/correction to a non-latest historical bar. This residual gap is closed by a **short TTL** (§ implementation plan, caching limits) applied in addition to the key, not instead of it, and is documented here as a known, bounded limitation — not claimed as an unconditional correctness guarantee.
- **Explicit invalidation**: `cache.invalidate_all()` is exposed for any future in-process caller (e.g. a correction tool that runs inside the same server process) to call directly. No new HTTP admin endpoint is added in this phase; a process restart remains the primary invalidation path today, bounded by the TTL in between.

In-flight request coalescing (one computation per cache key even under concurrent requests) is retained from the original design.

## 10. Frontend structure

```
frontend/src/app/
  market-view/page.tsx
  active-setups/page.tsx
  episodes/page.tsx
  timeline/page.tsx
  research/page.tsx
  dataset-health/page.tsx
  api/proxy/[...path]/route.ts   -> BFF route handler, explicit allowlist only

frontend/src/components/
  SetupEngineViewer.tsx
  ActiveSetupBundle.tsx
  EpisodeInspector.tsx
  EpisodeDurationStrip.tsx
  Timeline.tsx
  ResearchOverviewPanels/
  DatasetHealthPanels/
  FreshnessBadge.tsx
  MismatchBanner.tsx

frontend/src/lib/
  setupEngineApi.ts
  researchApi.ts
  useLiveEpisodes.ts
```

No new stack, no new dependencies beyond what's already installed, plus a minimal test harness (Vitest + React Testing Library) — new to this repo, introduced with the BFF/client foundation stage, not deferred (implementation plan §7).

## 11. Section-to-source traceability (summary table)

| Section | Track | Primary data source(s) | New backend work |
|---|---|---|---|
| 1. Market View | LIVE | `GET /rule-engine/latest` (exists), `GET /setup-engine/latest` (new) | New route only |
| 2. Active Setup Bundle | LIVE | `GET /setup-engine/episodes/live` (new, shared fetch) | New route, `atlas/live_view/` |
| 3. Episode Inspector | HYBRID | Same live endpoint + `GET /research/re2/summary` (frozen) | Both, plus §8 mismatch check |
| 4. Timeline | LIVE | `GET /setup-engine/episodes/live` (new, shared fetch) | Same endpoint as §2 |
| 5. Research Overview | FROZEN | `GET /research/re1/summary`, `GET /research/re2/summary` (new, static reads) | New routes + `atlas/research_export/` |
| 6. Dataset Health | FROZEN | `GET /research/dataset-health` (new, static reads) | New route + same export package |
