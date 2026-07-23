"""
Phase N4 Sprint 5. Experiment Builder's pure computation core plus its one
Ledger-touching orchestration function - see this package's own __init__.py
for the full boundary and cache-hit semantics.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional, Union

from atlas.market_engine.models import MarketState
from atlas.research.backtesting.models import ResearchDecision
from atlas.research.backtesting.service import execute_realization
from atlas.research.features.models import FeatureComputed, FeatureOutcome
from atlas.research.features.registry import REGISTRY, FeatureRegistration
from atlas.research.fingerprint import compute_fingerprint
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    CriterionResult,
    DatasetManifest,
    EvaluationMode,
    Experiment,
    Hypothesis,
    ProvenanceKind,
    Realization,
    RealizationKind,
    RealizationStatus,
    RealizationTemplateKind,
    TargetKind,
)
from atlas.research.ports import ExperimentStore, RealizationStore
from atlas.research.replay_bridge import ReplayFrame
from atlas.research.service import build_dataset_manifest, current_code_version


def evaluate_feature_series(states: list[MarketState], registration: FeatureRegistration) -> tuple[FeatureOutcome, ...]:
    """One FeatureOutcome per input MarketState position, using that
    position's own trailing window (bounded to the registration's
    required window size) - mirrors atlas.replay_engine.service's own
    per-position bounded-trailing-window convention
    (_market_context_for_position) exactly, so this never re-scans an
    ever-larger prefix for O(n^2) cost on a large dataset."""
    required = registration.feature.definition["window"]
    return tuple(
        registration.evaluate(states[max(0, i - required + 1): i + 1], registration.feature)
        for i in range(len(states))
    )


def resolve_feature_pins(
    feature_ids, registry: tuple[FeatureRegistration, ...] = REGISTRY
) -> tuple[dict, ...]:
    """Resolves each feature_id against the static Registered-tier
    REGISTRY only - Ledger-stored Candidate/Promoted features are not
    resolved this sprint (a disclosed, minor limitation of Sprint 5's own
    minimal scope, not a defect: nothing in the frozen Blueprint or
    Design Principles requires it, and Sprint 4 ships exactly one
    Registered feature). Raises if any feature_id is unregistered - an
    unresolvable reference is a real authoring error, never silently
    skipped. Sorted by feature_id before returning, for the same
    "never depend on an incidental ordering" reason
    atlas.research.fingerprint's own module docstring already states."""
    by_id = {r.feature.feature_id: r.feature for r in registry}
    pins = []
    for feature_id in feature_ids:
        feature = by_id.get(feature_id)
        if feature is None:
            raise ValueError(f"feature_id {feature_id!r} is not registered in the Feature Registry")
        pins.append({"feature_id": feature.feature_id, "version": feature.version, "fingerprint": feature.fingerprint})
    return tuple(sorted(pins, key=lambda p: p["feature_id"]))


def compute_semantic_fingerprint(
    hypothesis: Hypothesis, dataset_manifest: DatasetManifest, realization_id: Optional[str] = None,
) -> str:
    """{hypothesis_id, realization_id, dataset REQUEST fields,
    evaluation_mode} only - see models.py's own Experiment docstring for
    the full reasoning. realization_id defaults to None (Stage A, every
    call site through Sprint 7); Sprint 8's build_realization_experiment()
    is the first caller to pass a real one, for a Stage B/C Experiment.
    evaluation_mode is always SINGLE (no Monte Carlo/walk-forward until
    Sprint 6). feature_refs is not separately hashed here: it lives on
    the (immutable, append-only) Hypothesis itself, already captured
    transitively via hypothesis_id."""
    return compute_fingerprint({
        "hypothesis_id": hypothesis.hypothesis_id,
        "realization_id": realization_id,
        "dataset_request": {
            "symbol": dataset_manifest.symbol, "timeframe": dataset_manifest.timeframe,
            "requested_start": dataset_manifest.requested_start, "requested_end": dataset_manifest.requested_end,
        },
        "evaluation_mode": EvaluationMode.SINGLE.value,
    })


