"""
Phase N4 Sprint 8 (Realizations + Backtesting). This package is the pure
execution core the roadmap describes: given one Realization (a
TEMPLATED_STRATEGY or STRATEGY_VARIANT subtype only - STATISTICAL_TEST/
CONTEXT_FILTER/RISK_INPUT have no executable meaning yet) and an
already-fetched sequence of ReplayFrame, produce a deterministic decision
sequence. Computes zero statistics (the blueprint's own words) - it never
validates hypotheses, ranks hypotheses, or promotes hypotheses; those
remain atlas.research.validation/.ranking/(future) .promotion's own
exclusive concerns.

No new Ledger-tracked data model - the roadmap's own Sprint 8 text is
explicit ("Data models introduced: none new"). ResearchDecision
(backtesting/models.py) is a package-local supporting value, not a new
blueprint entity, exactly mirroring atlas.research.ranking.models.
RankingPolicy's own precedent. A full decision sequence is serialized to a
file whose path is recorded in Evidence.decision_sequence_path - a field
already frozen since Sprint 1, mirroring Experiment.profiling_report_path's
own established pattern exactly. No second persistence abstraction is
introduced.

ResearchStrategyPlugin (ports.py) is structurally distinct from
atlas.strategy_engine.ports.StrategyPlugin per Research Engine Design
Principles VIII.4 - different property/method names, not merely a
different return-type annotation, because @runtime_checkable Protocol
isinstance() checks only verify name/signature presence. This package
never imports atlas.strategy_engine, and nothing in atlas.strategy_engine
imports this package - proven mechanically by
test_research_backtesting_dependencies.py and by the existing, certified
atlas.strategy_engine dependency audit from the other side.

ResearchStrategyFactory (factory.py) is a small, closed, code-reviewed
dispatch table keyed on (Realization.template_kind, Realization.version) -
never a runtime plugin registry, never importlib/entry-point discovery.
Its dispatch decision depends only on those two fields, never on
configuration, environment, feature flags, or runtime state - the Sprint 8
purity contract that makes execute_realization()'s own end-to-end
determinism hold by construction, not merely by convention.

Dependencies: atlas.research.models, this package's own local modules, and
atlas.research.replay_bridge - for the ReplayFrame type only, never for
fetching data (execute_realization() receives an already-fetched frame
sequence, mirroring atlas.research.experiment_builder.build_experiment()'s
own "receive already-fetched data, never fetch it yourself" discipline).
The ReplayFrame type is sourced through replay_bridge's own re-export, not
by importing atlas.replay_engine.models directly - Sprint 3's own frozen
boundary test proves atlas.research.replay_bridge is the ONLY Research
Engine module permitted to import atlas.replay_engine at all; a second
module needing the type directly is that module's own "signal to widen
this module's surface, never add a second gateway," not license to import
atlas.replay_engine a second time. Never atlas.research.features,
.statistics, .validation, .ranking, .stores, .serialization, .fingerprint,
or any N1-N3 production package.
"""
