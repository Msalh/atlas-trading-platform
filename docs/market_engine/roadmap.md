# Market Engine — Roadmap

**Status: new authoritative planning baseline, approved 2026-07-19, superseding the original
(unrecoverable) roadmap.** See `architecture-principles.md` in this folder for the permanent
rules this roadmap must respect. See individual Sprint ADR/Debt Register entries (in-code, per
module docstring) for Sprint-level decisions this roadmap does not repeat.

## Why this document exists

The original Market Engine roadmap (a 21-sprint plan plus three amendments, and the accompanying
Project Charter) was produced entirely in chat during earlier project planning and was never
written to a file. A mid-session context compaction lost its full text; only fragments survived.
A full-repo, full-history search (see the roadmap reconciliation record) confirmed it is not
recoverable. Rather than reconstruct it from memory, this document replaces it, built fresh from
the actual state of the codebase after Sprint 8. It is persisted here specifically so this cannot
happen again.

## Current System Baseline (as of Sprint 31)

**Updated 2026-07-20** — this section originally described the system as of Sprint 8, then Sprint
24C. It now reflects everything completed through Sprint 31; see "Sprint Roadmap" below for how
Sprints 9 onward got here, and the Phase 3 entry above for the Rule Engine/Setup Engine detail
this section summarizes rather than repeats.

