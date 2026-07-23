"""
Sprint 28. The Research Engine - the smallest complete implementation
proving the architecture designed across Sprints 27/27.5 actually works in
practice with one real research cycle:

    Hypothesis -> DatasetManifest -> (existing, unchanged) Profiler
    -> Experiment -> ResearchReport

Sits above atlas.market_engine, atlas.rule_engine, atlas.setup_engine, and
atlas.profiling (imports all four; none of them import this package - same
one-way dependency rule enforced everywhere else in this project). Reuses
atlas.profiling completely unchanged - this package never re-derives a
firing rate or a detection count.

Sprint 28 scope, deliberately: acceptance criteria can only reference what
the existing Profiler already measures (detection/firing-rate/sample-size
questions) - no forward returns, no MAE/MFE, no statistical modeling, no
live monitoring. A Hypothesis registered this Sprint is an observational
claim about how often a fact or setup fires, never an edge or profitability
claim. See docs/market_engine/roadmap.md's Sprint 28 entry and the Sprint
27/27.5 design-review record for the full research methodology this
package is the first slice of.

Public entry points: atlas.research.service.run_experiment (pure) and
.build_research_report; atlas.research.stores.HypothesisRegistry /
.ExperimentTracker (file-backed persistence). Domain types:
atlas.research.models. Serialization: atlas.research.serialization.

--- Phase N4 (the Research Engine proper) ---

Sprint 28's own scope note above ("Extending this into a full promotion
lifecycle is future work, not built speculatively now") is exactly what
Phase N4 is. See docs/phase-n4-research-engine-blueprint.md,
docs/research-engine-design-principles.md, and
docs/phase-n4-implementation-roadmap.md for the full architecture, its
governing principles, and the sprint sequence - all three frozen before any
Phase N4 code was written. Phase N4 Sprint 1 (Core Entities) generalizes
Hypothesis/Experiment in place and adds Feature, Finding, Realization,
Evidence, ValidationResult, LeaderboardEntry/LeaderboardSnapshot, and
PromotionRecord to models.py, plus a new, self-contained
atlas.research.fingerprint module - data only, no new service function, no
storage, no new dependency.

Phase N4 Sprint 2 (Ledger) extends serialization.py (round-trip dict
conversion for every Sprint 1 entity, including - for backward
compatibility - the Sprint 1 fields Hypothesis/Experiment already had but
never serialized) and stores.py (one file-backed, append-only registry/
tracker per entity, same JSONL pattern as Sprint 28's own
HypothesisRegistry/ExperimentTracker; neither of those two classes is
modified), plus a new atlas.research.ports module (one Protocol per store,
proven by isinstance() in the test suite, not just claimed) and
find_similar_hypotheses() - a first, deliberately minimal, structural
(never textual) duplicate-hypothesis check.

Phase N4 Sprint 3 (Replay Bridge) adds atlas.research.replay_bridge - the
one, narrow gateway module through which the Research Engine reaches
atlas.replay_engine (Replay Engine), the first and only Research Engine
dependency on it. build_replay_frames_for_window()/fetch_replay_frames()
are direct, unmodified pass-throughs to Replay Engine's own
build_replay_output_window()/replay() - no computation, no new data model
(ReplayFrame flows through unchanged). See that module's own docstring for
the architectural resolution on how Experiment identity
(semantic_fingerprint/execution_fingerprint) must be applied once
Replay-sourced data feeds a future Experiment Builder (Sprint 5) - a
forward-looking policy note only, not code built here.

Phase N4 Sprint 4 (Feature Registry) adds atlas.research.features: a
deterministic-computation-only layer turning a MarketState window into a
named, versioned scalar, nothing more - see that package's own __init__.py
docstring for its full boundary (never creates Findings/Hypotheses,
compares Experiments, accesses the Ledger, or performs similarity search,
ranking, validation, AI reasoning, or statistical judgment). Two tiers:
Registered (registry.py, code-defined, mirroring atlas.rule_engine's own
FactRegistration/REGISTRY pattern without importing it) and Candidate
(candidate.py, a closed declarative spec + one fixed evaluator - never
dynamically generated/executed code). This sprint is the first real
computation of Feature.fingerprint (Sprint 1 left it required-but-
unpopulated).

Phase N4 Sprint 5 (Experiment Builder, Stage A + Statistics) adds two
independent packages, each with its own __init__.py docstring detailing
its full boundary: atlas.research.experiment_builder (Hypothesis +
already-resolved MarketState data -> a fingerprinted, decision-free
Experiment, append-only recorded via the Ledger's ExperimentStore
Protocol; the first real computation of semantic_fingerprint/
execution_fingerprint, and the first real use of Feature's own
feature_id/version/fingerprint as execution_fingerprint inputs) and
atlas.research.statistics (pure computation only - given an already-built
Experiment plus its raw per-bar Feature series, computes Evidence: sample
size, mean, sample standard deviation, a 95% confidence interval, and a
threshold-relative effect size). Neither package depends on the other.
Two additive enum values were needed on Sprint 1's own models.py -
TargetKind.FEATURE, CriterionKind.MEAN_ABOVE_THRESHOLD - fulfilling
exactly what that module's own docstring deferred ("extending
TargetKind/CriterionKind to reference Feature... not built yet") now that
Sprint 4 exists; FACT/SETUP/MIN_FIRING_RATE/MIN_COMPUTABLE_COUNT are
unchanged.

Phase N4 Sprint 6 (Validation) adds atlas.research.validate() - the
platform's scientific gatekeeper, the first sprint permitted to make a
scientific judgment about a result. Given one or more already-computed
in-sample and out-of-sample Evidence records (Sprint 5's own, separate
output) plus a WalkForwardSpec/MonteCarloSpec (both new, package-local
types - Sprint 1's models.py is untouched by this sprint), produces a
ValidationResult via a one-sided p-value computed exactly (math.erf, no
approximation), Bonferroni-corrected whenever more than one hypothesis
shares a dataset (structurally mandatory, not optional - a required
parameter, not merely documented), and a seeded parametric Monte Carlo
robustness check. Out-of-sample evidence is a required, non-empty
parameter - validate() cannot be called at all without it, making
Principle IV.3 (no hypothesis validated on in-sample evidence alone)
structurally impossible to violate, not merely discouraged.
Experiment.passed (Sprint 5's own mechanical threshold check) remains
categorically distinct from ValidationResult.verdict (this sprint's own
proper significance test) - see that package's own __init__.py for the
full boundary and why true nonparametric resampling is out of scope
(Evidence retains only aggregate statistics, never raw per-bar values).

Phase N4 Sprint 7 (Ranking) adds atlas.research.ranking - an
organizational layer, deliberately not a scientific scoring layer (see
that package's own __init__.py for the full reasoning: every currently-
available quantitative signal is confounded by the hypothesis author's
own threshold choice, so no honest quality score exists yet). rank()
filters to verdict == SUPPORTED only (Validation's own, already-decided
judgment - never recomputed or reinterpreted) and orders eligible entries
by validated_at descending, hypothesis_id ascending as tie-break - a
purely organizational, deterministic, non-evaluative basis.
LeaderboardEntry.score is a required float on the frozen Sprint 1 type;
Ranking sets it to the constant 1.0 for every eligible entry (never a
rank-derived transform, which would falsely imply meaningful gaps between
adjacent entries) with score_description disclosing this explicitly as a
compatibility placeholder. snapshot_leaderboard() is the one function
touching the Ledger, via the existing Sprint 2 LeaderboardSnapshotStore -
no second persistence abstraction. Three additive fields were needed on
Sprint 1's own models.py: LeaderboardEntry.validation_id (traces a rank to
the exact ValidationResult that grounded it) and
LeaderboardSnapshot.ranking_policy_id/.ranking_policy_version/
.excluded_validation_ids (policy versioning and audit preservation for
non-SUPPORTED or superseded results) - all Optional/defaulted, backward
compatible with every pre-Sprint-7 call site.

Phase N4 Sprint 8 (Realizations + Backtesting) adds atlas.research.backtesting -
a pure execution core turning one Realization (TEMPLATED_STRATEGY/
STRATEGY_VARIANT only) plus an already-fetched ReplayFrame sequence into a
deterministic decision sequence via ResearchStrategyPlugin/
ResearchStrategyFactory (see that package's own __init__.py for the full
boundary, the purity contract, and the structural-separation proof from
atlas.strategy_engine.ports.StrategyPlugin). Extends
atlas.research.experiment_builder (construct_realization(),
build_realization_experiment() - Stage A's own build_experiment() is
untouched) and atlas.research.statistics
(compute_decision_sequence_evidence() - decision-frequency metrics only,
never realized P&L, which needs price-matching and execution-cost
assumptions outside this sprint's scope). Two additive fields were needed
on frozen models.py types: RealizationTemplateKind (a new closed enum) and
Realization.template_kind (Optional, defaulted, required for
TEMPLATED_STRATEGY/STRATEGY_VARIANT and forbidden otherwise).

Deliberately does not extend atlas.research.validation/.ranking this
sprint: validate() reads Evidence.metrics keyed by
f"{criterion.target}__mean" (Feature-shaped), which
compute_decision_sequence_evidence()'s decision-frequency metrics don't
produce - a real, disclosed follow-up, not a gap silently papered over.

Every later Sprint 9-14 package the roadmap describes
(atlas.research.discovery, .formalization, .memory, .knowledge_graph,
.assistant, .promotion) does not exist yet.
"""
