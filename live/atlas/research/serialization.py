"""
Sprint 28. Domain <-> dict conversion for the Research Engine's own types.

Unlike atlas.profiling.serialization (one-way only - a ProfilingReport is
never read back in from JSON), this module is genuinely two-way:
HypothesisRegistry and ExperimentTracker (stores.py) persist records as JSON
Lines and must be able to reconstruct the exact same domain object from a
previously-written line, not just render one for a human to read. Every
`*_to_dict` has a matching `*_from_dict` for that reason.

Stable key order, schema_version fields, and "undefined means null, not
omitted" all follow the same conventions atlas.profiling.serialization
already established one layer down.
"""
from typing import Any

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


def dataset_manifest_to_dict(manifest: DatasetManifest) -> dict[str, Any]:
    return {
        "symbol": manifest.symbol,
        "timeframe": manifest.timeframe,
        "requested_start": manifest.requested_start,
        "requested_end": manifest.requested_end,
        "row_count": manifest.row_count,
        "first_occurred_at": manifest.first_occurred_at,
        "last_occurred_at": manifest.last_occurred_at,
        "source_description": manifest.source_description,
        "generated_at": manifest.generated_at,
    }


def dataset_manifest_from_dict(data: dict[str, Any]) -> DatasetManifest:
    return DatasetManifest(
        symbol=data["symbol"], timeframe=data["timeframe"],
        requested_start=data["requested_start"], requested_end=data["requested_end"],
        row_count=data["row_count"],
        first_occurred_at=data["first_occurred_at"], last_occurred_at=data["last_occurred_at"],
        source_description=data["source_description"], generated_at=data["generated_at"],
    )


def acceptance_criterion_to_dict(criterion: AcceptanceCriterion) -> dict[str, Any]:
    return {
        "description": criterion.description,
        "kind": criterion.kind.value,
        "target_kind": criterion.target_kind.value,
        "target": criterion.target,
        "threshold": criterion.threshold,
    }


def acceptance_criterion_from_dict(data: dict[str, Any]) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        description=data["description"], kind=CriterionKind(data["kind"]),
        target_kind=TargetKind(data["target_kind"]), target=data["target"],
        threshold=data["threshold"],
    )


def hypothesis_to_dict(hypothesis: Hypothesis) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis.hypothesis_id,
        "registered_at": hypothesis.registered_at,
        "author": hypothesis.author,
        "statement": hypothesis.statement,
        "dataset_symbol": hypothesis.dataset_symbol,
        "dataset_timeframe": hypothesis.dataset_timeframe,
        "dataset_start": hypothesis.dataset_start,
        "dataset_end": hypothesis.dataset_end,
        "acceptance_criteria": [acceptance_criterion_to_dict(c) for c in hypothesis.acceptance_criteria],
        "status": hypothesis.status.value,
    }


def hypothesis_from_dict(data: dict[str, Any]) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=data["hypothesis_id"], registered_at=data["registered_at"], author=data["author"],
        statement=data["statement"],
        dataset_symbol=data["dataset_symbol"], dataset_timeframe=data["dataset_timeframe"],
        dataset_start=data["dataset_start"], dataset_end=data["dataset_end"],
        acceptance_criteria=tuple(acceptance_criterion_from_dict(c) for c in data["acceptance_criteria"]),
        status=HypothesisStatus(data["status"]),
    )


def criterion_result_to_dict(result: CriterionResult) -> dict[str, Any]:
    return {
        "criterion": acceptance_criterion_to_dict(result.criterion),
        "actual_value": result.actual_value,
        "passed": result.passed,
        "reason": result.reason,
    }


def criterion_result_from_dict(data: dict[str, Any]) -> CriterionResult:
    return CriterionResult(
        criterion=acceptance_criterion_from_dict(data["criterion"]),
        actual_value=data["actual_value"], passed=data["passed"], reason=data["reason"],
    )


def experiment_to_dict(experiment: Experiment) -> dict[str, Any]:
    return {
        "experiment_id": experiment.experiment_id,
        "hypothesis_id": experiment.hypothesis_id,
        "executed_at": experiment.executed_at,
        "code_version": experiment.code_version,
        "dataset_manifest": dataset_manifest_to_dict(experiment.dataset_manifest),
        "criteria_results": [criterion_result_to_dict(r) for r in experiment.criteria_results],
        "passed": experiment.passed,
        "profiling_report_path": experiment.profiling_report_path,
    }


def experiment_from_dict(data: dict[str, Any]) -> Experiment:
    return Experiment(
        experiment_id=data["experiment_id"], hypothesis_id=data["hypothesis_id"],
        executed_at=data["executed_at"], code_version=data["code_version"],
        dataset_manifest=dataset_manifest_from_dict(data["dataset_manifest"]),
        criteria_results=tuple(criterion_result_from_dict(r) for r in data["criteria_results"]),
        passed=data["passed"], profiling_report_path=data["profiling_report_path"],
    )


def research_report_to_dict(report: ResearchReport) -> dict[str, Any]:
    """One-way only, like atlas.profiling.serialization - a ResearchReport
    is a terminal artifact, never read back in as a domain object."""
    return {
        "schema_version": report.schema_version,
        "hypothesis": hypothesis_to_dict(report.hypothesis),
        "experiment": experiment_to_dict(report.experiment),
        "conclusion": report.conclusion,
    }


def research_report_to_markdown(report: ResearchReport) -> str:
    """Deliberately a plain, mechanical template - not a smart/automated
    generator. Sprint 27's own design review was explicit that the Research
    Report Generator should be a thin rendering step over deterministic
    content, never a tool that decides what the finding means."""
    h = report.hypothesis
    e = report.experiment
    lines = [
        f"# Research Report - {h.hypothesis_id}",
        "",
        f"**Status**: {h.status.value.upper()}",
        f"**Registered**: {h.registered_at} by {h.author}",
        f"**Executed**: {e.executed_at}",
        f"**Code version**: {e.code_version or 'unknown'}",
        "",
        "## Hypothesis",
        "",
        h.statement,
        "",
        "## Dataset",
        "",
        f"- Symbol: {e.dataset_manifest.symbol} / {e.dataset_manifest.timeframe}",
        f"- Requested range: {e.dataset_manifest.requested_start} -> {e.dataset_manifest.requested_end}",
        f"- Rows: {e.dataset_manifest.row_count} "
        f"({e.dataset_manifest.first_occurred_at} -> {e.dataset_manifest.last_occurred_at})",
        f"- Source: {e.dataset_manifest.source_description}",
        "",
        "## Acceptance Criteria",
        "",
    ]
    for result in e.criteria_results:
        mark = "PASS" if result.passed else "FAIL"
        lines.append(f"- [{mark}] {result.criterion.description}")
        lines.append(
            f"  - target={result.criterion.target} ({result.criterion.target_kind.value}), "
            f"kind={result.criterion.kind.value}, threshold={result.criterion.threshold}, "
            f"actual={result.actual_value}"
        )
        if result.reason:
            lines.append(f"  - {result.reason}")
    lines += ["", "## Conclusion", "", report.conclusion]
    return "\n".join(lines) + "\n"