**Sprints 24D–31, summarized** (full detail lives in each Sprint's own commits/reports, not
repeated here): a production incident (`vwap` incorrectly tick-grid-validated, since it is a
continuous Pine-computed average, never a traded print) was root-caused, fixed
(`84a1765d5f09c1f85c685fd066f6f9a1d20c8b25`), and deployed — see `atlas/market_engine/models.py`'s
own `vwap` field comment for the permanent record. A historical CSV bootstrap pipeline (`plot()`
+ chart-data-export, Sprint 25A.5/25B, not Pine Logs — alert delivery does not fire on historical
bars) was built and its importer (`scripts/import_historical_market_state_csv.py`) committed
Sprint 31 after being reused uncommitted for several Sprints. A Research Engine MVP
(`atlas/research/`, Sprint 28) now exists one layer above the Profiler — `Hypothesis →
DatasetManifest → Profiler (unchanged) → Experiment → ResearchReport`, file-backed append-only
stores, proven end to end against real historical data. Sprint 31 resolved the project's
instrument-identity uncertainty empirically: the live production symbol is `MNQ1!` (not `MNQU6`,
which was never a literal wire value anywhere in this project's evidence); the historical CSV
export's native `time` column is bar-OPEN time while the live webhook uses bar-CLOSE time
(`time_close`) — a TradingView platform convention difference, not a bug, resolved via the
importer's existing `--assume-bar-open-time` flag; the real historical dataset
(`data/CME_MINI_MNQ1!, 5_504af.csv`, 1200 bars) is **CERTIFIED WITH WARNINGS** (Sprint 31 Task 4;
warnings are all documented, by-design properties, not defects). Full detail:
`docs/market_engine/sprint31-task3-equivalence-report.md` and the Sprint 31 commit history on
`feature/market-engine-rule-setup-engine`.

**Completed**: core primitives (`atlas/core/`); TradingView ingest (validate → translate →
idempotent persist); Postgres + in-memory repositories; read API (`latest`, `history`); Pine v6
indicator; staleness detection + alerting (`atlas/monitoring.py`); gap/integrity reporting
(`find_gaps`, `GET /market-state/integrity`); range-bounded historical export
(`get_market_state_export`, Sprint 9); ordered read-only replay (`replay_market_state`, Sprint
10); Rule Engine — individual facts (7: the original 6 plus `vwap_relationship`, Sprint 22B, the
first fact added beyond the original 13-field scope), an observability endpoint, and windowed
output orchestration (Sprints 11–15, 17A, 22B); Setup Engine foundation, the long-term
catalog/roadmap planning (`setup-engine-catalog.md`, Sprint 19), and four real setups —
`displacement_with_volume_confirmation` (Sprint 18), `liquidity_sweep_with_volume_confirmation`
(Sprint 20), `sustained_displacement_streak` (Sprint 21, the first setup with
`required_history > 1`), and `vwap_extension_with_volume_confirmation` (Sprint 23B, the first
`CONFLUENCE`-family setup — that family was added Sprint 23A, ahead of this consumer, for reasons
disclosed in `setup-engine-catalog.md`'s classification review, not speculatively). All five steps
of Sprint 19's original rolling implementation queue are now complete. Sprint 24A codified the Rule
Fact Independence Audit's findings: `rejection` is an unconditional predicate refinement of
`liquidity_sweep` (whenever both are computable), and `reclaim` is a predicate refinement of
`liquidity_sweep` under the current matched default window configuration (both `window=3`,
configuration-contingent) — see `rule-fact-inventory.md`'s "Fact hierarchy within this family" for
the authoritative statement and `setup-engine-catalog.md`'s coexistence rule for the resulting
catalog policy. No predicate, threshold, window, or registry changed in that Sprint — documentation
and two regression tests only.

Sprint 24B designed, and Sprint 24C implemented, a deterministic **historical fact and setup
profiler** (`atlas/profiling/`) — an observational-only analysis package sitting above all three
engines (Market Engine, Rule Engine, Setup Engine), reporting how often the current 7 facts and 4
setups compute, fire, overlap, and encounter insufficient data over real historical `MarketState`
data. Never a signal, confidence score, or profitability claim — see `setup-engine-architecture.md`'s
"Position in the pipeline" for exactly how this third path differs from both the decision path and
the LLM interpretation path. Sprint 24C also added `build_setup_engine_output_window()` to
`atlas/setup_engine/service.py` — a direct, one-layer-up generalization of
`build_rule_engine_output_window`, added because the profiler became a real, present consumer
needing exactly that capability (see `setup-engine-architecture.md`'s Orchestration section). Key
behavior, for anyone building on this later:
- **Gap segmentation, not exclusion**: a raw `MarketState` range is split into strictly-contiguous
  segments at every interval that isn't exactly one timeframe cadence apart (weekends, holidays,
  exchange maintenance, any other missing interval) — rows around a gap are never discarded, only
  placed in separate segments, each evaluated independently. A duplicate or non-monotonic
  timestamp is not a gap — both fail the run outright, since they indicate a real input defect, not
  a normal data condition.
- **Warm-up is counted, never discarded**: the first bars of every segment naturally produce
  `InsufficientData` for facts/setups whose required history exceeds what precedes them — the
  profiler reports this as real data (`InsufficientData` counts, plus explicit
  `fact_warm_up_observations`/`setup_warm_up_observations` per segment), never pads, synthesizes,
  or drops these rows.
- **21 MarketState bars, not 20, for two consecutive fully-computed Rule Engine outputs**: with
  `required_history(RULE_ENGINE_REGISTRY) = 20` (driven by `trend_5m`'s 20-bar window),
  `build_rule_engine_output_window` only fully resolves every one of the 7 registered facts at
  position 20 onward within a segment — a 20-bar segment yields exactly ONE such fully-computed
  output, not two; 21 bars are needed for two consecutive ones. Setup Engine completeness itself
  needs far fewer bars (as few as 2–4, since no registered setup consumes `trend_5m`) — both figures
  are derived directly from the real orchestration code and tested, not assumed (see
  `tests/test_profiling.py::TestRequiredHistoryBoundary`).
- **The hierarchy summary is derived, never a replacement for raw detections**: the profiler always
  reports every fact's and setup's actual computed outcome faithfully; on top of that, it separately
  computes whether the two Sprint 24A relationships (`rejection`/`reclaim` → `liquidity_sweep`) held
  on the profiled data, using a small, explicit, two-entry configuration (`KNOWN_REFINEMENTS` in
  `atlas/profiling/service.py`) that points back to `rule-fact-inventory.md` as the authoritative
  explanation — not a generic hierarchy engine, graph, or runtime metadata framework. A discrepancy
  (the documented relationship not holding on real data) is always surfaced, never hidden or
  corrected away.

**Not yet built**: LLM narration/interpretation of Setup Engine output (no LLM reasoning code
exists yet — see `setup-engine-architecture.md`'s interpretation-path note); Strategy & Signal
Layer (Phase 4); paper/live execution tied to Market Engine (Phases 5–6); journaling. The pure
orchestration functions themselves (`build_rule_engine_output_window`,
`build_setup_engine_output_window`) remain repository-free, input-assembly-left-to-the-caller
functions, unchanged since Sprint 17A/24C — but Sprint 24C's profiler now provides the first real
repository-backed (impure) CONSUMER sitting above both (`atlas.profiling.service.profile_market_state_range`,
calling `MarketStateRepository.get_range` directly), not a wrapper added inside either engine
package itself. That distinction — impure assembly stays one layer above pure orchestration, never
merged into it — is deliberate, not a partial retreat from the Sprint 17A posture.

**Known debt** (updated through Sprint 31; entries marked resolved, not removed, per this
project's standing rule):
- **No per-instrument identity/tick-size registry** — `TICK_SIZE = 0.25` (`atlas/market_engine/
  constants.py`) is a single global constant, applied identically regardless of the `symbol`
  string on any given event; `Symbol` performs no validation beyond non-blank. This is the
  identified root cause behind two independent findings this project has had: the `vwap`
  tick-validation incident, and the `MNQ1!`/`MNQU6`/`MNQU2026` instrument-identity ambiguity
  (Sprint 29A.6). Deliberately not built ahead of a second real instrument (no-speculative-
  abstraction rule) — now a documented, evidence-backed candidate for whenever that need becomes
  concrete, not a hypothetical one.
- **Roll policy decided, not yet operationalized**: dated contracts (not continuous/`MNQ1!`) are
  the adopted policy for tick-validated price fields (Sprint 29A.6 §4) — because a back-adjusted
  continuous series can silently stop representing a literal traded print, which is the entire
  justification for tick-grid validation. No roll/stitch mechanism exists yet; none is needed
  until research spans a contract rollover.
- **No `MARKET_STATE_REJECTED` event/observability** — `atlas/api/v1/market_state.py`'s 422
  rejection path logs a structured warning (added Sprint M4/Sprint 31 diagnostic work) but never
  publishes to the `EventBus`, so `GET /status` (`atlas/status.py`) has no visibility into
  rejections at all, only successes. Identified, not yet built (Sprint 29A §4) — the recommended
  fix reuses the existing `EventBus`/`SystemStatus` mechanism, not new infrastructure.
- **Sprint 26 Phase 3/4 (real historical import execution + post-import audit) still open** —
  blocked on `DATABASE_URL`/`TEST_DATABASE_URL` access, unchanged since Sprint 24D. The correct
  invocation is known and requires no new code: `--symbol MNQ1! --timeframe 5m
  --assume-bar-open-time --apply`. See Sprint 31 Task 8's exact commands, this document's own
  history (git log on this file) or the Sprint 31 commit range for the full audit.
- The historical profiler (`atlas/profiling/`, Sprint 24C) does not attempt automatic contract-roll
  detection — only explicitly-configured roll timestamps are recorded in its data-quality summary
  (`observations_near_roll_boundary`); an un-configured roll inside a profiled range is silently
  invisible to it, not flagged. Disclosed, not solved — the same "detection and reporting only, no
  automation" posture `find_gaps`/the Dataset Builder export already established one layer down.
- The profiler's gap segmentation has no holiday-aware or session-aware semantic classification
  beyond raw cadence-gap detection — it correctly splits on any non-cadence interval (a weekend, a
  holiday, an exchange maintenance window are all treated identically as "a gap"), but cannot
  distinguish which KIND of gap occurred, the same disclosed limitation `window_integrity.py`
  itself carries (deliberately calendar-agnostic, per that module's own docstring).
- `MarketStateRepository.get_range`'s Protocol does not expose whether a `limit`-bounded query was
  truncated — the profiler's `possible_truncation` flag (raw row count equals the requested limit)
  is a heuristic, not a guarantee; a range that genuinely contains exactly `limit` rows would also
  set this flag. Disclosed explicitly rather than claimed as certain detection.
- ~~`MarketStateRepository.get_history()` supports only "most recent N," no time-range query~~ —
  **resolved, Sprint 9**: `MarketStateRepository.get_range()` now exists (`atlas/market_engine/ports.py`).
- `is_market_hours_expected` is not holiday-aware (disclosed in `atlas/monitoring.py`) — still
  unresolved; now also the reason `build_rule_engine_output_window`'s strict contiguity check will
  misclassify a window spanning an exchange holiday as an integrity violation (disclosed in
  `rule-engine-architecture.md`'s §3, Sprint 17A).
- `find_gaps`'s 1.5x jitter tolerance is an unvalidated heuristic — real production traffic now
  flows (confirmed Sprint 31), but this specific tolerance value has not been independently
  re-validated against it.
- `vwap_relationship`'s threshold (1.0, Sprint 22B) is a provisional, explicitly unvalidated
  heuristic borrowed from `trend_5m`'s own threshold shape — the same disclosed status as every
  other threshold in this project.
- `EventBus`/`SystemStatus`/SSE are single-process, in-memory — a real horizontal-scaling
  constraint.
- `live/README.md` has never been updated for any Market Engine work.
- `GET /market-state/*` read endpoints carry no rate limit (consistent with every other read
  endpoint in the app, not a new gap).
- Setup Engine severity is a single fixed `NORMAL` value for every detected setup, for all four
  real setups built so far (Sprints 18, 20, 21, 23B — deliberate, no real data exists yet to
  calibrate a genuine severity metric against). Not a bug; named here so it isn't mistaken for a
  completed feature.

**Operational risks**: real production TradingView traffic now flows through this system
(confirmed directly, Sprint 31 Tasks 1-3 — the `vwap` incident was a real production failure and
its fix independently re-verified against live data multiple times since). `DATABASE_URL`/
`TEST_DATABASE_URL` access has not been available in any working session this project has had
through Sprint 31 — every historical-import and audit capability beyond translation-only proof
remains unexercised against a real database (Sprint 26 Phase 3/4, still open). Alerting is a
silent no-op if `ALERT_WEBHOOK_URL` is unconfigured. In-memory state is lost on process restart.

**Production test fixtures (Sprint 15)**: three synthetic symbols were ingested into the real
production `market_state_events` table during Sprint 15's live smoke test —
`SMOKETEST_NEVER` (queried but never ingested, used to verify the `found=false` path),
`SMOKETEST_PARTIAL` (5 bars, used to verify a mixed `computed`/`insufficient_data` response), and
`SMOKETEST_FULL` (20 bars, used to verify all six facts compute in `REGISTRY` order). Market
Engine's store is append-only with no delete path (Immutability Rules), so these rows are
permanent. **They are operational test fixtures, not real traded instruments** — any future
Sprint or tool that lists or aggregates over symbols in production should exclude or otherwise
account for these three names, the same way `test_closed` is excluded from `stats.today`'s real
trade counts in the original trading-platform project.

**Real historical dataset (Sprint 25B/26/31)**: `data/CME_MINI_MNQ1!, 5_504af.csv` — 1200 real
5m bars, `2026-07-13T13:00:00Z` → `2026-07-17T20:55:00Z`, symbol `MNQ1!` (confirmed, Sprint 31
Task 1 — the original Sprint 25B/26 import commands used `MNQU6`, now known to be unverified).
Certified **CERTIFIED WITH WARNINGS** (`scripts/certify_historical_dataset.py`, Sprint 31 Task 4)
— all warnings documented, by-design properties, not defects. Not yet imported into any real
repository (Sprint 26 Phase 3, still open on `DATABASE_URL` access) — translation-level proof
only so far.

**Architectural assumptions**: modular monolith remains correct as long as Market Engine, AI, and
trading logic share one process; "AI never writes to Market Engine" is non-negotiable; hexagonal
layering verified intact through Sprint 23B (each Rule Engine and Setup Engine Sprint re-ran its own
dependency-direction grep check as part of its own Definition of Done, not just once at Sprint 8);
CT-timezone, CME-aligned session logic assumes MNQ/NQ-like instruments only.

## Phase Structure

- **Phase 1 — Market Data Foundation.** Complete (Sprints 1–8).
- **Phase 2 — Historical Data Tooling** (Dataset Builder, Replay). Makes Phase 1's data usable and
  testable-against before anything acts on it.
- **Phase 3 — AI Analysis Layer.** Read-only analysis of market state — explicitly split into
  three separate architectural concerns per standing instruction, not one combined "AI" layer:
  - **Rule-based market analysis** (`atlas/rule_engine/`): deterministic, code-defined computation
    over market state — individual facts (Sprints 11-14, plus `vwap_relationship` in Sprint 22B,
    the first fact beyond the original 13-field scope), an observability endpoint (Sprint 15),
    and windowed output orchestration for downstream consumers (Sprint 17A).
  - **Setup Engine** (`atlas/setup_engine/`, foundation implemented Sprint 17B; long-term catalog
    and rolling roadmap planned Sprint 19; four real setups implemented, Sprints 18, 20, 21, and
    23B; a sixth `SetupFamily` member, `CONFLUENCE`, added Sprint 23A following a dedicated
    classification review, ahead of and specifically to unblock the Sprint 23B setup, all
    2026-07-19): deterministic, code-defined composition of Rule Engine
    facts into higher-level market structures. Still never an LLM call, still never a probability —
    sits between Rule Engine and the LLM, not a part of either. See `setup-engine-architecture.md`,
    `setup-engine-catalog.md`, and `setup-inventory.md`.
  - **LLM reasoning**: consumes Setup Engine's output only, for interpretation/narration — never
    computes facts or structures directly from raw market state, never invents numbers.
  See `architecture-principles.md`'s AI Boundaries section for the full rule,
  `rule-engine-architecture.md` (a dedicated planning Sprint, completed 2026-07-19, before any
  Phase 3 code; Interface section updated 2026-07-19 to reflect Setup Engine's insertion) for
  objective market facts, Rule Engine outputs, and the deterministic-vs-probabilistic split, and
  `rule-fact-inventory.md` (completed 2026-07-19) for the per-fact catalog Sprint 11 builds
  against, including which facts are actually computable today versus blocked on ingestion that
  doesn't exist yet.
- **Phase 4 — Strategy & Signal Layer.** Turns analysis into candidate trade signals. No
  execution.
- **Phase 5 — Paper Trading.** Simulated execution, zero capital risk.
- **Phase 6 — Live Trading Enablement.** Real execution, gated behind Phase 5 having actually run
  plus a separate, explicit human go/no-go decision.

Journaling and multi-instrument expansion remain named but unscheduled, to be placed once a
phase's real needs clarify where they belong.

## Sprint Roadmap

Sprints 9–10 are recorded below as originally planned, now marked complete. Sprints 11–18 are not
re-detailed here in the same template — that would duplicate what's already recorded in-code (each
module's own docstring) and in the four dedicated planning documents this roadmap already points
to (`rule-engine-architecture.md`, `rule-fact-inventory.md`, `setup-engine-architecture.md`,
`setup-inventory.md`); the Phase 3 entry above is this document's summary of that work and is kept
current instead.

### Sprint 9 — Dataset Builder, Phase 1 (static historical export) — **Complete**
- **Objective**: produce a portable, static export of a stored `market_state` series for offline
  use.
- **In scope**: a range-bounded repository query (new — `get_history` today only supports "most
  recent N"); export logic serializing an ordered series to a file; integration with `find_gaps`
  so an export surfaces its own gaps rather than presenting incomplete data as complete.
- **Out of scope**: scheduling/automation, cloud storage integration, multi-series batch export,
  consumption by anything downstream (that's Sprint 10+).
- **Deliverables**: extended `MarketStateRepository` port; pure export function; a trigger
  mechanism; tests.
- **Acceptance criteria**: exporting a known series produces a complete, correctly ordered file;
  gaps are annotated, not hidden; existing read/integrity behavior unchanged; full suite green.
- **Dependencies**: Sprint 4 (read path), Sprint 8 (`find_gaps`).
- **Risks**: the repository port change is a real, disclosed architectural change, not incidental;
  export tooling scope creep (a flat file, not a data warehouse).

### Sprint 10 — Replay Engine, Phase 1 (ordered, read-only delivery) — **Complete**
- **Objective**: deterministically re-deliver a stored `market_state` series, in order, to a
  caller.
- **In scope**: given `(symbol, timeframe, range)`, an async generator yielding stored
  `MarketState` in exact `occurred_at` order. Read-only, zero side effects.
- **Out of scope**: real-time pacing/speed-scaling; a richer consumer interface than the
  generator itself (no real consumer exists yet).
- **Deliverables**: the replay generator; tests proving exact ordering, no drops/duplicates,
  correct range boundaries.
- **Acceptance criteria**: replaying a known series yields events in exact chronological order
  matching the requested range precisely; full suite green.
- **Dependencies**: Sprint 9 (reuses its range-query capability).
- **Risks**: pressure to over-build the consumer interface speculatively before Phase 3 exists to
  define its actual needs — mitigate by keeping this Sprint's output the smallest correct
  primitive.

### Next planning point
**Updated Sprint 24C** — Sprint 23B's implementation closed out all five steps of Sprint 19's
original rolling implementation queue. The Rule Fact Independence Audit that followed found that
`liquidity_sweep`, `rejection`, and `reclaim` — previously catalogued as three independent ICT
peer primitives — are actually a two-level hierarchy: `rejection` is an unconditional predicate
refinement of `liquidity_sweep`, and `reclaim` is a predicate refinement of `liquidity_sweep` under
the current matched default window configuration. Sprint 24A codified that finding as the
authoritative documentation (`rule-fact-inventory.md`), the permanent Setup Engine catalog
coexistence rule (`setup-engine-catalog.md`), and two regression tests — no predicate, threshold,
window, or registry change.

No currently cataloged `trend_5m` setup is implementation-ready. The two existing candidates
(`setup-engine-catalog.md`'s ICT and MOMENTUM tables) were both inspected and found blocked:
- `trend_aligned_liquidity_sweep` needs its own dedicated directional-alignment design pass
  (what "a sweep whose reclaim direction agrees with `trend_5m`" precisely means is undefined) —
  and, now that `liquidity_sweep` is known to sit atop the refinement hierarchy above, that design
  pass must be hierarchy-aware, not just directional.
- `trend_aligned_displacement` remains blocked on `displacement` exposing magnitude only, with no
  directional sign — unresolved without a new or modified fact, out of scope for a design pass
  alone.

Sprints 24B/24C did not resolve either blocker above — they were a deliberately orthogonal next
step: rather than open an implementation Sprint on an unresolved design question, or scope Phase 4
speculatively, the project instead built the observational capability needed to eventually inform
that design work with real data (how often does `liquidity_sweep` actually fire? does `rejection`'s
documented unconditional relationship hold on real historical bars, not just synthetic fixtures?).
The historical fact/setup profiler (`atlas/profiling/`) now exists for exactly that purpose — see
this Sprint's own entry above and `setup-engine-architecture.md`'s "Position in the pipeline" for
its placement. It has not yet been RUN against real production data (no real production traffic has
ever exercised this system — see Operational risks below); running it is itself a candidate for
whatever comes next, not assumed to have happened already.

What comes next remains a dedicated design decision, not an implementation Sprint chosen
speculatively — whether that's running the profiler against whatever real or replayed data becomes
available, the `trend_aligned_liquidity_sweep` design pass, a different candidate from
`setup-engine-catalog.md`'s list (re-deriving priority from that document's own Capability Coverage
and Rule Fact Utilization matrices, not from a list written before this Sprint existed), or scoping
Phase 4 (Strategy & Signal Layer). Naming that now would repeat the speculative-planning risk this
project has consistently avoided; it gets its own decision when actually taken up.

**Updated Sprint 31** — what happened next was decided: production incident response (`vwap`,
Sprint 26) and building the Research Engine MVP (Sprint 28) one layer above the profiler, rather
than the `trend_aligned_*` design passes above, which remain exactly as blocked as described. The
profiler *has* now been run against real production-adjacent data (the certified historical CSV
and, indirectly, real production reads — Sprint 31 Tasks 2-4); it has not yet been run against a
real Postgres-backed repository (Sprint 26 Phase 3/4, still open).

A formal Research Readiness Gate exists (design: Sprint 29A.5 §5) with these items still
outstanding before Forward Return Analysis or any statistical research begins:
- Sprint 26 Phase 3 (historical import execution) and Phase 4 (post-import audit) — blocked on
  `DATABASE_URL`/`TEST_DATABASE_URL` access; exact commands are recorded in Sprint 31 Task 8's
  report (this Sprint's commit history) once that access exists.
- Roll policy (dated contracts, decided Sprint 29A.6) is not yet operationalized into ingestion
  or research code — no research has yet needed to span a contract rollover, so nothing is
  currently blocked by this, but it must be handled before any research does.
- A sustained live production observation window (Sprint 29A §2, design only — never executed).

The `trend_aligned_liquidity_sweep`/`trend_aligned_displacement` blockers from Sprint 24C remain
exactly as described above — untouched by any of this, not reopened, not resolved.

## Why this ordering is technically correct

- Phase 1 before everything: nothing above it can be trusted without persisted, gap-checked data.
- Phase 2 before Phase 3: AI logic needs a way to be tested against known, deterministic
  historical scenarios before ever touching live data.
- Dataset Builder before Replay: both need the same missing prerequisite (range-bounded
  retrieval); Dataset Builder is strictly simpler and retires that shared risk once, before
  Replay's added ordering/streaming complexity is layered on top.
- Phase 3 (read-only) before Phase 4 (strategy/signals): "AI never writes to Market Engine"
  already establishes AI as analysis, not decision-making; strategy is categorically higher risk
  and depends on analysis being trustworthy first.
- Phase 4 before Phase 5: simulated execution needs candidate signals to exist first.
- Phase 5 before Phase 6: reliability-before-intelligence applied to capital risk — no new
  capability touches real execution before being proven where a mistake costs nothing.
