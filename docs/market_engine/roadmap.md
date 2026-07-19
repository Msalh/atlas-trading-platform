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

## Current System Baseline (as of Sprint 23A)

**Updated 2026-07-19** — this section originally described the system as of Sprint 8, the point
this document was first written. It now reflects everything completed through Sprint 23A; see
"Sprint Roadmap" below for how Sprints 9 onward got here, and the Phase 3 entry above for the
Rule Engine/Setup Engine detail this section summarizes rather than repeats.

**Completed**: core primitives (`atlas/core/`); TradingView ingest (validate → translate →
idempotent persist); Postgres + in-memory repositories; read API (`latest`, `history`); Pine v6
indicator; staleness detection + alerting (`atlas/monitoring.py`); gap/integrity reporting
(`find_gaps`, `GET /market-state/integrity`); range-bounded historical export
(`get_market_state_export`, Sprint 9); ordered read-only replay (`replay_market_state`, Sprint
10); Rule Engine — individual facts (7: the original 6 plus `vwap_relationship`, Sprint 22B, the
first fact added beyond the original 13-field scope), an observability endpoint, and windowed
output orchestration (Sprints 11–15, 17A, 22B); Setup Engine foundation, the long-term
catalog/roadmap planning (`setup-engine-catalog.md`, Sprint 19), three real setups —
`displacement_with_volume_confirmation` (Sprint 18), `liquidity_sweep_with_volume_confirmation`
(Sprint 20), and `sustained_displacement_streak` (Sprint 21, the first setup with
`required_history > 1`) — and a sixth `SetupFamily` member, `CONFLUENCE` (Sprint 23A), added
ahead of its first consumer for reasons disclosed in `setup-engine-catalog.md`'s classification
review, not speculatively. Steps 1–3 of Sprint 19's rolling implementation queue are complete
(step 3 being `vwap_relationship` itself); step 4, `vwap_extension_with_volume_confirmation` (now
correctly classified `CONFLUENCE`), is designed and fully unblocked but not yet implemented.

**Not yet built**: LLM narration/interpretation of Setup Engine output (no LLM reasoning code
exists yet — see `setup-engine-architecture.md`'s interpretation-path note); Strategy & Signal
Layer (Phase 4); paper/live execution tied to Market Engine (Phases 5–6); journaling; any
repository-backed (impure) wrapper around `build_rule_engine_output_window` or Setup Engine's
orchestration — both remain pure-function-only, with input assembly left to the caller (a
deliberate Sprint 17A deferral, not an oversight).

**Known debt** (updated through Sprint 23A; entries marked resolved, not removed, per this
project's standing rule):
- ~~`MarketStateRepository.get_history()` supports only "most recent N," no time-range query~~ —
  **resolved, Sprint 9**: `MarketStateRepository.get_range()` now exists (`atlas/market_engine/ports.py`).
- `is_market_hours_expected` is not holiday-aware (disclosed in `atlas/monitoring.py`) — still
  unresolved; now also the reason `build_rule_engine_output_window`'s strict contiguity check will
  misclassify a window spanning an exchange holiday as an integrity violation (disclosed in
  `rule-engine-architecture.md`'s §3, Sprint 17A).
- `find_gaps`'s 1.5x jitter tolerance is an unvalidated heuristic — no real production traffic
  has ever flowed through this system.
- `vwap_relationship`'s threshold (1.0, Sprint 22B) is a provisional, explicitly unvalidated
  heuristic borrowed from `trend_5m`'s own threshold shape — the same disclosed status as every
  other threshold in this project.
- `EventBus`/`SystemStatus`/SSE are single-process, in-memory — a real horizontal-scaling
  constraint.
- `live/README.md` has never been updated for any Market Engine work.
- `GET /market-state/*` read endpoints carry no rate limit (consistent with every other read
  endpoint in the app, not a new gap).
- Setup Engine severity is a single fixed `NORMAL` value for every detected setup, for all three
  real setups built so far (Sprints 18, 20, 21 — deliberate, no real data exists yet to calibrate a
  genuine severity metric against). Not a bug; named here so it isn't mistaken for a completed
  feature.

**Operational risks**: no real production TradingView traffic has ever exercised this system —
everything is validated against in-memory or local/CI Postgres only. Alerting is a silent no-op
if `ALERT_WEBHOOK_URL` is unconfigured. In-memory state is lost on process restart.

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

**Architectural assumptions**: modular monolith remains correct as long as Market Engine, AI, and
trading logic share one process; "AI never writes to Market Engine" is non-negotiable; hexagonal
layering verified intact through Sprint 23A (each Rule Engine and Setup Engine Sprint re-ran its own
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
    and rolling roadmap planned Sprint 19; three real setups implemented, Sprints 18, 20, and 21;
    a sixth `SetupFamily` member, `CONFLUENCE`, added Sprint 23A following a dedicated
    classification review, all 2026-07-19): deterministic, code-defined composition of Rule Engine
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
**Updated Sprint 23A** — the previous version of this section flagged an open classification
question (`vwap_extension_with_volume_confirmation`'s definition asserting no reversion thesis
while its cataloged family, `MEAN_REVERSION`, asserted one) as a blocker on step 4 of the rolling
queue, and said Sprint 23 would not begin until it was resolved. It's now resolved:
`SetupFamily.CONFLUENCE` was added (Sprint 23A, no other code changed) and the setup reclassified
in `setup-engine-catalog.md`. Sprint 23A deliberately did **not** implement the setup itself —
only the taxonomy amendment — so that the classification decision could be reviewed on its own,
separately from the implementation work it unblocks. The next concrete step is now genuinely
unblocked: `vwap_extension_with_volume_confirmation` (`setup-engine-catalog.md`'s rolling roadmap,
step 4), designed and correctly classified, zero remaining blockers, not yet implemented. What
remains genuinely undecided, and is correctly left unscoped here, is anything past that single
next step: whether to continue the rolling queue, begin scoping Phase 4 (Strategy & Signal Layer),
or something else. Naming that now would repeat the speculative-planning risk this project has
consistently avoided; it gets its own decision when the rolling queue's own "re-evaluate" step is
actually reached.

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
