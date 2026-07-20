# UI v2 — Market Intelligence Dashboard: Architecture

**Status**: Design only, revision 2 (amended per review). No implementation code. Nothing in this document authorizes changing any Rule Engine, Setup Engine, RE-1, or RE-2 computation — every number the dashboard shows already exists, already has a defined meaning, and is already produced by frozen or existing code. All six previously-open decisions are resolved in §8. See `docs/ui_v2/market-intelligence-dashboard-implementation-plan.md` for the task-level plan built on this document.

## 1. Objective and non-goals

**Objective**: expose the existing Rule Engine, Setup Engine, RE-1, and RE-2 outputs through a professional operator dashboard — a visualization layer, nothing else.

**Explicit non-goals** (carried through every section below without exception):
- No trading decisions, no recommendations, no probabilities, no forecasting, no AI-generated signals, no strategy logic.
- No new statistical measures, no new aggregation, no new thresholding. If a number isn't already computed by an existing, unmodified function, it does not appear.
- No modification to `atlas.rule_engine`, `atlas.setup_engine`, `atlas.research.statistical_profiling` (RE-1), or `atlas.research.setup_profiling` (RE-2). Every one of those packages is read from, never written to or altered.

This same discipline is already established in the codebase: `RuleEngineViewer.tsx` deliberately renders a `trend_5m` value as plain neutral text with no color-coding implying good/bad, "since this viewer reports facts; judging them is explicitly out of scope." Every new component in this design follows that same posture: a `detected=True` setup is displayed as an **active structural state**, never as a signal, alert, or suggestion.

## 2. The one architectural decision everything else follows: two data-freshness tracks

The six requested sections split cleanly into two groups, and conflating them would be the single easiest way to accidentally imply something the dashboard must not imply (that a frozen historical baseline is "live," or that a live snapshot is "certified").

| Track | Sections | Source | Changes when? |
|---|---|---|---|
| **LIVE** | Market View, Active Setup Bundle, Episode Inspector (current episode), Timeline | Live production repository + existing Rule/Setup Engine evaluation functions, called fresh on every request | Every new closed bar |
| **FROZEN** | Research Overview, Dataset Health, Episode Inspector (historical distribution overlay) | The certified 97,858-bar RE-1/RE-2 baseline, frozen per `docs/market_engine/re1-phase5-freeze.md` and `docs/market_engine/re2-freeze.md` | Only when a future RE-3 (or a new RE-1/RE-2 baseline) is explicitly run and frozen |

Every screen carries a visible **LIVE** or **FROZEN BASELINE (as of `<date>`, code `<short-sha>`)** badge, sourced directly from each track's own response envelope (§6). This is the mechanism that prevents the dashboard from ever implying the frozen research baseline reflects "now," and it is reinforced by §7's symbol/timeframe mismatch rule.

### 2.1 "LIVE" means the last received, closed bar — not a tick feed

Every LIVE response is only as fresh as the most recent 5-minute bar the repository has ingested and Rule/Setup Engine has evaluated — the same `BarStatus.CLOSED`-only boundary `filter_input_states` already enforces everywhere else in this codebase. There is no sub-bar, tick-by-tick update anywhere in this design. Concretely: a LIVE response's `data_as_of` field (§6) is the `occurred_at` of the latest closed bar it used, and the dashboard's LIVE badge displays that timestamp directly (e.g. "LIVE · as of 14:35 CT"), not just a generic pulsing dot — an operator must always be able to see exactly how current the number in front of them is, and "current" here can lag real-time by up to one bar interval plus ingestion latency.

### 2.2 Why the LIVE track is not "new analytics"

