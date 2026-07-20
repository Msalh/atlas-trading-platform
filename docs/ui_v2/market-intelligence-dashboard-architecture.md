# UI v2 — Market Intelligence Dashboard: Architecture

**Status**: Design only. No implementation code. Nothing in this document authorizes changing any Rule Engine, Setup Engine, RE-1, or RE-2 computation — every number the dashboard shows already exists, already has a defined meaning, and is already produced by frozen or existing code.

## 1. Objective and non-goals

**Objective**: expose the existing Rule Engine, Setup Engine, RE-1, and RE-2 outputs through a professional operator dashboard — a visualization layer, nothing else.

**Explicit non-goals** (carried through every section below without exception):
- No trading decisions, no recommendations, no probabilities, no forecasting, no AI-generated signals, no strategy logic.
- No new statistical measures, no new aggregation, no new thresholding. If a number isn't already computed by an existing, unmodified function, it does not appear.
- No modification to `atlas.rule_engine`, `atlas.setup_engine`, `atlas.research.statistical_profiling` (RE-1), or `atlas.research.setup_profiling` (RE-2). Every one of those packages is read from, never written to or altered.

This same discipline is already established in the codebase: `RuleEngineViewer.tsx` (the one existing Rule Engine page) deliberately renders a `trend_5m` value as plain neutral text with no color-coding implying good/bad, "since this viewer reports facts; judging them is explicitly out of scope." Every new component in this design follows that same posture: a `detected=True` setup is displayed as an **active structural state**, never as a signal, alert, or suggestion.

## 2. The one architectural decision everything else follows: two data-freshness tracks

The six requested sections split cleanly into two groups, and conflating them would be the single easiest way to accidentally imply something the dashboard must not imply (that a frozen historical baseline is "live," or that a live snapshot is "certified").

| Track | Sections | Source | Changes when? |
|---|---|---|---|
| **LIVE** | Market View, Active Setup Bundle, Episode Inspector (current episode), Timeline | Live production repository + existing Rule/Setup Engine evaluation functions, called fresh on every request | Every new bar |
| **FROZEN** | Research Overview, Dataset Health, Episode Inspector (historical distribution overlay) | The certified 97,858-bar RE-1/RE-2 baseline, frozen per `docs/market_engine/re1-phase5-freeze.md` and `docs/market_engine/re2-freeze.md` | Only when a future RE-3 (or a new RE-1/RE-2 baseline) is explicitly run and frozen |

Every screen in this dashboard carries a visible **LIVE** or **FROZEN BASELINE (as of `<date>`, code `<short-sha>`)** badge, sourced directly from each track's own manifest. This is not a cosmetic detail — it is the mechanism that prevents the dashboard from ever implying the frozen research baseline reflects "now."

### Why the LIVE track is not "new analytics"

RE-1 and RE-2 were explicitly designed from their first sprint for exactly this property: `build_statistical_profile()` and `build_setup_profiling_dataset()` are pure, source-agnostic functions — `list[MarketState]` in, a computed result out, with no knowledge of whether that list came from a CSV file or a repository query. Sprint RE-1's own mid-course correction stated this outright: *"ensure the architecture is designed so that the exact same pipeline can later be rerun unchanged on a much larger historical dataset."* Pointing that same unmodified pipeline at a **live** window (the repository's existing `get_history`/`get_range` methods, already implemented, already used elsewhere) instead of a frozen CSV is the same kind of re-pointing, not a new capability. The Episode Inspector's "current episode," "activation timestamp," and "continuation status" are `SetupEpisode` fields that already exist in `atlas.research.setup_profiling.models` — this dashboard is the first thing to *read* them for a live window, not a redefinition of what they mean.

## 3. Section-by-section design

### 3.1 Market View — LIVE

**Shows**: the 7 registered Rule Engine facts, the 4 registered Setup Engine setups, current active/detected states, computability state for each.

