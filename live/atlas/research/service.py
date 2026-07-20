"""
Sprint 28. Research Engine orchestration - the pipeline this Sprint exists
to prove works end to end:

    Hypothesis -> DatasetManifest -> (existing) Profiler -> Experiment
    -> ResearchReport

Reuses atlas.profiling.service.profile_market_state_series completely
unchanged - this module never recomputes a firing rate, a detection count,
or anything else the Profiler already produces. The only new logic here is
mechanically checking a Hypothesis's own pre-stated AcceptanceCriterion
list against that unchanged ProfilingReport output.

Pure/impure split mirrors every other layer in this project:
build_dataset_manifest and evaluate_criterion are pure; run_experiment is
pure with respect to persistence (it does not write to a HypothesisRegistry
or ExperimentTracker itself - the caller decides whether/where to record
the result, the same "orchestration decides persistence, not the pure
core" separation atlas.profiling.service already follows). No
repository-backed, DATABASE_URL-requiring wrapper is added this Sprint -
Sprint 27's own review is explicit that a component should not be built
without an immediate, exercisable consumer, and this session has no
DATABASE_URL to exercise one against. The natural next small addition,
mirroring atlas.profiling.service.profile_market_state_range exactly, is
named here rather than built blind.
"""
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import MarketState
from atlas.profiling.models import ProfilingRunConfig
from atlas.profiling.serialization import profiling_report_to_dict
from atlas.profiling.service import profile_market_state_series
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    CriterionResult,
    DatasetManifest,
    Experiment,
    Hypothesis,
    HypothesisStatus,
    ResearchReport,
    TargetKind,
)

SCHEMA_VERSION = "1.0"


