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
.fingerprint, neither depends on the other) - the same "Statistics must
not depend on Backtesting even implicitly" posture the roadmap's own Sprint
5 risk note names, applied here as the general principle it actually is:
each of Sprint 5's two packages stays independently reasoned-about and
independently testable.
"""
