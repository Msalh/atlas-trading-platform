# Phase N4 Implementation Roadmap — The Research Engine

**Status:** Official implementation roadmap, derived from two frozen references
**Frozen inputs:** `docs/phase-n4-research-engine-blueprint.md`, `docs/research-engine-design-principles.md`
**Date:** 2026-07-21

This roadmap translates the approved architecture into an ordered sequence of implementation sprints. It does not reopen, and must not be read as reopening, either frozen reference. If an implementation sprint below ever appears to require violating a principle or the blueprint's package layout, that is a contradiction to be raised explicitly, not silently resolved by adjusting the code.

---

## Sequencing rationale — what comes first, and why this order departs from the example list

The blueprint listed candidate components in roughly this order: *Core entities, Ledger, Feature registry, Discovery Engine, Formalization, Experiment Builder, Replay bridge, Backtesting, Statistics, Validation, Ranking, Memory, Knowledge Graph, AI Assistant, Promotion.* This roadmap reorders three things, each for a stated reason:

1. **Replay Bridge moves much earlier (Sprint 3, not late).** It is the single highest-risk dependency in the whole engine — the one module touching certified, frozen production code (Replay Engine). Proving this narrow gateway in isolation, under its own dependency audit, as early as possible is the most direct application of "minimize architectural risk" the roadmap can make. Everything downstream that needs real data depends on it being right; nothing is gained by deferring it.

2. **Experiment Builder → Statistics → Validation → Ranking are built and certified end-to-end *before* Realizations and Backtesting exist**, using only decision-free (`StatisticalTestRealization`) experiments over Feature data. This is deliberate, not incidental: it is the first opportunity to prove, with a real working system rather than a diagram, that the hypothesis-centric claim from the blueprint is real — that the platform can run a complete, rigorous, ranked, promotable research cycle *without ever writing a strategy*. Building Backtesting first and bolting statistics on afterward would silently reproduce the strategy-first center of gravity this whole redesign exists to avoid, even with the "right" package names.

3. **Discovery Engine, Formalization (beyond manual), Memory, Knowledge Graph, and the AI Assistant all come after a complete, certified, human-driven core pipeline exists (Sprints 10–14, after the Sprint 9 milestone).** Discovery Engine's output (`Finding`) is only valuable if there is a trustworthy formalization → validation → ranking → promotion pipeline waiting to receive it; building the miner before the receiving pipeline is proven would mean building exploratory code against an unstable foundation. The AI Assistant is last of all, for the strongest version of the same reason: its entire value depends on a rich, populated, *already-trustworthy* ledger and knowledge base to read from, and Section VI's write-boundary guarantees are only as strong as the enforcement beneath them — that enforcement must already be proven solid before an LLM-touching component is added on top of it.

Everything else follows the dependency order the blueprint already specifies.

---

## Testing philosophy

Every sprint below follows the identical certification discipline already proven across N1–N3, applied to a system that introduces one genuinely new dimension — deliberate stochasticity (Monte Carlo) — which gets its own explicit testing discipline.

- **Unit testing.** Every pure function (entity construction/validation, criterion evaluation, sweep expansion, statistic computation) is tested directly against hand-built fixtures, the same way Rule Engine facts and Setup Interpretation rules were tested before any real pipeline existed.
- **Integration testing.** Wherever practical, tests chain *real* project builders rather than mocks at every layer — real `MarketState` → real `build_replay_output_window()` → real Feature evaluation → real `Experiment` construction — the same "prefer real builders over hand-built mocks" discipline Setup Interpretation's own Sprint 3 Integration Review established.
- **Deterministic replay testing.** Every pure Research Engine function gets the same 100+-repeated-call determinism audit used throughout N1–N3. Monte Carlo/resampling methods get an *additional*, new discipline: same-seed-same-result reproducibility tests, and different-seed-produces-a-different-but-still-valid-result tests — this project's first genuinely stochastic component, and the first place Principle VII.2 (explicit seeding, never system entropy) is actually load-bearing rather than theoretical.
- **Dependency audits.** Every new subpackage gets its own AST-based dependency test the moment it is created (never retrofitted later), following the exact pattern already used for Replay Engine, Setup Interpretation, and Strategy Engine — plus one project-wide audit, added at Sprint 1 and re-run at every subsequent sprint, verifying that `atlas.research.assistant`'s isolated AI/LLM dependency remains the *only* such exception anywhere in the `atlas` tree.
- **Certification gates.** Not every sprint below earns a full ADR-style certification pass — that would slow the roadmap without adding real assurance. Two sprints get **full milestone certification** (dependency audit + real-data validation + determinism audit + documentation review, exactly like Setup Interpretation's Sprint 4 and Phase N3's Sprint 7): **Sprint 9 ("Phase N4 Core")** and **Sprint 14 ("Phase N4 Complete")**. Every other sprint gets a **sprint-level gate**: its own focused tests, the full existing backend suite, Ruff, and its own new dependency audit — the same bar every N1–N3 sprint cleared before being called done.

---