**Data source**: `GET /rule-engine/latest` (exists today, unchanged) + a new `GET /setup-engine/latest` (new route, zero new computation — wires the already-existing `atlas.setup_engine.service.setup_engine_output_to_dict()` the exact same way `rule_engine.py` already wires `rule_engine_output_to_dict()`).

**Frontend**: extends the existing `RuleEngineViewer.tsx` pattern (already renders all 7 facts with computability state via `status: "computed" | "insufficient_data"` and a `reason` string) with a sibling `SetupEngineViewer.tsx` following the identical layout convention, plus a combined `MarketViewPage` that places both side by side. No new visual language is invented — same card/row structure, same `FactValue`-style neutral rendering extended to setups (`detected: true/false` rendered the same way `trend_5m`'s categorical value is today: plain text, no implied judgment).

**Wireframe reference**: §5, Section 1.

### 3.2 Active Setup Bundle — LIVE

**Shows**: every setup simultaneously active right now, each one's episode duration so far, its activation timestamp, and whether the current bar is the activation bar or a continuation bar.

**Data source**: new `GET /setup-engine/episodes/live` — described in full in §4. This is the one endpoint in this design that does real composition work (not zero-line wiring like §3.1), so it gets its own subsection there.

**Frontend**: a new `ActiveSetupBundle.tsx` component — one card per currently-active setup (`SetupEpisode` where the live window's last bar falls inside it), showing `duration_bars` so far, `start_timestamp`, and an `activation` vs `continuation` badge (continuation = the current bar is not the episode's `start_timestamp`). A setup with zero active episodes right now renders as an empty/dim state, not hidden — "nothing is active" is itself a real, displayable fact.

### 3.3 Episode Inspector — HYBRID (live current-episode + frozen distribution overlay)

**Shows**: the current episode (live), the historical duration distribution for that setup (frozen, from RE-2), the current episode's censoring status, and recent activation history.

- **Current episode** (live): the same `SetupEpisode` object from §3.2's endpoint, for the one setup the operator has selected. Shown with its live `termination_reason` (always `None`/not-yet-terminated while still active) and whether it is currently `is_left_censored` (its own live window started mid-run — the live window's own "segment start" boundary, not a market-data gap, since a live window is itself just a suffix of the full live segment).
- **Historical duration distribution** (frozen): `SetupProfile.entries[setup].all_episodes_duration` / `.fully_observed_duration` (`NumericStats`: mean/median/p75/p90/p95/max) straight from the frozen RE-2 baseline (§4's static JSON export). Rendered as a simple horizontal distribution strip (p50/p75/p90/p95/max markers) with the current episode's live duration-so-far plotted on the same axis — this is a **comparison against history**, explicitly not a prediction of how long the current episode will last. The label says exactly that.
- **Recent activation history** (live): the last N `SetupEpisode`s for the selected setup from the same live window used by §3.2/§3.4, listed with start/end timestamp, duration, and termination reason.

**Frontend**: `EpisodeInspector.tsx`, a setup-selector plus three stacked panels (current episode card, distribution strip, recent-history table). The distribution strip is a small new chart using `recharts` (already a frontend dependency) — a horizontal box-and-whisker-style strip is a direct, unadorned rendering of five already-computed numbers, not a new statistical construct.

### 3.4 Timeline — LIVE

**Shows**: activation events, continuations, segment boundaries, gap markers, over a selectable recent window.

**Data source**: the same live-window computation as §3.2/§3.3 (§4's endpoint returns enough to drive all three live sections from one fetch, to avoid three separate live Rule/Setup Engine evaluation passes over the same window). Segment boundaries and gap markers come directly from `atlas.profiling.service.segment_by_gap` applied to the live window — reused exactly as RE-1/RE-2 already use it, and the same function that already draws every gap boundary in the certified historical baseline.

**Frontend**: `Timeline.tsx` — a horizontal time axis (a `recharts` scatter/timeline composition, or a simple absolutely-positioned-div timeline if `recharts` proves awkward for this shape — a frontend implementation decision, not an architecture one) with one lane per setup. Each `SetupEpisode` renders as a bar spanning `start_timestamp`→`end_timestamp`; `ActivationEvent`s that coincide across setups (RE-2's multi-label tie handling) render as a vertical marker spanning all affected lanes, labeled with every tied setup name — never an invented ordering among them, exactly matching RE-2's own `ActivationEvent.activated_setups` semantics (alphabetically sorted for display determinism only). Segment/gap boundaries render as a distinct visual break in the timeline (not just a wide empty gap that could be mistaken for "nothing happened" — it must read as "no data exists here," which is a different fact from "nothing was active here").

### 3.5 Research Overview — FROZEN

**Shows**: RE-1 summary, RE-2 summary, time concentration, overlap matrix, clustering summary, transition summary.

**Data source**: entirely the static JSON export described in §4.2 — no live computation anywhere in this section. Every number is a direct read of an already-generated, already-reviewed value from `research/RE1_*.md` / `research/RE2_*.md` (the JSON export mirrors the markdown exactly — same manifest, same figures — it only exists so the frontend has something structured to render instead of parsing markdown at request time).

**Frontend**: `ResearchOverviewPage`, six panels:
- RE-1 summary — fact frequency/persistence highlights, reusing `RE1_Research_Notes.md`'s own already-written prose summary rather than re-deriving a new one.
- RE-2 summary — setup frequency/persistence highlights, same reuse of `RE2_Research_Notes.md`.
- Time concentration — the 08:00 CT (and other) concentration table already in `RE1_Research_Notes.md` §5 / `RE2_Research_Notes.md` §2, rendered as a small bar chart per setup/fact instead of a markdown table — same numbers, different rendering only.
- Overlap matrix — `RE2_Setup_Overlap.md`'s five metrics per pair, rendered as a 4×4 grid (setups × setups) with the relationship category (`LOGICALLY_IMPLIED` / `SHARED_INPUTS_ONLY` / `EMPIRICAL` / `UNKNOWN`) shown as a badge per cell — reusing RE-2's own typed `SetupRelationshipMetadata`, never re-classified in the frontend.
- Clustering summary — `RE2_Clustering.md`'s gap/burst statistics per setup.
- Transition summary — `RE2_Setup_Transitions.md`'s matrix and recurrence rates, including the denominator note (expanded-destination-label vs source-episode) carried through as on-screen help text, not dropped.

Every panel in this section carries the **FROZEN BASELINE** badge from §2, with the exact `code_version`, `generated_at`, and dataset row count/range from the manifest, linking through to the underlying `.md` report for anyone who wants the full detail this summary view intentionally doesn't repeat.

### 3.6 Dataset Health — FROZEN

**Shows**: dataset identity, computability, segment count, known warnings, frozen version.

**Data source**: the RE-1 certification report (`docs/market_engine/re1-5file-phase3-certification-report.md`) and both freeze documents (`docs/market_engine/re1-phase5-freeze.md`, `docs/market_engine/re2-freeze.md`), read from the same static JSON export (§4.2) — this section is a structured rendering of documents that already exist, word for word in substance.

**Frontend**: `DatasetHealthPage` — dataset identity (symbol, timeframe, row count, date range, file list), computability summary (the certification report's PASS/WARNING/FAIL table, including the `trend_1m` FAIL with its full root-cause explanation — never hidden, never softened), segment count (359, matching RE-1's certified gap count), known warnings (every disclosed limitation from both freeze documents, verbatim), and the frozen code version with a direct link to the exact commit.

This section is explicitly about the **research baseline's** health, not live system health — live ingestion/API health already has its own surface (`GET /status`, `GET /health`), which this design does not duplicate or fold in.

## 4. New backend surface

Every new endpoint lives under the existing `atlas/api/v1/` convention (one router file per resource, registered in `atlas/main.py` exactly like every existing router) and follows the existing `require_api_key` auth pattern used by every non-webhook, non-health route today.

### 4.1 `atlas/api/v1/setup_engine.py` (new file, mirrors `rule_engine.py` exactly)

- `GET /setup-engine/latest?symbol=&timeframe=` — fetches the latest `MarketState` (existing `get_latest`), builds the `RuleEngineOutput` and `SetupEngineOutput` via existing `build_rule_engine_output_window`/`build_setup_engine_output_window` over the minimal trailing history the registries require (same pattern `rule_engine.py` already uses), and returns `setup_engine_output_to_dict()` — a function that **already exists**, unchanged, in `atlas/setup_engine/service.py`. This route is pure wiring.

### 4.2 `atlas/api/v1/research.py` (new file, static-snapshot reads only)

- `GET /research/re1/summary`, `GET /research/re2/summary`, `GET /research/dataset-health` — read a pre-generated JSON snapshot from disk (or an in-process cache loaded at startup) and return it as-is. **No computation happens on request.**

The snapshot itself is produced by a new, small, one-time **export step** — not a new analytics capability, an additional *serialization* of dataclasses RE-1/RE-2 already computed and already froze. Two ways to produce it, to decide during implementation planning (not this document):
  (a) A new `to_dict()` function per report dataclass in each package's `serialization.py` (a new file, following the exact pattern `atlas/research/serialization.py` already established for the Hypothesis Registry — dataclass↔dict, nothing else), invoked once by a new tiny script (`scripts/export_research_json.py`) that imports the already-frozen `research/RE1_*.md`-adjacent Python objects and writes `research/RE1_*.json` / `research/RE2_*.json` alongside the existing markdown.
  (b) A lighter-weight alternative: skip new `to_dict()` functions entirely and have `research.py`'s three routes parse the existing frozen markdown files directly at startup (the six reports have a consistent, mechanically-generated structure from `reports.py`'s own templates, so parsing them back is well-defined) — avoids touching RE-1/RE-2 packages at all, at the cost of a small, brittle markdown parser.

Recommendation for the implementation phase: **(a)**, because a typed `to_dict()` is far less brittle than parsing generated markdown back into structure, and it is exactly the same shape of addition `atlas/setup_engine/service.py`'s own `setup_engine_output_to_dict()` already is — additive serialization beside a frozen computation core, not a modification of it.

### 4.3 `atlas/api/v1/setup_engine.py` (continued) — the one endpoint with real composition logic

- `GET /setup-engine/episodes/live?symbol=&timeframe=&window=` — powers §3.2, §3.3, and §3.4 from one call.

  **What it does**: fetch the last `window` bars via the repository's existing `get_history(symbol, timeframe, limit=window)`, run them through `atlas.profiling.service.filter_input_states` → `segment_by_gap` → `build_rule_engine_output_window` → `build_setup_engine_output_window`, then RE-2's own episode-construction logic (`atlas.research.setup_profiling.service`'s segment-scoped walk) — **every one of these calls is an existing, unmodified function.** The route's own code is limited to: fetch → call the pipeline → shape the response. No new statistic, threshold, or aggregation is introduced anywhere in this call chain.

  **Response shape** (sketch, not a contract): per setup — the currently-active episode if any (or `null`), the last N episodes within the window (for §3.3's activation history and §3.4's timeline lanes), and the window's own segment boundaries (for §3.4's gap markers). A `computability` block per setup mirrors `ComputabilityProfile`'s existing shape.

  **Design constraint carried into implementation**: `window` must be bounded (e.g. a sane default and a hard maximum) — this is a live, per-request computation, not a cached frozen artifact, so it must stay cheap enough for an operator dashboard's refresh cadence. This is an implementation/performance concern, not a computation-correctness one; it does not change what any function computes, only how much history one request asks it to compute over.

### 4.4 `atlas/main.py`

Two new `app.include_router(...)` lines, same `dependencies=[Depends(require_api_key)]` convention every existing non-public router uses. No change to any existing router.

## 5. Frontend structure

Extends the existing Next.js App Router project at `frontend/` — no new stack, no new dependencies beyond what's already installed (`@tanstack/react-query`, `recharts`, Tailwind 4).

```
frontend/src/app/
  market-view/page.tsx            -> 3.1
  active-setups/page.tsx          -> 3.2
  episodes/page.tsx                -> 3.3
  timeline/page.tsx                -> 3.4
  research/page.tsx                -> 3.5
  dataset-health/page.tsx          -> 3.6

frontend/src/components/
  SetupEngineViewer.tsx            (sibling to existing RuleEngineViewer.tsx)
  ActiveSetupBundle.tsx
  EpisodeInspector.tsx
  EpisodeDurationStrip.tsx         (recharts distribution strip)
  Timeline.tsx
  ResearchOverviewPanels/          (6 sub-components, one per §3.5 panel)
  DatasetHealthPanels/             (identity / computability / warnings / version)
  FreshnessBadge.tsx                (the LIVE / FROZEN BASELINE badge from §2 - one
                                      shared component, used on every page)

frontend/src/lib/
  setupEngineApi.ts                 (sibling to existing ruleEngineApi.ts)
  researchApi.ts
```

**Data fetching**: every new query follows the existing TanStack Query + SSE-assisted-polling pattern already established in `ActivityTimeline.tsx` (`refetchInterval` driven by `pollInterval(sseConnected, baseMs)`, where `sseConnected` comes from the existing `/stream` SSE connection) — no new streaming mechanism is introduced. The existing `/stream` SSE endpoint is a generic any-event relay that triggers a refetch, not a payload carrier (documented as deliberate in `stream.py`); this design does not change that.

**Auth**: the existing shared `src/lib/api.ts` client (`NEXT_PUBLIC_API_KEY` bearer header on every request) is the pattern every new page should use. `RuleEngineViewer.tsx`'s own manual per-session key-entry form is an older, self-contained pattern that predates `api.ts`'s global key — noted here as a reconciliation decision for the implementation phase, not resolved by this document.

**Visual language**: no new design system. Every new component uses the existing CSS custom properties already established in `globals.css` (`--surface`, `--border`, `--foreground`, `--muted`, plus the semantic `--ok`/`--warn`/`--danger` set) and the existing component library's card/row/badge conventions (`StatusBadge.tsx` and friends). The one genuinely new visual primitive is `FreshnessBadge.tsx` (§2's LIVE/FROZEN distinction) — everything else is a direct extension of what's already on screen in `RuleEngineViewer.tsx`, `ActivityTimeline.tsx`, and the analytics charts.

## 6. What this document does not decide

Left open for the implementation-planning step that follows this document, deliberately not resolved here:
- Exact `window` default/max for the live episodes endpoint.
- Whether the JSON research export (§4.2) is a build-time script run manually alongside `run_statistical_profile.py`/`run_setup_profile.py`, or wired into CI.
- Reconciling `RuleEngineViewer.tsx`'s manual key-entry with the rest of the app's global-key convention.
- Exact chart library usage details (recharts component choices) for the Timeline and duration-strip visuals.
- Whether Market View's symbol/timeframe selector is shared (one global selector driving all six sections) or per-page — recommended default is a single shared selector in a layout-level header, to keep the six sections describing "the same market" consistently, but this is a UX decision for the design/wireframe review, not an architectural one.

## 7. Section-to-source traceability (summary table)

| Section | Track | Primary data source(s) | New backend work |
|---|---|---|---|
| 1. Market View | LIVE | `GET /rule-engine/latest` (exists), `GET /setup-engine/latest` (new, zero-computation wiring) | New route only |
| 2. Active Setup Bundle | LIVE | `GET /setup-engine/episodes/live` (new) | New route, reuses RE-2 functions unmodified |
| 3. Episode Inspector | HYBRID | Same live endpoint + `GET /research/re2/summary` (frozen) | Both of the above |
| 4. Timeline | LIVE | `GET /setup-engine/episodes/live` (new) | Same endpoint as §2 |
| 5. Research Overview | FROZEN | `GET /research/re1/summary`, `GET /research/re2/summary` (new, static reads) | New routes + new JSON export script |
| 6. Dataset Health | FROZEN | `GET /research/dataset-health` (new, static reads) | New route + same JSON export script |
