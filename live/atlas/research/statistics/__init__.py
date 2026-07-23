"""
Phase N4 Sprint 5 (Statistics), corrected Sprint 6.1. Pure, stateless
statistical computation over already-completed execution results -
nothing else. Given an already-built Experiment
(atlas.research.experiment_builder's own job) and the raw per-bar Feature
series that produced its criteria_results, computes Evidence: raw sample
size, an autocorrelation-corrected effective_sample_size (Sprint 6.1 -
see service.py's own module docstring for the exact formula and its
justification), mean, sample standard deviation, a 95% confidence
interval, and a threshold-relative effect size, per FEATURE-targeted
criterion.

Never touches the Ledger (no import of atlas.research.stores), never
re-evaluates a Feature or re-fetches data (no import of
atlas.research.features.registry or any Replay Engine/Replay Bridge
module - only the FeatureOutcome/FeatureComputed TYPES from
atlas.research.features.models, for reading already-computed values),
never decides caching or reuse (that stays entirely
atlas.research.experiment_builder's job - see that package's own
__init__.py), and never produces a verdict: Evidence.metrics carries only
computed numbers, satisfying Design Principle III.1 (evidence is
computed, not judged) literally - there is no pass/fail field anywhere on
Evidence.

Deliberately zero dependency on atlas.research.experiment_builder in
either direction (both packages depend on atlas.research.features/.models/
.fingerprint, neither depends on the other) - each of Sprint 5's two
packages stays independently reasoned-about and independently testable.

--- Sprint 8: compute_decision_sequence_evidence() ---

Extends this package with a second, independent Evidence-computing
function - the decision-sequence counterpart to compute_evidence() above,
computing decision-frequency metrics from an already-executed decision
sequence (atlas.research.backtesting's own output). This is a TYPE-only
dependency on atlas.research.backtesting.models (ResearchDecision/
ResearchDispositionKind), exactly the same posture already established for
atlas.research.features.models above: reads an already-computed value,
never imports or calls atlas.research.backtesting.service/.factory/
.templates/.ports - Statistics still never re-executes anything, and the
"Statistics must not depend on Backtesting" posture the roadmap's own
Sprint 5 risk note named is honored in its intended sense (no execution
machinery, ever) while still being able to read the data type that
machinery produces. Still no dependency on
atlas.research.experiment_builder, and still pure/no-I/O -
decision_sequence_path is a plain pass-through field, never written here.

--- Sprint 8.1: Validation integration ---

The Sprint 8 architectural finding: atlas.research.validation already
consumes any Evidence whose metrics follow the {target}__mean/__std_dev/
__sample_size/__effective_sample_size/... key family, regardless of what
computed them - it has been criterion-target-agnostic since Sprint 5.
compute_decision_sequence_evidence() is revised (not replaced) to also
populate that exact family for each requested decision-rate target - via
_series_statistics_metrics(), one shared helper extracted verbatim (never
altered) from compute_evidence()'s own formula block, so Feature-based
Evidence remains numerically identical in every case. decision_rate_target()
is the one authoritative ResearchDispositionKind -> target-name mapping
(no_action_rate/enter_long_rate/enter_short_rate/exit_rate) - never
reproduced via scattered string concatenation. Only criteria whose
target_kind is TargetKind.DECISION_SEQUENCE are processed; an unrecognized
target name fails explicitly, never silently skipped.

Gains one further type-only dependency, atlas.research.replay_bridge (the
ReplayFrame type only, for compute_decision_sequence_evidence()'s own
`frames` parameter - used to assert decisions/frames share the same length,
never to fetch or re-derive anything). atlas.research.validation and
atlas.research.ranking are untouched by this sprint - proven, not merely
asserted, by test_research_sprint8_1_validation_ranking_integration.py's
own dependency audit.
"""
