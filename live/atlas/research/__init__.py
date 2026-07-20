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
"""