def compute_execution_fingerprint(
    semantic_fingerprint: str, code_version: Optional[str],
    dataset_manifest: DatasetManifest, feature_pins: tuple[dict, ...],
    realization_fingerprint: Optional[str] = None,
) -> str:
    """{semantic_fingerprint, code_version, seed, dataset RESOLVED fields,
    feature_pins, realization_fingerprint} - every axis that could change
    the computed result, nested rather than duplicated. seed is always
    None this sprint (SINGLE evaluation_mode has no stochastic component).
    realization_fingerprint defaults to None (Stage A); Sprint 8 pins the
    full Realization.fingerprint here, not just its id, so a Realization's
    own fingerprint changing (e.g. a different template_kind) changes
    every downstream execution_fingerprint that references it too."""
    return compute_fingerprint({
        "semantic_fingerprint": semantic_fingerprint,
        "code_version": code_version,
        "seed": None,
        "dataset_resolved": {
            "row_count": dataset_manifest.row_count,
            "first_occurred_at": dataset_manifest.first_occurred_at,
            "last_occurred_at": dataset_manifest.last_occurred_at,
            "source_description": dataset_manifest.source_description,
        },
        "feature_pins": list(feature_pins),
        "realization_fingerprint": realization_fingerprint,
    })


def construct_realization(
    hypothesis: Hypothesis, kind: RealizationKind, version: str,
    parameters: Mapping[str, Union[int, float, str, bool]], template_kind: Optional[RealizationTemplateKind],
    provenance: ProvenanceKind, realization_id: str, created_at: str, tracker: RealizationStore,
) -> Realization:
    """Sprint 8. Constructs and records (via the Sprint 2 RealizationStore,
    unused by any production code path until now) a Realization for
    `hypothesis`. fingerprint is a curated projection of {hypothesis_id,
    kind, version, parameters, template_kind} - excludes realization_id
    (storage key), status/provenance/created_at (lifecycle/audit, never
    identity), matching Feature's own corrected fingerprint discipline.
    template_kind participates because it changes executable meaning: two
    Realizations differing only in template_kind must fingerprint
    differently - see Realization.template_kind's own docstring.

    A Realization's own lifecycle is independent of any one Experiment -
    the same Realization may back many Experiments across different
    datasets (see build_realization_experiment()) - so this is a
    standalone construction step, never folded into experiment building
    itself."""
    fingerprint = compute_fingerprint({
        "hypothesis_id": hypothesis.hypothesis_id,
        "kind": kind.value,
        "version": version,
        "parameters": dict(parameters),
        "template_kind": template_kind.value if template_kind is not None else None,
    })
    realization = Realization(
        realization_id=realization_id, hypothesis_id=hypothesis.hypothesis_id, kind=kind, version=version,
        parameters=parameters, status=RealizationStatus.CONSTRUCTED, provenance=provenance,
        created_at=created_at, fingerprint=fingerprint, template_kind=template_kind,
    )
    tracker.register(realization)
    return realization


def _evaluate_feature_criterion(criterion: AcceptanceCriterion, feature_series: tuple[FeatureOutcome, ...]) -> CriterionResult:
    """Mechanical only - never a judgment call, the same posture
    atlas.research.service.evaluate_criterion already established one
    layer down for ProfilingReport-targeted criteria. This is
    deliberately NOT the same richer statistics
    atlas.research.statistics.compute_evidence() separately computes
    (effect size, confidence interval) - just enough arithmetic (a
    sample mean, compared to the hypothesis's own pre-declared threshold)
    to populate Experiment.criteria_results/passed, which Sprint 28
    already requires as non-optional fields on every Experiment. The two
    packages compute a mean independently rather than one depending on
    the other - see this package's own __init__.py for why."""
    values = [outcome.value for outcome in feature_series if isinstance(outcome, FeatureComputed)]
    if not values:
        return CriterionResult(
            criterion=criterion, actual_value=None, passed=False,
            reason="no computable Feature values across the dataset",
        )
    if criterion.kind == CriterionKind.MEAN_ABOVE_THRESHOLD:
        mean = sum(values) / len(values)
        return CriterionResult(criterion=criterion, actual_value=mean, passed=mean >= criterion.threshold, reason=None)
    raise ValueError(f"unhandled CriterionKind for TargetKind.FEATURE: {criterion.kind!r}")


@dataclass(frozen=True)
class ExperimentBuildOutcome:
    """experiment_builder's own local return-value wrapper - not one of
    the blueprint's entities, just a way to hand back the Experiment
    together with whether it was newly executed and the raw per-bar
    Feature series statistics will need. feature_series maps feature_id
    -> that feature's own per-bar outcomes across the dataset.

    decision_sequence (Sprint 8) is populated only by
    build_realization_experiment() (Stage B/C) - None for every Stage A
    Experiment (build_experiment()) and also None on a Stage B/C cache
    hit, where execute_realization() is never re-run. Returned raw here,
    exactly like feature_series, for atlas.research.statistics's own
    extension to separately turn into Evidence - this package never
    computes Evidence itself, decision-bearing or not."""

    experiment: Experiment
    is_new_execution: bool
    feature_series: Mapping[str, tuple[FeatureOutcome, ...]]
    decision_sequence: Optional[tuple[ResearchDecision, ...]] = None


