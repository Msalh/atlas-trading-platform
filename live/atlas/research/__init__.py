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

Every later Sprint 6-14 package the roadmap describes
(atlas.research.validation, .ranking, .discovery, .formalization,
.backtesting, .memory, .knowledge_graph, .assistant, .promotion) does not
exist yet.
"""
