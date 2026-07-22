"""
Phase N4 Sprint 5 (Experiment Builder, Stage A). Hypothesis + DatasetManifest
-> a decision-free Experiment, fingerprinted, recorded append-only. No
Realization, no decision sequence, no strategy anywhere in this package -
`Experiment.realization_id` is never set (always None, the Stage-A default
Sprint 1 already established).

Owns: deterministic Experiment construction; semantic_fingerprint/
execution_fingerprint computation; exact Feature reference pinning by
feature_id/version/fingerprint; the cache-hit-vs-new-execution decision;
append-only Experiment recording via the Ledger's own ExperimentStore
Protocol (atlas.research.ports); producing the raw per-bar Feature series
as "Evidence inputs" for atlas.research.statistics to separately consume.

Never computes Evidence itself (that is atlas.research.statistics's own,
separate job - see that package's own __init__.py) and never transitions
Hypothesis.status - models.py's own docstring already assigns every such
transition exclusively to Formalization (Sprint 10), Validation (Sprint
6), Ranking (Sprint 7), and Promotion (Sprint 9); this package is not on
that list and does not add itself to it.

Depends on atlas.research.features (Sprint 4, read-only - REGISTRY lookups
and evaluate() calls only, never modified) and reuses two existing,
unmodified Sprint 28 functions (atlas.research.service.build_dataset_manifest,
.current_code_version) rather than re-deriving either. Does not import
atlas.replay_engine or atlas.research.replay_bridge at all:
build_experiment() takes an already-resolved list[MarketState] as a plain
parameter, the same shape atlas.research.service.run_experiment() already
established - only the test suite calls Replay Bridge, to produce real
fixture data.

--- Cache-hit semantics, resolved precisely ---

execution_fingerprint depends on RESOLVED dataset facts (row count, actual
first/last bar) that are only knowable after the data has actually been
fetched and every referenced Feature evaluated across it. This means the
cache-hit check can only run AFTER that work has already happened, not
before - Sprint 5's caching avoids a duplicate Ledger write (and,
downstream, a duplicate Evidence computation, at the caller's own
discretion), never the compute cost itself. Skipping the run entirely on
a partial match (e.g. semantic_fingerprint + code_version alone, without
the resolved dataset facts) would be exactly the shortcut Design
Principle VII.3 forbids: it would prevent ever discovering that the
underlying dataset had changed since the question was last asked.
"""
