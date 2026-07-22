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
storage, no new dependency. Every later Sprint 1-14 package the roadmap
describes (atlas.research.discovery, .formalization, .experiment_builder,
.replay_bridge, .backtesting, .statistics, .validation, .ranking, .memory,
.knowledge_graph, .assistant, .promotion) does not exist yet.
"""