def current_code_version() -> Optional[str]:
    """The git commit of the running code, or None if it genuinely cannot
    be determined (not a git checkout, git unavailable) - never silently
    omitted without the field itself being able to say so. An experiment's
    result is meaningless once the Rule/Setup Engine code it ran against
    has since changed; this is how a later reader knows which code that
    was."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    commit = result.stdout.strip()
    return commit or None


def build_dataset_manifest(
    states: list[MarketState], requested_start: str, requested_end: str,
    source_description: str, generated_at: datetime,
) -> DatasetManifest:
    """Pure. Source-agnostic by design - built identically whether `states`
    came from a repository query or a historical CSV import
    (Sprint 25B/26); describes what is actually in the resolved dataset,
    never how it got there beyond the one free-text source_description.
    Raises ValueError on an empty or mixed-symbol/timeframe list - the same
    defense-in-depth atlas.rule_engine.window_integrity already applies one
    layer down, checked again here since this function's caller may not
    have gone through that validation at all (e.g. a hand-built states list
    in a test)."""
    if not states:
        raise ValueError("cannot build a DatasetManifest from an empty states list")
    symbols = {s.symbol.ticker for s in states}
    timeframes = {s.timeframe for s in states}
    if len(symbols) > 1:
        raise ValueError(f"states contains more than one symbol: {sorted(symbols)}")
    if len(timeframes) > 1:
        raise ValueError(f"states contains more than one timeframe: {sorted(tf.value for tf in timeframes)}")

    ordered = sorted(states, key=lambda s: s.envelope.occurred_at)
    return DatasetManifest(
        symbol=ordered[0].symbol.ticker, timeframe=ordered[0].timeframe.value,
        requested_start=requested_start, requested_end=requested_end,
        row_count=len(ordered),
        first_occurred_at=ordered[0].envelope.occurred_at.isoformat(),
        last_occurred_at=ordered[-1].envelope.occurred_at.isoformat(),
        source_description=source_description,
        generated_at=generated_at.astimezone(timezone.utc).isoformat(),
    )


def evaluate_criterion(criterion: AcceptanceCriterion, report) -> CriterionResult:
    """Pure. Mechanical only - never a judgment call. `report` is an
    atlas.profiling.models.ProfilingReport (not type-hinted directly to
    avoid a hard import-time coupling neither module currently needs
    elsewhere, the same "duck-typed at the boundary" choice this project
    makes sparingly and only where it already reduces real coupling)."""
    metrics = report.fact_metrics if criterion.target_kind == TargetKind.FACT else report.setup_metrics
    profile = metrics.get(criterion.target)
    if profile is None:
        return CriterionResult(
            criterion=criterion, actual_value=None, passed=False,
            reason=f"{criterion.target!r} not found in {criterion.target_kind.value} metrics - "
                   f"check the name against the registry",
        )

    if criterion.kind == CriterionKind.MIN_FIRING_RATE:
        actual = profile.firing_rate if criterion.target_kind == TargetKind.FACT else profile.detection_rate
        if actual is None:
            return CriterionResult(
                criterion=criterion, actual_value=None, passed=False,
                reason="rate is undefined (zero computable observations) - not the same as a rate of zero",
            )
        return CriterionResult(criterion=criterion, actual_value=actual, passed=actual >= criterion.threshold, reason=None)

    if criterion.kind == CriterionKind.MIN_COMPUTABLE_COUNT:
        actual = float(profile.computable_count)
        return CriterionResult(criterion=criterion, actual_value=actual, passed=actual >= criterion.threshold, reason=None)

    raise ValueError(f"unknown criterion kind: {criterion.kind!r}")  # unreachable while CriterionKind stays closed


def run_experiment(
    hypothesis: Hypothesis, states: list[MarketState], generated_at: datetime,
    experiment_id: str, source_description: str, profiling_report_dir: Optional[Path] = None,
):
    """Pure with respect to persistence (see module docstring). Returns
    (Experiment, ProfilingReport) - the caller decides whether to hand
    either to a store. Validates that `states` actually matches what the
    hypothesis specified before running anything - a silent symbol/
    timeframe mismatch here would make the resulting Experiment describe
    the wrong dataset entirely."""
    if states:
        actual_symbol = states[0].symbol.ticker
        actual_timeframe = states[0].timeframe.value
        if actual_symbol != hypothesis.dataset_symbol or actual_timeframe != hypothesis.dataset_timeframe:
            raise ValueError(
                f"states are for {actual_symbol}/{actual_timeframe}, but hypothesis "
                f"{hypothesis.hypothesis_id!r} specifies {hypothesis.dataset_symbol}/{hypothesis.dataset_timeframe}"
            )

    manifest = build_dataset_manifest(
        states, hypothesis.dataset_start, hypothesis.dataset_end, source_description, generated_at,
    )

    config = ProfilingRunConfig(
        symbol=Symbol(manifest.symbol), timeframe=Timeframe(manifest.timeframe),
        start=datetime.fromisoformat(hypothesis.dataset_start), end=datetime.fromisoformat(hypothesis.dataset_end),
    )
    report = profile_market_state_series(states, config, generated_at)

    criteria_results = tuple(evaluate_criterion(c, report) for c in hypothesis.acceptance_criteria)
    passed = all(r.passed for r in criteria_results)

    profiling_report_path = None
    if profiling_report_dir is not None:
        profiling_report_dir.mkdir(parents=True, exist_ok=True)
        profiling_report_path = profiling_report_dir / f"{experiment_id}.profiling_report.json"
        import json
        profiling_report_path.write_text(json.dumps(profiling_report_to_dict(report), indent=2), encoding="utf-8")

    experiment = Experiment(
        experiment_id=experiment_id, hypothesis_id=hypothesis.hypothesis_id,
        executed_at=generated_at.astimezone(timezone.utc).isoformat(),
        code_version=current_code_version(),
        dataset_manifest=manifest, criteria_results=criteria_results, passed=passed,
        profiling_report_path=str(profiling_report_path) if profiling_report_path else None,
    )
    return experiment, report


def build_research_report(hypothesis: Hypothesis, experiment: Experiment) -> ResearchReport:
    """Pure. The mechanical status/conclusion derivation - never a judgment
    call, deliberately terse, no interpretation beyond "did the pre-stated
    criteria pass." A human researcher's own written reasoning belongs in
    the Hypothesis's own `statement` and, later, in a Promotion Committee
    review (Sprint 27's design) - not invented here."""
    status = HypothesisStatus.VALIDATED if experiment.passed else HypothesisStatus.REJECTED
    resolved_hypothesis = Hypothesis(
        hypothesis_id=hypothesis.hypothesis_id, registered_at=hypothesis.registered_at, author=hypothesis.author,
        statement=hypothesis.statement,
        dataset_symbol=hypothesis.dataset_symbol, dataset_timeframe=hypothesis.dataset_timeframe,
        dataset_start=hypothesis.dataset_start, dataset_end=hypothesis.dataset_end,
        acceptance_criteria=hypothesis.acceptance_criteria, status=status,
    )

    total = len(experiment.criteria_results)
    failed = [r for r in experiment.criteria_results if not r.passed]
    if not failed:
        conclusion = f"PASSED: all {total} acceptance criteria met."
    else:
        detail = "; ".join(
            f"{r.criterion.description} (actual={r.actual_value}, required>={r.criterion.threshold})"
            + (f" - {r.reason}" if r.reason else "")
            for r in failed
        )
        conclusion = f"REJECTED: {len(failed)} of {total} acceptance criteria not met: {detail}"

    return ResearchReport(
        schema_version=SCHEMA_VERSION, hypothesis=resolved_hypothesis, experiment=experiment, conclusion=conclusion,
    )