## Sprint-by-sprint plan

### Sprint 1 — Core Entities

**Objective:** Define every entity from the blueprint (§1) as frozen, immutable, versioned data models — no behavior, no computation, no storage yet.

**Why before the next sprint:** Every later sprint references these types. Getting the shapes and invariants right once, before anything depends on them, is the same "models first, service later" discipline every N1–N3 package followed (e.g. Setup Interpretation Sprint 1).

**Deliverables:** `Feature` (Registered/Candidate), `Finding`, `Hypothesis` (generalized beyond Sprint 28's firing-rate-only criteria), `Realization` and its five subtypes, `Experiment`, `Evidence`, `ValidationResult`, `Ranking`/`LeaderboardSnapshot`, `PromotionRecord`; the full state-machine invariants from the blueprint's §2 tables, enforced as unconstructable-invalid-states wherever possible (the same posture `SetupResult`/`SetupInterpretation` already established).

**New packages/modules:** `atlas.research.models` (or the existing top-level `atlas.research` models module, generalized in place).

**Public interfaces introduced:** the entity constructors/dataclasses themselves; no service functions yet.

**Data models introduced:** all ten listed above.

**Dependency changes:** none beyond what `atlas.research` already has (Market Engine, Rule Engine, Setup Engine models, `atlas.core`).

**Test strategy:** construction/invariant tests for every entity and every documented invalid-state rejection; equality/immutability tests; fingerprint-determinism tests for every fingerprinted type.

**Certification requirements:** sprint-level only.

**Definition of Done:** every entity constructible, every documented invariant enforced by a failing test when violated, zero behavior beyond construction, full test suite and Ruff green.

**Risks:** *Architectural* — getting a field wrong here is expensive to fix later, since every downstream sprint will depend on it; mitigate by reviewing directly against blueprint §1 field-by-field before moving on. *Dependency* — none new. *Testing* — invariant coverage must be exhaustive now, since these types won't be revisited casually later. *Future-extension* — `CriterionKind`/`Realization` subtypes must be additive enums/unions from day one, never a closed set assumed complete.

---

### Sprint 2 — Ledger

**Objective:** Persist and retrieve every Sprint 1 entity, append-only, fingerprinted, with a basic hypothesis-level duplicate check.

**Why before the next sprint:** Nothing can be registered, queried, or referenced by ID until a store exists. This is also the first genuinely *useful* milestone — a human can register and browse hypotheses manually, before any automated pipeline exists.

**Deliverables:** extended `stores.py` (registries/trackers for all ten entities, same file-backed JSONL pattern as Sprint 28's existing `HypothesisRegistry`/`ExperimentTracker`); a Protocol boundary for each store (the same shape as `MarketStateRepository`) so a future Postgres swap never touches calling code; a first, minimal similarity check ("does a hypothesis with a structurally similar statement already exist") over the Hypothesis store only.

**New packages/modules:** extensions to `atlas.research.stores`; no new top-level package.

**Public interfaces introduced:** one repository-style Protocol per entity type; `register()`/`get()`/`list()`-shaped operations; `find_similar_hypotheses()`.

**Data models introduced:** none new — persistence of Sprint 1's models.

**Dependency changes:** none.

**Test strategy:** round-trip serialization tests for every entity; append-only/idempotent-or-reject-on-conflict tests (mirroring Sprint 28's existing `RecordConflictError` behavior); a deliberate test proving a `REJECTED`/`DECLINED` record survives everywhere a store is queried, never silently filtered out by default.

**Certification requirements:** sprint-level only.

**Definition of Done:** every entity can be registered and retrieved; conflict/idempotency behavior is proven; the duplicate-hypothesis check returns correct results against a hand-built fixture ledger; full suite + Ruff green.

**Risks:** *Architectural* — a naive similarity check (exact match only) would fail Principle II.4 outright; must be structural (feature-combination + context + outcome), not textual, even in this minimal form. *Dependency* — none new. *Testing* — conflict/idempotency edge cases are easy to under-test; budget real coverage here. *Future-extension* — the Protocol boundary must be proven swappable in principle now (even if only one implementation exists), or the promised future Postgres migration becomes a rewrite instead of a swap.

---

### Sprint 3 — Replay Bridge

**Objective:** The one, narrow gateway module that calls Replay Engine on Research Engine's behalf.

**Why before the next sprint:** Highest architectural risk in the entire roadmap (the only module touching certified production code); proving it correct and audited early removes that risk from every later sprint that needs real `ReplayFrame` data, rather than leaving it unresolved until much later.

**Deliverables:** `atlas.research.replay_bridge`, wrapping `build_replay_output_window()`/`replay()` behind a Research-Engine-shaped call surface; its own, immediate AST-based dependency audit proving it is the *only* Research Engine module importing `atlas.replay_engine`.

**New packages/modules:** `atlas.research.replay_bridge`.

**Public interfaces introduced:** a function (or small set of functions) that, given a symbol/timeframe/range, yields real `ReplayFrame`s — the Research Engine's own entry point to replay, never re-exporting Replay Engine's own API surface unchanged.

**Data models introduced:** none — consumes `ReplayFrame` unchanged.

**Dependency changes:** first Research Engine dependency on `atlas.replay_engine` (models + service), confined entirely to this one module.

**Test strategy:** integration tests against real `build_replay_output_window()` output (real MarketState fixtures, no mocks, mirroring Setup Interpretation's own real-builder discipline); a dependency-audit test proving no other Research Engine module imports Replay Engine.

**Certification requirements:** sprint-level, but with the dependency audit treated as load-bearing (not optional) given this module's risk profile.

**Definition of Done:** real `ReplayFrame`s flow through this module unchanged and unmutated; the "only one gateway" audit passes; full suite + Ruff green.

**Risks:** *Architectural* — if this module ever does more than call Replay Engine and pass through its result, the "no computation in the bridge" boundary has already eroded. *Dependency* — this is the one place a Replay Engine API change would be felt; keep the wrapping surface minimal so that risk stays small and localized. *Testing* — must use real builders, not mocks, or the integration proof is hollow. *Future-extension* — if a second Research Engine module ever needs Replay Engine directly, that is a signal to widen this module's own surface, never to add a second gateway.

---

### Sprint 4 — Feature Registry

**Objective:** The Registered and Candidate feature tiers.

**Why before the next sprint:** Every hypothesis, discovery method, and statistical test needs features to reference. This is the last purely foundational sprint before the research loop itself begins.

**Deliverables:** `atlas.research.features` with two tiers — Registered (code-defined, reviewed, permanent, structurally mirroring Rule Engine's own `FactRegistration`/`REGISTRY` shape) and Candidate (declarative specs interpreted by one fixed, reviewed evaluator — never dynamically generated/executed code, per Principle VIII.1's extension into feature-generation safety); the Feature lifecycle states from blueprint §2.2.

**New packages/modules:** `atlas.research.features`.

**Public interfaces introduced:** a registration mechanism for Registered features; a declarative spec schema plus its fixed evaluator for Candidate features; a promotion function moving a Candidate to Registered.

**Data models introduced:** the Candidate feature spec schema (data, not code).

**Dependency changes:** Market Engine, Rule Engine models (read-only, mirroring the shape, never modifying the registry itself).

**Test strategy:** unit tests against hand-built `MarketState` fixtures (same convention Rule Engine's own facts were first tested with); integration tests via Replay Bridge (Sprint 3) proving Registered features evaluate correctly over real `ReplayFrame` data; a dedicated test proving the Candidate evaluator cannot execute arbitrary code (only the fixed, closed spec vocabulary).

**Certification requirements:** sprint-level only.

**Definition of Done:** at least one real Registered feature and one real Candidate feature evaluate correctly against both hand-built and real-replay data; the "declarative, not generated code" boundary is proven by test, not only by design; full suite + Ruff green.

**Risks:** *Architectural* — any accidental import of `atlas.research.features` by `atlas.rule_engine` (or vice versa in the wrong direction) would violate the frozen registry boundary; audit this explicitly. *Dependency* — none beyond what's declared. *Testing* — the "no arbitrary code execution" guarantee for Candidate features is a security property, not just a correctness one, and deserves adversarial test cases, not only happy-path ones. *Future-extension* — new feature families (Order Blocks, FVG, Wyckoff, etc.) must each be additive Registered-tier registrations later, never a change to this sprint's own evaluator contract.

---

### Sprint 5 — Experiment Builder (Stage A) + Statistics

**Objective:** The first real, decision-free research loop: a human-authored `Hypothesis` about Feature data becomes an `Experiment`, runs, and produces `Evidence`.

**Why before the next sprint:** This is the sprint that proves the hypothesis-centric claim is real, not aspirational — a complete research cycle exists here with no strategy, no Realization, and no Backtesting anywhere in it.

**Deliverables:** `atlas.research.experiment_builder` (Stage A only: `Hypothesis` + `DatasetManifest` → a decision-free `Experiment`, fingerprinted); `atlas.research.statistics` (criterion evaluation over Feature data → `Evidence`, including effect size and confidence interval computation).

**New packages/modules:** `atlas.research.experiment_builder`, `atlas.research.statistics`.

**Public interfaces introduced:** `build_experiment()` (Stage A path); `compute_evidence()` (or equivalent) taking an `Experiment` + Feature data, returning `Evidence`.

**Data models introduced:** none new — populates Sprint 1's `Experiment`/`Evidence`.

**Dependency changes:** Features (Sprint 4); no Replay Engine dependency needed directly here (Statistics consumes Feature output, not raw frames) unless a criterion needs frame-level data, in which case it goes through Replay Bridge, never around it.

**Test strategy:** unit tests for criterion evaluation against hand-built Feature data; a full, real, hand-authored-hypothesis-to-Evidence integration test using real Replay Bridge output; a reproducibility test proving the same Experiment fingerprint always reproduces the same Evidence.

**Certification requirements:** sprint-level only.

**Definition of Done:** a human can register a hypothesis, have it built into an Experiment, run it, and receive Evidence — entirely without any strategy, Realization, or decision sequence existing anywhere in the system; full suite + Ruff green.

**Risks:** *Architectural* — this is the sprint most likely to be quietly "gotten right by shortcut" (e.g. someone reaches for a decision sequence because it's a familiar shape); watch for any Realization-shaped concept leaking in here — there must be none. *Dependency* — Statistics must not depend on Backtesting even implicitly (e.g. by importing a shared helper meant for decision sequences). *Testing* — reproducibility (same fingerprint → same Evidence) is the first real test of Principle VII.1 and deserves its own dedicated, explicit test, not an incidental one. *Future-extension* — new criteria must be additive to `CriterionKind`, each with its own versioned evaluator, never a change to an existing criterion's meaning.

---

### Sprint 6 — Validation

**Objective:** Walk-forward, Monte Carlo, out-of-sample enforcement, and multiple-testing correction, applied to Sprint 5's decision-free Evidence.

**Why before the next sprint:** A `Hypothesis` cannot be honestly called `VALIDATED` without this — and proving the funnel's rigor works on the simplest possible Evidence shape (no decisions involved) isolates any bugs here from anything decision-related.

**Deliverables:** `atlas.research.validation` — walk-forward fold construction, Monte Carlo resampling (seeded), out-of-sample consistency checks, and mandatory multiple-testing correction whenever a batch of hypotheses shares a dataset; `ValidationResult` production with full statistical justification attached (never a bare boolean).

**New packages/modules:** `atlas.research.validation`.

**Public interfaces introduced:** `validate()` (or equivalent), taking one or more `Evidence` records + a `WalkForwardSpec`/`MonteCarloSpec` + the hypothesis's `AcceptanceCriterion`, returning a `ValidationResult`.

**Data models introduced:** `WalkForwardSpec`, `MonteCarloSpec` (both named in the blueprint, defined here).

**Dependency changes:** Statistics (Sprint 5); no new external dependency.

**Test strategy:** determinism tests for every stochastic method (same-seed-same-result, different-seed-still-valid); a dedicated test proving a hypothesis validated on in-sample-only evidence is structurally impossible to mark `VALIDATED` (Principle IV.3); a dedicated multiple-testing-correction test over a real batch of hypotheses sharing one dataset.

**Certification requirements:** sprint-level only.

**Definition of Done:** a decision-free hypothesis can be carried all the way from Experiment through a real walk-forward/Monte Carlo validation to a fully-justified `ValidationResult`; every stochastic path is proven reproducible given a seed; full suite + Ruff green.

**Risks:** *Architectural* — the temptation to make multiple-testing correction "opt-in" for convenience must be refused outright; it is mandatory per Principle IV.4, and must be structurally required by the API, not merely documented as expected. *Dependency* — none new. *Testing* — this is the roadmap's first genuinely stochastic component; reproducibility testing here sets the pattern every later Monte Carlo use in the system will follow, so it deserves disproportionate care. *Future-extension* — new walk-forward/resampling schemes must be additive spec types, never a change to an existing scheme's meaning.

---

### Sprint 7 — Ranking

**Objective:** Comparative assessment across validated hypotheses, still entirely decision-free, plus the first Leaderboard Snapshot.

**Why before the next sprint:** Proving ranking works over purely descriptive, non-actionable hypotheses first (before Realizations exist) reinforces, rather than quietly abandons, the hypothesis-centric design — a leaderboard here ranks *ideas*, not strategies.

**Deliverables:** `atlas.research.ranking` — comparison of `ValidationResult`s against each other and against simple benchmarks (e.g. a null/random baseline); versioned, timestamped `LeaderboardSnapshot` persistence.

**New packages/modules:** `atlas.research.ranking`.

**Public interfaces introduced:** `rank()`/`compare()`; `snapshot_leaderboard()`.

**Data models introduced:** none new beyond `LeaderboardSnapshot` (named in blueprint §1).

**Dependency changes:** Validation (Sprint 6), Ledger (Sprint 2, for reading history).

**Test strategy:** unit tests over hand-built `ValidationResult` fixtures; a real end-to-end test carrying several Sprint 5/6-produced hypotheses through to a ranked, snapshotted leaderboard; a determinism test proving repeated ranking of the same inputs is stable and order-independent of insertion order.

**Certification requirements:** sprint-level only.

**Definition of Done:** several real, decision-free, validated hypotheses can be ranked against each other and a benchmark, and that ranking is snapshotted and later retrievable unchanged; full suite + Ruff green.

**Risks:** *Architectural* — a ranking that silently assumes every entry has a Realization would break the moment it's asked to rank a purely descriptive hypothesis; test that case explicitly, since it's the whole point of this sprint's ordering. *Dependency* — none new. *Testing* — snapshot immutability (a past leaderboard must never change retroactively) needs its own explicit test, mirroring Principle II.3's "supersede, never overwrite" discipline. *Future-extension* — once Realizations exist (Sprint 8), Ranking must extend to cover them without changing how it ranks decision-free hypotheses.

---

### Sprint 8 — Realizations + Backtesting

**Objective:** Stage B (templated) and Stage C (human-authored) realizations, and the pure execution core that turns a Realization into a decision sequence.

**Why before the next sprint:** Only now, with the entire decision-free pipeline already proven end-to-end, is it safe to introduce the strategy-shaped concept the whole redesign was careful not to start from.

**Deliverables:** `atlas.research.backtesting` — pure execution: `Realization` (Templated or StrategyVariant subtype) × `ReplayFrame` sequence (via Replay Bridge) → deterministic decision sequence; extension of Experiment Builder to construct Realization-bound Experiments (Stage B/C); extension of Statistics/Validation/Ranking to accept decision-sequence-based Evidence alongside the decision-free kind already supported.

**New packages/modules:** `atlas.research.backtesting`.

**Public interfaces introduced:** `ResearchStrategyPlugin` protocol (structurally distinct from `atlas.strategy_engine.ports.StrategyPlugin`, per Principle VIII.4); `execute_realization()`.

**Data models introduced:** none new — populates Sprint 1's `Realization` subtypes.

**Dependency changes:** Replay Bridge (Sprint 3, for frame data); no dependency on `atlas.strategy_engine` in either direction.

**Test strategy:** a dedicated, explicit test proving `ResearchStrategyPlugin` cannot be accepted anywhere `atlas.strategy_engine.ports.StrategyPlugin` is expected, and vice versa (structural-typing separation, tested, not assumed); real end-to-end tests for both Templated and StrategyVariant realizations against real Replay Bridge output; extension of Sprint 5–7's own tests to cover the now-decision-bearing Evidence path without weakening the decision-free path's own coverage.

**Certification requirements:** sprint-level only (full certification deferred to Sprint 9, which covers the whole pipeline).

**Definition of Done:** a human-authored strategy variant can be realized, backtested, statistically evaluated, validated, and ranked alongside decision-free hypotheses in one leaderboard; the type-boundary test against production `StrategyPlugin` passes; full suite + Ruff green.

**Risks:** *Architectural* — this is the sprint most likely to accidentally reintroduce strategy-first thinking by convenience; watch that Realizations remain optional attachments to a Hypothesis, never a required one. *Dependency* — any accidental import from `atlas.strategy_engine` here (even "just for the type") is a direct Principle VIII.2/VIII.4 violation and must fail the dependency audit immediately. *Testing* — the type-separation test is the single most important test in this sprint; do not treat it as boilerplate. *Future-extension* — Context-filter and Risk-input realization subtypes (named in the blueprint, not built yet) must slot into this same `execute_realization()` shape without a redesign.

---

### Sprint 9 — Promotion (Milestone: Phase N4 Core certification)

**Objective:** The `PromotionRecord` workflow and mandatory human review gate; full certification of the entire human-driven pipeline built in Sprints 1–8.

**Why before the next sprint:** This closes the first complete, certifiable loop — Hypothesis through Promotion — before any exploratory/automated components (Discovery, AI Assistant) are added on top of it. Everything from here on is additive to a proven core, never a repair of an unproven one.

**Deliverables:** `atlas.research.promotion` — the review queue, `PromotionRecord` construction (mandatory rationale, pinned evidence snapshot), `APPROVED`/`DECLINED`/`DEFERRED` handling; **the full Phase N4 Core certification pass**: whole-pipeline dependency audit (zero production dependents of `atlas.research`, confirmed the same way Replay Engine's/Setup Interpretation's zero/approved-dependent lists were verified), a real-data end-to-end run (a real historical dataset carried through Feature evaluation → Experiment → Evidence → Validation → Ranking → Promotion review, both for a decision-free and a decision-bearing hypothesis), and a documentation review of every package built so far.

**New packages/modules:** `atlas.research.promotion`.

**Public interfaces introduced:** `submit_for_review()`, `record_decision()`.

**Data models introduced:** none new — populates Sprint 1's `PromotionRecord`.

**Dependency changes:** none new (this package does not perform production certification itself — see below).

**Test strategy:** unit tests for the review workflow's state transitions; a dedicated test proving a `DECLINED` record is retained and surfaces on a resubmission attempt (Principle V.3); the milestone's own real-data certification suite (see Deliverables).

**Certification requirements:** **full milestone certification** — this is "Phase N4 Core."

**Definition of Done:** a real hypothesis can be carried, end to end, through every stage from registration to a human's promotion decision, with a complete, auditable evidence trail at every step; the whole-pipeline dependency audit is green; full suite + Ruff green; a short certification report is produced (mirroring the Setup Interpretation Sprint 4 / Phase N3 Sprint 7 report format).

**Risks:** *Architectural* — `atlas.research.promotion` must not be confused with, or attempt to perform, the actual production certification sprint (dependency audit + equivalence study + ADR) that a *promoted* strategy still requires before reaching `atlas.strategy_engine` — that remains a separate, later, human-led effort, explicitly out of this package's scope. *Dependency* — the whole-pipeline audit here is the first point something could have quietly leaked a production dependency across eight prior sprints; treat any finding here as a stop-the-line event, not a fix-and-continue one. *Testing* — the real-data run must cover both the decision-free and decision-bearing paths, or the milestone doesn't actually prove what it claims to. *Future-extension* — this milestone is the stable foundation everything in Sprints 10–14 builds on; nothing in it should need revisiting once Discovery/AI Assistant are added.

---

### Sprint 10 — Discovery Engine v1 (correlation/interaction + clustering) + Formalization

**Objective:** The first automated Finding-producing methods, and the workflow that turns a Finding into a real Hypothesis.

**Why before the next sprint:** These are the two best-precedented, lowest-risk discovery methods (they directly generalize RE-1's own existing pairwise methodology), and Formalization is what makes any Discovery output usable at all — building them together keeps the sprint's own vertical slice complete and testable.

**Deliverables:** `atlas.research.discovery` (correlation/interaction submodule, clustering submodule) producing `Finding` records tagged with method + version + parameters; `atlas.research.formalization` — Finding → draft Hypothesis, including the Sprint 2 duplicate-detection check extended to cover Finding-sourced proposals.

**New packages/modules:** `atlas.research.discovery`, `atlas.research.formalization`.

**Public interfaces introduced:** `discover_correlations()`, `discover_clusters()` (or equivalent); `formalize()`.

**Data models introduced:** none new — populates Sprint 1's `Finding`.

**Dependency changes:** Features (Sprint 4), Replay Bridge (Sprint 3), RE-1's own existing pairwise methodology (read, reused, never modified).

**Test strategy:** unit tests for each discovery method against hand-built feature data with known, planted relationships; a real end-to-end test from real replay data through a Finding through Formalization into a registered Hypothesis; a test proving a Finding matching an existing (including rejected) Hypothesis is flagged before formalization, not after.

**Certification requirements:** sprint-level only.

**Definition of Done:** running Discovery against real data produces genuine, correctly-tagged Findings; at least one Finding is successfully formalized into a Hypothesis that then flows through the already-certified Sprint 9 pipeline unmodified; full suite + Ruff green.

**Risks:** *Architectural* — the single highest risk in this sprint is a Finding being treated as validated anywhere downstream; a dedicated test must prove Discovery output alone can never reach `VALIDATED` status without passing through Formalization and the full Sprint 5–9 pipeline. *Dependency* — Discovery must never import Statistics/Validation/Ranking/Promotion directly to "shortcut" a finding through — it only ever produces Findings. *Testing* — planted-relationship fixtures (known ground truth) are essential here; without them, a discovery method's correctness is unverifiable. *Future-extension* — every later discovery method (Sprints 12–13) must follow this same submodule shape without requiring changes to Formalization's own contract.

---

### Sprint 11 — Research Memory (full) + Knowledge Graph

**Objective:** Finding-scale retention/expiry policy, full similarity search across the whole ledger, and the read-only graph projection.

**Why before the next sprint:** Once Discovery Engine (Sprint 10) is producing real Finding volume, Memory's full capability — not just the Sprint 2 minimal hypothesis-dedup check — becomes necessary; the Knowledge Graph is naturally built alongside it since graph traversal is the most natural implementation of "find structurally similar records."

**Deliverables:** `atlas.research.memory` — Finding retention/expiry enforcement (unformalized Findings only, per Principle II.2), full similarity search across Findings, Hypotheses (including rejected/declined), and their relationships; `atlas.research.knowledge_graph` — a read-only, rebuildable graph projection over the canonical ledger (§3/§5 of the blueprint), never a second source of truth.

**New packages/modules:** `atlas.research.memory`, `atlas.research.knowledge_graph`.

**Public interfaces introduced:** `find_similar()` (generalized from Sprint 2's minimal version); `expire_stale_findings()`; `project_graph()`/graph query functions (e.g. "shortest path," "shared-feature neighbors").

**Data models introduced:** none new — a projection over existing entities.

**Dependency changes:** Ledger (Sprint 2), Discovery (Sprint 10, for Finding volume to manage).

**Test strategy:** a test proving the graph projection can always be fully rebuilt from the canonical ledger with an identical result (no drift, no independent state); a retention-policy test proving only unformalized Findings are ever pruned, never anything with an Experiment, Evidence, or PromotionRecord attached to it; multi-hop query tests against a hand-built, known-shape fixture graph.

**Certification requirements:** sprint-level only.

**Definition of Done:** "have we tried this before" queries return correct, structurally-aware answers across the whole ledger including rejected work; the graph projection is proven rebuildable and non-authoritative; full suite + Ruff green.

**Risks:** *Architectural* — the graph projection must never be allowed to silently become the system of record (e.g., by a future sprint writing to it directly instead of to the canonical ledger); a test enforcing "the projection is read-only, always" should exist from day one. *Dependency* — none new. *Testing* — retention-policy edge cases (a Finding that gets formalized right at its expiry boundary) deserve explicit coverage. *Future-extension* — new graph query shapes are additive functions over the same projection, never a change to what the canonical ledger stores.

---

### Sprint 12 — Discovery Engine v2 (anomaly detection, temporal/sequence mining, feature importance, interaction discovery)

**Objective:** Four additional, well-understood discovery methods, each an independent, additively-versioned submodule.

**Why before the next sprint:** These methods carry ordinary (not elevated) governance requirements and directly reuse existing RE-2 structures (`SetupEpisode`/`ActivationEvent` for sequence mining), making them lower-risk than the causal/regime/representation-learning methods reserved for Sprint 13.

**Deliverables:** four new submodules under `atlas.research.discovery`, each producing `Finding`s tagged with their own method/version.

**New packages/modules:** none new at the top level — submodules within the existing `atlas.research.discovery`.

**Public interfaces introduced:** one discovery function per method, following Sprint 10's established shape.

**Data models introduced:** none new.

**Dependency changes:** RE-2's `setup_profiling` outputs (read, reused, never modified) for sequence mining.

**Test strategy:** planted-relationship/planted-sequence fixtures per method, mirroring Sprint 10's own discipline; a test confirming feature-importance output correctly feeds back into candidate feature generation (the loop named in the blueprint §6) without creating a circular dependency.

**Certification requirements:** sprint-level only.

**Definition of Done:** all four methods produce correctly-tagged Findings against both hand-built and real data; none requires any change to Formalization, Memory, or the Knowledge Graph's own contracts; full suite + Ruff green.

**Risks:** *Architectural* — feature-importance's feedback loop into candidate feature generation is the one place this sprint could accidentally create a cycle; test the dependency direction explicitly. *Dependency* — none new beyond RE-2 reuse. *Testing* — sequence-mining fixtures need genuinely time-ordered planted patterns, not just co-occurrence, to prove the method does what it claims. *Future-extension* — this sprint should require zero changes to Sprint 10's Formalization contract, proving that contract was generalized correctly the first time.

---

### Sprint 13 — Discovery Engine v3 (causal discovery, regime discovery, representation learning)

**Objective:** The three higher-governance discovery methods, each requiring the extra scrutiny machinery the blueprint calls for.

**Why before the next sprint:** These methods produce claims (causal) or artifacts (candidate regimes, learned representations) that need explicit, mandatory extra handling before they may participate in a Hypothesis at all — building this scrutiny machinery is substantial enough to deserve its own sprint, separate from Sprint 12's lower-risk methods.

**Deliverables:** causal discovery (every Finding tagged `claim_strength: causal`, distinct from `associative`, with a higher formalization bar enforced structurally, not just documented); regime discovery (producing Candidate Regime Definitions — research-only, never touching Market Context's frozen `VolatilityRegime`); representation learning (every resulting Candidate Feature carrying a mandatory `interpretability_status` field and a higher review bar before promotion or Hypothesis participation).

**New packages/modules:** none new at the top level — three submodules within `atlas.research.discovery`.

**Public interfaces introduced:** the three discovery functions; an explicit `claim_strength` check enforced at Formalization time; an explicit `interpretability_status` check enforced at Promotion review time.

**Data models introduced:** `claim_strength` tag (on `Finding`); `interpretability_status` tag (on `Feature`); Candidate Regime Definition.

**Dependency changes:** Market Context (models only, read-only, to confirm a Candidate Regime Definition never collides with or shadows `VolatilityRegime`).

**Test strategy:** a dedicated test proving Formalization enforces a stricter bar for `claim_strength: causal` Findings than for `associative` ones; a dedicated test proving a representation-learned feature with an unresolved `interpretability_status` cannot pass Promotion review; a test proving Candidate Regime Definitions never alias or override `atlas.market_context.models.VolatilityRegime`.

**Certification requirements:** sprint-level only.

**Definition of Done:** all three methods work against real data, each with its own governance guarantee proven by a failing test when violated, not merely documented; full suite + Ruff green.

**Risks:** *Architectural* — this sprint carries the highest risk of quietly weakening a governance guarantee "just to get a promising result through"; any change to the causal bar or the interpretability gate must be treated as a Principle-level amendment, not an implementation convenience. *Dependency* — the Market Context read-only dependency here must be audited to confirm it stays read-only and version-locked, never drifting into a soft dependency on Market Context's own evolution. *Testing* — governance guarantees need adversarial tests (a deliberately low-interpretability feature, a deliberately weak causal claim) as much as happy-path ones. *Future-extension* — any future discovery method producing a similarly elevated claim type should reuse the `claim_strength`/`interpretability_status` pattern rather than inventing a new one.

---

### Sprint 14 — AI Research Assistant (Milestone: Phase N4 Complete certification)

**Objective:** The advisory AI layer, and full certification of the complete Research Engine.

**Why before the next sprint:** This is deliberately the last sprint of the roadmap. Its value depends entirely on the rich, populated, already-trustworthy ledger and knowledge base built by Sprints 1–13; its safety depends entirely on the write-boundary enforcement proven at every prior milestone.

**Deliverables:** `atlas.research.assistant` — read access to the full ledger and Knowledge Graph; write access limited to draft `Hypothesis`/`Experiment` proposals (always `PROPOSED`) and Annotations; the per-version, immutable `provenance`/`derived_from` mechanism proven across every entity type it can touch; **the full Phase N4 Complete certification pass**: a whole-project dependency audit confirming `atlas.research.assistant` is the *only* package in the entire `atlas` tree with an LLM-service dependency, a real-data end-to-end run exercising Discovery → Formalization → (AI-drafted alternative) → Validation → Ranking → Promotion review side by side, and a full documentation review of every principle in the constitutional reference against the finished implementation.

**New packages/modules:** `atlas.research.assistant`.

**Public interfaces introduced:** `propose_hypothesis()`, `propose_experiment()`, `annotate()` — each producing only draft/annotation objects.

**Data models introduced:** `Annotation` (named in the blueprint's relationship graph, defined here); per-version `provenance`/`derived_from` fields retrofitted onto every entity type that can carry AI-originated content (a schema addition, not a redesign, since Sprint 1's models already anticipated this field per the blueprint).

**Dependency changes:** the one, explicitly disclosed AI/LLM service dependency, confined entirely to this package.

**Test strategy:** a dedicated test proving no AI-authored object can ever reach `VALIDATED`, `APPROVED`, or any production-adjacent state directly; a dedicated test proving an AI-drafted Hypothesis, once refined by a human, retains its full provenance lineage (`derived_from`) rather than collapsing to a single author field; the milestone's own whole-project dependency and real-data audits.

**Certification requirements:** **full milestone certification** — this is "Phase N4 Complete."

**Definition of Done:** the AI Assistant can propose a hypothesis and an experiment, and explain a finding, entirely within its read/draft/annotate boundary; every principle in `research-engine-design-principles.md` has at least one test that would fail if it were violated; a certification report is produced covering the entire Phase N4 build, from Sprint 1 through this sprint; full suite + Ruff green.

**Risks:** *Architectural* — this is the sprint most likely to face pressure to "let the AI just do this one obviously-correct thing automatically"; the roadmap and the constitutional reference must both be treated as non-negotiable here, precisely because this is where the temptation is strongest. *Dependency* — the isolated-LLM-dependency audit is the single most important dependency check in the whole roadmap; it must be re-run, not assumed, at this milestone. *Testing* — provenance-lineage testing must cover multi-generation refinement (AI → human → AI-annotated-again), not only the single-hop case. *Future-extension* — any future AI capability (a second model, a different provider, a new proposal type) must fit inside this same read/draft/annotate boundary without requiring a new exception to Section VI.

---

## Final roadmap table

| Sprint | Objective | Dependencies | Est. complexity | Major risks | Expected certification |
|---|---|---|---|---|---|
| 1 | Core Entities | none (atlas.core only) | Medium | Getting a field wrong is expensive later | Sprint-level |
| 2 | Ledger | Sprint 1 | Medium | Weak similarity check violates II.4 | Sprint-level |
| 3 | Replay Bridge | Sprint 1 | Low | Highest-risk external dependency | Sprint-level (audit load-bearing) |
| 4 | Feature Registry | Sprints 1, 3 | Medium | Candidate-feature code-execution risk | Sprint-level |
| 5 | Experiment Builder (Stage A) + Statistics | Sprints 1–4 | Medium | Decision-shaped concepts leaking in early | Sprint-level |
| 6 | Validation | Sprint 5 | High | First stochastic component; correction must be mandatory | Sprint-level |
| 7 | Ranking | Sprints 5–6, 2 | Low | Ranking assuming every entry has a Realization | Sprint-level |
| 8 | Realizations + Backtesting | Sprints 1–7, 3 | High | Reintroducing strategy-first thinking by convenience | Sprint-level |
| 9 | Promotion | Sprints 1–8 | Medium | Confusing this package with production certification itself | **Full — Phase N4 Core** |
| 10 | Discovery v1 + Formalization | Sprints 4, 9 | Medium | Finding treated as validated anywhere downstream | Sprint-level |
| 11 | Memory (full) + Knowledge Graph | Sprints 2, 10 | Medium | Graph projection becoming a second source of truth | Sprint-level |
| 12 | Discovery v2 | Sprints 4, 10 | Medium | Feature-importance feedback loop creating a cycle | Sprint-level |
| 13 | Discovery v3 | Sprints 4, 10, Market Context (read-only) | High | Governance guarantees weakened under pressure | Sprint-level |
| 14 | AI Research Assistant | Sprints 1–13 | High | The single strongest temptation to bypass a mandatory gate | **Full — Phase N4 Complete** |

Optimize this sequence for long-term maintainability, not shortest calendar time: no sprint should ever be reordered ahead of a dependency it's marked as needing, and the two full-certification milestones (9 and 14) should never be skipped or downgraded to sprint-level checks, regardless of schedule pressure.