def build_experiment(
    hypothesis: Hypothesis, states: list[MarketState],
    requested_start: str, requested_end: str, source_description: str,
    generated_at: datetime, experiment_id: str, tracker: ExperimentStore,
) -> ExperimentBuildOutcome:
    """Deterministic. Every acceptance criterion on `hypothesis` must be
    TargetKind.FEATURE - this sprint does not evaluate FACT/SETUP
    criteria (that remains atlas.research.service.run_experiment's own,
    untouched job); a mixed hypothesis is a scope error, raised
    explicitly, never silently partially handled. Every FEATURE
    criterion's target (a feature_id) must already be listed in
    hypothesis.feature_refs - an unlisted reference is a real authoring
    inconsistency, caught here rather than silently accepted."""
    if states:
        actual_symbol = states[0].symbol.ticker
        actual_timeframe = states[0].timeframe.value
        if actual_symbol != hypothesis.dataset_symbol or actual_timeframe != hypothesis.dataset_timeframe:
            raise ValueError(
                f"states are for {actual_symbol}/{actual_timeframe}, but hypothesis "
                f"{hypothesis.hypothesis_id!r} specifies {hypothesis.dataset_symbol}/{hypothesis.dataset_timeframe}"
            )

    for criterion in hypothesis.acceptance_criteria:
        if criterion.target_kind != TargetKind.FEATURE:
            raise ValueError(
                f"{hypothesis.hypothesis_id}: build_experiment only supports TargetKind.FEATURE criteria "
                f"this sprint, got {criterion.target_kind.value!r} for {criterion.target!r}"
            )
        if criterion.target not in hypothesis.feature_refs:
            raise ValueError(
                f"{hypothesis.hypothesis_id}: criterion targets feature_id {criterion.target!r}, "
                f"which is not listed in the hypothesis's own feature_refs {hypothesis.feature_refs}"
            )

    manifest = build_dataset_manifest(states, requested_start, requested_end, source_description, generated_at)
    semantic_fingerprint = compute_semantic_fingerprint(hypothesis, manifest)

    feature_ids = sorted({c.target for c in hypothesis.acceptance_criteria})
    feature_pins = resolve_feature_pins(feature_ids)
    registrations_by_id = {r.feature.feature_id: r for r in REGISTRY}
    feature_series = {
        feature_id: evaluate_feature_series(states, registrations_by_id[feature_id]) for feature_id in feature_ids
    }

    code_version = current_code_version()
    execution_fingerprint = compute_execution_fingerprint(semantic_fingerprint, code_version, manifest, feature_pins)

    exact_match = next(
        (e for e in tracker.for_hypothesis(hypothesis.hypothesis_id) if e.execution_fingerprint == execution_fingerprint),
        None,
    )
    if exact_match is not None:
        return ExperimentBuildOutcome(experiment=exact_match, is_new_execution=False, feature_series=feature_series)

    criteria_results = tuple(
        _evaluate_feature_criterion(c, feature_series[c.target]) for c in hypothesis.acceptance_criteria
    )
    passed = all(r.passed for r in criteria_results)

    experiment = Experiment(
        experiment_id=experiment_id, hypothesis_id=hypothesis.hypothesis_id,
        executed_at=generated_at.astimezone(timezone.utc).isoformat(), code_version=code_version,
        dataset_manifest=manifest, criteria_results=criteria_results, passed=passed,
        profiling_report_path=None,
        semantic_fingerprint=semantic_fingerprint, execution_fingerprint=execution_fingerprint,
    )
    tracker.record(experiment)
    return ExperimentBuildOutcome(experiment=experiment, is_new_execution=True, feature_series=feature_series)