RE-1 and RE-2 were explicitly designed from their first sprint for exactly this property: `build_statistical_profile()` and `build_setup_profiling_dataset()` are pure, source-agnostic functions — `list[MarketState]` in, a computed result out, with no knowledge of whether that list came from a CSV file or a repository query. Pointing that same unmodified pipeline at a **live** window (the repository's existing `get_history`/`get_range` methods) instead of a frozen CSV is the same kind of re-pointing, not a new capability.

**One boundary this amendment draws precisely**: RE-2's `SetupEpisode` was designed and frozen against a dataset where the *entire* available history is loaded — `is_left_censored` there means "this segment's own first bar," a genuine data-availability fact. A live dashboard instead loads a *bounded, arbitrary suffix* of a much longer live segment. Reusing `is_left_censored` for "the fetched window happened to start here" would silently redefine what that frozen field means. §5 introduces a separate, additive projection model specifically so this never happens — RE-2's own dataclasses are never asked to represent a concept they were not designed to represent.

## 3. Section-by-section design

### 3.1 Market View — LIVE

**Shows**: the 7 registered Rule Engine facts, the 4 registered Setup Engine setups, current active/detected states, computability state for each.

**Data source**: `GET /rule-engine/latest` (exists today, unchanged) + a new `GET /setup-engine/latest` (new route, zero new computation — wires the already-existing `atlas.setup_engine.service.setup_engine_output_to_dict()` the exact same way `rule_engine.py` already wires `rule_engine_output_to_dict()`), both wrapped in the shared response envelope from §6.

**Frontend**: extends the existing `RuleEngineViewer.tsx` pattern with a sibling `SetupEngineViewer.tsx`, plus a combined `MarketViewPage`. Uses the shared LIVE symbol/timeframe selector (§7).

### 3.2 Active Setup Bundle — LIVE

**Shows**: every setup simultaneously active right now, each one's episode duration so far, its activation timestamp (when observed — see §5), and whether the current bar is the activation bar or a continuation bar.

**Data source**: the shared `GET /setup-engine/episodes/live` endpoint (§6.2), fetched once via one shared frontend hook and reused by this section, §3.3, and §3.4 (§9).

**Frontend**: `ActiveSetupBundle.tsx` — one card per setup. A setup with an unresolved left boundary (§5) shows "active for at least N bars" instead of a false-precision activation timestamp. A setup with zero active episodes right now renders as an empty/dim state, not hidden.

### 3.3 Episode Inspector — HYBRID (live current-episode + frozen distribution overlay)

**Shows**: the current episode (live), the historical duration distribution for that setup (frozen, from RE-2), the current episode's boundary/censoring status, and recent activation history.

- **Current episode** (live): the `LiveEpisodeProjection` for the selected setup (§5) — its `left_boundary_reason`, `activation_timestamp_observed` (nullable), `duration_bars_observed`, and `is_window_truncated`. When the left boundary is unresolved, the panel reads "active for at least N bars — activation occurred before the loaded window" (query-truncated) or "active for at least N bars — activation occurred before available data begins" (a genuine RE-2-style segment boundary) — never a bare, falsely-precise timestamp.
- **Historical duration distribution** (frozen): `SetupProfile.entries[setup].all_episodes_duration` / `.fully_observed_duration` from the frozen RE-2 snapshot (§6.3), rendered as a distribution strip with the live duration-so-far plotted on the same axis — an explicit comparison against history, never a prediction. This panel carries its own mismatch check (§7): if the live selector's symbol/timeframe differs from the frozen snapshot's, the strip is replaced with the mismatch message, not silently shown against the wrong baseline.
- **Recent activation history** (live): the last N well-understood episodes for the selected setup from the same shared live fetch, each carrying its own `left_boundary_reason` (the oldest entry in a short window is often itself boundary-affected).

**Frontend**: `EpisodeInspector.tsx`, a setup-selector plus three stacked panels.

### 3.4 Timeline — LIVE

**Shows**: activation events, continuations, segment boundaries, gap markers, over a selectable recent window.

**Data source**: the same shared `GET /setup-engine/episodes/live` fetch as §3.2/§3.3. Segment boundaries and gap markers come directly from `atlas.profiling.service.segment_by_gap` applied to the live window — reused exactly as RE-1/RE-2 already use it.

**Frontend**: `Timeline.tsx` — one lane per setup. Each episode renders as a bar; a bar whose left edge has an unresolved boundary (§5) renders with a distinct visual treatment (e.g. a faded/hatched left edge) so "we don't know when this started" is visually different from "this started here." `ActivationEvent` ties render as a single vertical marker spanning every tied setup's lane, labeled with every tied name in the same alphabetical, no-ordering-implied convention RE-2's own `ActivationEvent` already uses. Segment/gap boundaries render as a distinct visual break, never mistakable for "nothing was active here."

### 3.5 Research Overview — FROZEN

**Shows**: RE-1 summary, RE-2 summary, time concentration, overlap matrix, clustering summary, transition summary.

**Data source**: `GET /research/re1/summary`, `GET /research/re2/summary` — both read pre-generated, checked-in JSON snapshots (§6.3) with **no computation, and no markdown parsing, on request**.

**Frontend**: `ResearchOverviewPage`, six panels (RE-1 summary, RE-2 summary, time concentration, overlap matrix with relationship-category badges, clustering summary, transition summary — including the expanded-destination-label denominator note carried through as on-screen help text). The whole page's identity is manifest-locked (§7) — it always shows the snapshot's own symbol/timeframe, never the live selector's.

### 3.6 Dataset Health — FROZEN

**Shows**: dataset identity, computability, segment count, known warnings, frozen version.

**Data source**: `GET /research/dataset-health` (§6.4), reading the checked-in `dataset-health.v1.json` snapshot only.

**Frontend**: `DatasetHealthPage` — dataset identity, the certification report's PASS/WARNING/FAIL table (including the `trend_1m` FAIL with its full root-cause explanation, never hidden or softened), segment count, every disclosed limitation from both freeze documents, and the frozen code version linking to the exact commit. This section is explicitly about the **research baseline's** health, not live system health — `GET /status`/`GET /health` remain the surface for live ingestion/API health, not duplicated or folded in here.

## 4. Live projection model (amendment 1) — new package, outside RE-2

RE-2's frozen `SetupEpisode` is never modified. A new, additive package projects live-window episode state into its own model, explicitly distinct from RE-2's frozen semantics.

```
atlas/live_view/
    __init__.py          - scope docstring: additive live-window projection, never
                            imported by or modifying atlas.research.setup_profiling
    models.py             - LeftBoundaryReason, LiveEpisodeProjection, LiveSetupSnapshot,
                            LiveWindowResult
    episode_projector.py   - the progressive-backward-fetch + boundary-resolution logic,
                            calling RE-2's own segment_by_gap / build_rule_engine_output_window
                            / build_setup_engine_output_window as a library, unmodified
    cache.py               - the short-lived, bar-keyed cache (§9)
```

### 4.1 `LeftBoundaryReason` (enum)

| Value | Meaning | `activation_timestamp_observed` | `is_window_truncated` |
|---|---|---|---|
| `observed_activation` | The bar immediately before the run's start is a computable, `detected=False` bar — a genuine, fully-observed activation edge, same shape as RE-2's own frozen definition. | known | `false` |
| `insufficient_data` | The bar immediately before the run's start is `InsufficientData` — RE-2's own frozen semantics already treat this as a legitimate new-episode start ("first False/absent → True"), so the timestamp is just as definite; flagged separately only so an operator can see a data-quality-adjacent boundary was involved. | known | `false` |
| `segment_start` | The run's start bar is the true first bar of its live-window `segment_by_gap` segment — a genuine market-data gap immediately precedes it, the same fact RE-2's own `is_left_censored` records for the frozen baseline. The true prior activation (if any) predates all available data, not just this query. | `null` | `false` |
| `query_window_start` | The run's start bar is the first bar the endpoint actually fetched, and it is **not** a segment boundary — more history exists, the query simply didn't reach it (or reached the hard maximum before resolving). The true activation could be arbitrarily further back. | `null` | `true` |

### 4.2 `LiveEpisodeProjection` (fields, sketch)

- `setup_name: str`
- `left_boundary_reason: LeftBoundaryReason`
- `activation_timestamp_observed: str | None` — the real activation timestamp, only when known.
- `observed_start_timestamp: str` — the first bar of this run actually present in the loaded data, always populated (this is a fact about what was loaded, not a claim about the true activation).
- `end_timestamp: str` — the current/latest bar, since the episode is still open.
- `duration_bars_observed: int` — exact when `activation_timestamp_observed` is known; a **lower bound** otherwise.
- `is_window_truncated: bool`
- `is_continuation: bool` — is the latest bar itself the activation bar, or a later bar in the same run.
- `start_state` / `end_state`: `RegisteredFactSnapshot` (RE-2's own typed snapshot shape, reused unchanged).

### 4.3 Boundary-resolution algorithm

1. Fetch an initial window of `window` bars via the existing `get_history(symbol, timeframe, limit=window)`.
2. Run the existing pipeline (`filter_input_states` → `segment_by_gap` → `build_rule_engine_output_window` → `build_setup_engine_output_window`) and locate, per setup, the run containing the latest bar (if any).
3. If that run's start position is **not** the first loaded bar, or **is** the first loaded bar but that bar is also its `segment_by_gap` segment's own first bar — the boundary is resolved (`observed_activation` / `insufficient_data` / `segment_start` as appropriate). Done.
4. Otherwise (active on the first loaded bar, and that bar is *not* a segment boundary): widen the window (double it, or fetch a fixed additional chunk — an implementation-phase parameter, §9) and repeat from step 1, up to a **hard maximum** window size.
5. If the hard maximum is reached and the boundary is still unresolved: return `query_window_start`, `is_window_truncated=true`, `duration_bars_observed` = the count of active bars actually observed (a lower bound the UI must present as such — §3.3's exact copy).

This keeps the endpoint's worst-case cost bounded (the hard maximum, not unbounded backward scanning) while genuinely trying to resolve the boundary rather than defaulting to a truncated state on every request.

## 5. Research snapshot export (amendment 2) — new package, outside RE-1/RE-2

No `serialization.py` is added to `atlas.research.statistical_profiling` or `atlas.research.setup_profiling`. A new, additive package reads their frozen dataclasses and serializes them.

```
atlas/research_export/
    __init__.py
    serialization.py      - one generic, recursive, deterministic to_jsonable() converter
                            (dataclass -> dict via dataclasses.fields(); Enum -> .value;
                            tuple/frozenset -> sorted list; Mapping -> dict with sorted
                            keys) plus a thin per-report envelope wrapper - no bespoke
                            per-dataclass function needed, and no analytics of any kind
    models.py              - SnapshotEnvelope (schema_version, source_report_code_version,
                            dataset identity, generated_at, code_version, checksum),
                            DatasetHealthSnapshot (see below)
    snapshot_builder.py     - orchestration: re-run the exact frozen pipeline
                            (run_statistical_profile.load_and_merge_states +
                            build_statistical_profile; each of RE-2's 6 build_* functions)
                            against the same frozen five-file CSV input, serialize the
                            result, write the checked-in JSON

scripts/export_research_snapshots.py   - thin CLI invoking snapshot_builder.py, the
                                          checked-in-artifact equivalent of
                                          run_statistical_profile.py / run_setup_profile.py

research/snapshots/
    re1-summary.v1.json
    re2-summary.v1.json
    dataset-health.v1.json
```

**This is reproduction, not recomputation with new meaning**: `snapshot_builder.py` calls the identical, already-frozen, already-certified functions against the identical frozen CSV inputs that produced the checked-in markdown reports. Because those functions are pure, re-running them is guaranteed to reproduce the exact same figures — the same property already exercised every time RE-1/RE-2's reports were regenerated after a certifier fix earlier in this project. A test asserts this explicitly (§ implementation plan, test strategy).

**`dataset-health.v1.json`'s one honest exception**: unlike `re1-summary`/`re2-summary` (pure serializations of existing dataclasses), the dataset-health snapshot combines two sources — `certify_historical_dataset.py`'s real, typed `CertificationResult` list (reused via its own `certify()` function, serialized the same generic way) **and** a small amount of hand-transcribed content from the two freeze documents' prose "known limitations" sections, which have no dataclass source (they are markdown text authored during RE-1/RE-2's close-out). The snapshot builder captures the latter as a small, explicitly-labeled `known_warnings: [{severity, title, detail}]` list, transcribed once and reviewed for accuracy — not mechanically derived, and documented as such in the snapshot itself via a `warnings_source: "manual_transcription"` marker, so no consumer mistakes it for a machine-derived figure.

**Envelope fields on every snapshot** (§6.3/§6.4 restate these as part of the HTTP response):
`schema_version`, `source_report_code_version` (the RE-1/RE-2 commit the underlying figures came from — usually equal to, but conceptually distinct from, the snapshot export's own commit), dataset identity (`symbol`, `timeframe`, `row_count`, `date_range`), `generated_at` (snapshot export time), `code_version` (commit the export script ran at), and a `checksum` (SHA-256 over the canonical serialized payload excluding the checksum field itself — detects accidental hand-edits or drift between the checked-in JSON and what the pipeline would currently produce).

## 6. Typed response contracts (amendment 5)

Every response — LIVE or FROZEN — shares one envelope shape:

| Field | LIVE meaning | FROZEN meaning |
|---|---|---|
| `schema_version` | contract version | contract version |
| `source_track` | `"live"` | `"frozen"` |
| `symbol` / `timeframe` | the requested live selection | the snapshot's own locked identity (§7) |
| `generated_at` | when this response was computed (now) | when the snapshot was exported |
| `data_as_of` | `occurred_at` of the latest closed bar used (§2.1) | the frozen dataset's own end timestamp (fixed) |
| `code_version` | current running backend commit | the frozen commit the snapshot was built from |
| `warnings` | e.g. `["window truncated for sustained_displacement_streak"]` | e.g. carried-forward certification caveats |

### 6.1 `GET /setup-engine/latest`

Envelope (`source_track: "live"`) + `setups: [{name, status: "computed" | "insufficient_data", detected?, severity?, reason?, evidence?}]` — the existing `setup_engine_output_to_dict()` shape, unchanged, wrapped in the envelope.

### 6.2 `GET /setup-engine/episodes/live`

Envelope + `window: {requested, actually_used}` (the actually-used value can exceed `requested` after progressive widening, §4.3) + per setup:
- `current_episode: LiveEpisodeProjection | null` (§4.2)
- `recent_episodes: LiveEpisodeProjection[]` (bounded count)
- `computability: ComputabilityProfile`-shaped summary for the window

Plus window-level `segments: [{segment_id, start_timestamp, end_timestamp | null}]` and `activation_events: [{timestamp, activated_setups}]` for §3.4's Timeline.

### 6.3 `GET /research/re1/summary`, `GET /research/re2/summary`

Envelope (`source_track: "frozen"`) + the underlying `StatisticalProfile` / RE-2 report dataclasses, serialized via `atlas.research_export.serialization`, unchanged in shape from what `research/RE1_*.md`/`RE2_*.md` already describe in prose/tables.

### 6.4 `GET /research/dataset-health`

Envelope (`source_track: "frozen"`) + dataset identity, `segment_count`, `certification: {checks_run, pass_count, warning_count, fail_count, verdict, checks: [...]}`, `known_warnings: [{severity, title, detail}]`, `frozen_version: {code_version, frozen_at}`.

## 7. Symbol/timeframe behavior across tracks (amendment 4)

- **LIVE sections** (Market View, Active Setup Bundle, Episode Inspector's live panels, Timeline) share **one** selector, defined once at a layout level, driving every LIVE fetch.
- **FROZEN sections** (Research Overview, Dataset Health) are **manifest-locked**: they always render the identity embedded in their own snapshot envelope (today, always `MNQ1!` / `5m`) — never the live selector's value, and never silently relabeled to match it.
- Every FROZEN panel, and Episode Inspector's frozen distribution-overlay sub-panel specifically, compares the live selector's `(symbol, timeframe)` against the snapshot's own. On a mismatch, the panel replaces its normal content with a visible message, verbatim in form:

  > Frozen research baseline is available for MNQ1! / 5m.
  > Current live selection: `<live symbol>` / `<live timeframe>`.

  No partial rendering of frozen numbers under a mismatched banner, and no automatic switching of either selector to "fix" the mismatch — the operator decides.

## 8. Resolution of the six previously-open decisions

1. **Live window default/max** — default `window` sized to comfortably cover a typical operator session's lookback (implementation-plan detail, §ops); hard maximum enforced per §4.3's boundary-resolution algorithm so cost stays bounded regardless of how far back progressive widening searches.
2. **Snapshot production mechanism** — resolved by amendment 2: `atlas/research_export/` + `scripts/export_research_snapshots.py`, run manually alongside `run_statistical_profile.py`/`run_setup_profile.py` whenever RE-1/RE-2 are regenerated (i.e., never on a schedule — only when a human explicitly re-freezes the baseline), checked in like the markdown reports it mirrors.
3. **Auth pattern** — resolved by amendment 3 (§ implementation plan, Authentication flow): Next.js Backend-for-Frontend via route handlers and a server-only `ATLAS_API_KEY`, confirmed feasible today (`frontend/` runs `next build && next start`, a real Node server, not a static export). `RuleEngineViewer.tsx`'s older manual key-entry form and the rest of the app's `NEXT_PUBLIC_API_KEY` pattern are both left as-is for existing pages — a disclosed, deliberately-deferred inconsistency, not fixed by UI v2.
4. **Chart library specifics** — `recharts` (already a dependency) for the time-concentration bars and any curve-shaped visuals; the Timeline's lane/bar layout and the duration distribution strip are simple absolutely-positioned `div` compositions (matching the wireframe), since `recharts`' primitives are built for cartesian/pie charts, not interval timelines — a frontend implementation choice with no architectural consequence.
5. **Shared vs per-page selector** — resolved by §7: one shared selector for LIVE, manifest-locked identity for FROZEN, with an explicit mismatch banner rather than either silently switching.
6. **Snapshot mechanism: typed serialization vs markdown parsing** — resolved by amendment 2 in favor of typed serialization (§5) — markdown parsing is explicitly rejected as the on-request path; `research.py`'s routes read only pre-generated JSON.

## 9. Shared live fetch and caching (amendment 5)

**Frontend**: Active Setup Bundle, Episode Inspector, and Timeline all consume `GET /setup-engine/episodes/live` through **one** TanStack Query hook (`useLiveEpisodes(symbol, timeframe, window)`) with a shared, deterministic query key — React Query's own cache then naturally dedupes across the three pages/components without any bespoke coordination code, the same way the existing SSE-assisted-polling pattern already works for `ActivityTimeline.tsx`.

**Backend**: `atlas/live_view/cache.py` holds a small, short-lived cache keyed by `(symbol, timeframe, window, latest_bar_timestamp)`. Because the *only* thing that can change the pipeline's result for a fixed `(symbol, timeframe, window)` is a new closed bar arriving, keying directly on the latest bar's own timestamp (obtained via the existing, cheap `get_latest()`) makes cache invalidation exact and free of TTL guesswork: a request with the same key as an existing entry returns it as-is; a new bar changes the key and naturally misses, recomputing once. This means N simultaneous dashboard requests for the same market, arriving before any one of them completes, still only run the pipeline once in the common case (a small in-flight-request coalescing detail for the implementation plan).

## 10. Frontend structure

```
frontend/src/app/
  market-view/page.tsx            -> 3.1
  active-setups/page.tsx          -> 3.2
  episodes/page.tsx                -> 3.3
  timeline/page.tsx                -> 3.4
  research/page.tsx                -> 3.5
  dataset-health/page.tsx          -> 3.6
  api/proxy/...                    -> BFF route handlers (§ implementation plan)

frontend/src/components/
  SetupEngineViewer.tsx
  ActiveSetupBundle.tsx
  EpisodeInspector.tsx
  EpisodeDurationStrip.tsx
  Timeline.tsx
  ResearchOverviewPanels/
  DatasetHealthPanels/
  FreshnessBadge.tsx                (LIVE "as of <time>" / FROZEN BASELINE, §2)
  MismatchBanner.tsx                (§7)

frontend/src/lib/
  setupEngineApi.ts
  researchApi.ts
  useLiveEpisodes.ts                 (the one shared hook, §9)
```

No new stack, no new dependencies beyond what's already installed. Every new component uses the existing CSS custom properties (`--surface`, `--border`, `--foreground`, `--muted`, `--ok`/`--warn`/`--danger`) and the existing component library's conventions.

## 11. Section-to-source traceability (summary table)

| Section | Track | Primary data source(s) | New backend work |
|---|---|---|---|
| 1. Market View | LIVE | `GET /rule-engine/latest` (exists), `GET /setup-engine/latest` (new) | New route only |
| 2. Active Setup Bundle | LIVE | `GET /setup-engine/episodes/live` (new, shared fetch) | New route, `atlas/live_view/` |
| 3. Episode Inspector | HYBRID | Same live endpoint + `GET /research/re2/summary` (frozen) | Both, plus §7 mismatch check |
| 4. Timeline | LIVE | `GET /setup-engine/episodes/live` (new, shared fetch) | Same endpoint as §2 |
| 5. Research Overview | FROZEN | `GET /research/re1/summary`, `GET /research/re2/summary` (new, static reads) | New routes + `atlas/research_export/` |
| 6. Dataset Health | FROZEN | `GET /research/dataset-health` (new, static reads) | New route + same export package |