def build_realization_experiment(
    hypothesis: Hypothesis, realization: Realization, frames: list[ReplayFrame],
    requested_start: str, requested_end: str, source_description: str,
    generated_at: datetime, experiment_id: str, tracker: ExperimentStore,
) -> ExperimentBuildOutcome:
    """Sprint 8, Stage B/C. Mirrors build_experiment()'s own construction
    logic exactly - same symbol/timeframe validation, same TargetKind.FEATURE-
    only criteria check (a Realization tests the same underlying Hypothesis,
    whose acceptance_criteria shape is unchanged), same cache-hit-vs-new-
    execution decision - extended to (a) thread realization.realization_id
    into semantic_fingerprint and realization.fingerprint into
    execution_fingerprint (see both functions' own docstrings), and (b)
    additionally execute the Realization (atlas.research.backtesting.
    execute_realization()) to produce a decision sequence, returned raw via
    ExperimentBuildOutcome.decision_sequence for Statistics's own extension
    to separately turn into Evidence - this function never computes
    Evidence itself.

    execute_realization() is deliberately called AFTER the cache-hit check,
    not before: unlike feature_series (which execution_fingerprint's own
    RESOLVED dataset facts structurally require), the decision sequence
    itself is never a fingerprint input - only realization.fingerprint, an
    already-known value, is - so a cache hit skips the backtesting compute
    cost entirely, not just the Ledger write.

    Takes frames (not states) as its one dataset parameter - states are
    derived internally (frame.market_state) for reuse of
    build_dataset_manifest()/evaluate_feature_series(), and frames are
    passed to execute_realization() unchanged. A single parameter, never
    two independently-supplied sequences that could silently disagree."""
    states = [frame.market_state for frame in frames]
    if states:
        actual_symbol = states[0].symbol.ticker
        actual_timeframe = states[0].timeframe.value
        if actual_symbol != hypothesis.dataset_symbol or actual_timeframe != hypothesis.dataset_timeframe:
            raise ValueError(
                f"frames are for {actual_symbol}/{actual_timeframe}, but hypothesis "
                f"{hypothesis.hypothesis_id!r} specifies {hypothesis.dataset_symbol}/{hypothesis.dataset_timeframe}"
            )
    if realization.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"realization {realization.realization_id!r} targets hypothesis_id "
            f"{realization.hypothesis_id!r}, not {hypothesis.hypothesis_id!r}"
        )

    for criterion in hypothesis.acceptance_criteria:
        if criterion.target_kind != TargetKind.FEATURE:
            raise ValueError(
                f"{hypothesis.hypothesis_id}: build_realization_experiment only supports TargetKind.FEATURE "
                f"criteria this sprint, got {criterion.target_kind.value!r} for {criterion.target!r}"
            )
        if criterion.target not in hypothesis.feature_refs:
            raise ValueError(
                f"{hypothesis.hypothesis_id}: criterion targets feature_id {criterion.target!r}, "
                f"which is not listed in the hypothesis's own feature_refs {hypothesis.feature_refs}"
            )

    manifest = build_dataset_manifest(states, requested_start, requested_end, source_description, generated_at)
    semantic_fingerprint = compute_semantic_fingerprint(hypothesis, manifest, realization_id=realization.realization_id)

    feature_ids = sorted({c.target for c in hypothesis.acceptance_criteria})
    feature_pins = resolve_feature_pins(feature_ids)
    registrations_by_id = {r.feature.feature_id: r for r in REGISTRY}
    feature_series = {
        feature_id: evaluate_feature_series(states, registrations_by_id[feature_id]) for feature_id in feature_ids
    }

    code_version = current_code_version()
    execution_fingerprint = compute_execution_fingerprint(
        semantic_fingerprint, code_version, manifest, feature_pins, realization_fingerprint=realization.fingerprint,
    )

    exact_match = next(
        (e for e in tracker.for_hypothesis(hypothesis.hypothesis_id) if e.execution_fingerprint == execution_fingerprint),
        None,
    )
    if exact_match is not None:
        return ExperimentBuildOutcome(
            experiment=exact_match, is_new_execution=False, feature_series=feature_series, decision_sequence=None,
        )

    criteria_results = tuple(
        _evaluate_feature_criterion(c, feature_series[c.target]) for c in hypothesis.acceptance_criteria
    )
    passed = all(r.passed for r in criteria_results)
    decision_sequence = execute_realization(realization, frames)

    experiment = Experiment(
        experiment_id=experiment_id, hypothesis_id=hypothesis.hypothesis_id,
        executed_at=generated_at.astimezone(timezone.utc).isoformat(), code_version=code_version,
        dataset_manifest=manifest, criteria_results=criteria_results, passed=passed,
        profiling_report_path=None, realization_id=realization.realization_id,
        semantic_fingerprint=semantic_fingerprint, execution_fingerprint=execution_fingerprint,
    )
    tracker.record(experiment)
    return ExperimentBuildOutcome(
        experiment=experiment, is_new_execution=True, feature_series=feature_series,
        decision_sequence=decision_sequence,
    )
