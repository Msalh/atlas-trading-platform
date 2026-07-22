"""
Sprint 28. Domain <-> dict conversion for the Research Engine's own types.
Extended Phase N4 Sprint 2 (Ledger) to cover every Sprint 1 entity.

Unlike atlas.profiling.serialization (one-way only - a ProfilingReport is
never read back in from JSON), this module is genuinely two-way:
HypothesisRegistry and ExperimentTracker (stores.py) persist records as JSON
Lines and must be able to reconstruct the exact same domain object from a
previously-written line, not just render one for a human to read. Every
`*_to_dict` has a matching `*_from_dict` for that reason.

Stable key order, schema_version fields, and "undefined means null, not
omitted" all follow the same conventions atlas.profiling.serialization
already established one layer down.

Sprint 2 note on hypothesis_to_dict/experiment_to_dict: these two functions
are the one place this sprint touches *existing* code rather than only
adding new functions. Through Sprint 28 they serialized only the original
fields - none of Sprint 1's additive fields on Hypothesis/Experiment were
ever written or read back. Left alone, "persist and retrieve every Sprint 1
entity" (this sprint's own objective) would silently drop every Sprint 1
field on every round-trip. Every new key is written unconditionally on the
`_to_dict` side and read via `.get(key, <the dataclass field's own
default>)` on the `_from_dict` side - so a pre-Sprint-2 JSONL line, which
never had these keys, still loads with exactly the values the dataclass
itself would have defaulted to. Function signatures are unchanged; no
caller (service.py, the two existing stores, test_research.py's own
round-trip tests) is affected.
"""
from typing import Any

from atlas.research.models import (
    AcceptanceCriterion,
    ClaimStrength,
    CriterionKind,
    CriterionResult,
    DatasetManifest,
    Evidence,
    EvaluationMode,
    Experiment,
    ExperimentStatus,
    Feature,
    FeatureStatus,
    FeatureTier,
    Finding,
    FindingStatus,
    Hypothesis,
    HypothesisStatus,
    LeaderboardEntry,
    LeaderboardSnapshot,
    PromotionDecision,
    PromotionRecord,
    ProvenanceKind,
    Realization,
    RealizationKind,
    RealizationStatus,
    ResearchReport,
    TargetKind,
    ValidationResult,
    ValidationVerdict,
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
        "provenance": hypothesis.provenance.value,
        "origin_finding_id": hypothesis.origin_finding_id,
        "derived_from": hypothesis.derived_from,
        "feature_refs": list(hypothesis.feature_refs),
        "context_description": hypothesis.context_description,
        "outcome_metric": hypothesis.outcome_metric,
        "expected_relationship": hypothesis.expected_relationship,
        "superseded_by": hypothesis.superseded_by,
        "fingerprint": hypothesis.fingerprint,
    }


def hypothesis_from_dict(data: dict[str, Any]) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=data["hypothesis_id"], registered_at=data["registered_at"], author=data["author"],
        statement=data["statement"],
        dataset_symbol=data["dataset_symbol"], dataset_timeframe=data["dataset_timeframe"],
        dataset_start=data["dataset_start"], dataset_end=data["dataset_end"],
        acceptance_criteria=tuple(acceptance_criterion_from_dict(c) for c in data["acceptance_criteria"]),
        status=HypothesisStatus(data["status"]),
        provenance=ProvenanceKind(data.get("provenance", ProvenanceKind.HUMAN.value)),
        origin_finding_id=data.get("origin_finding_id"),
        derived_from=data.get("derived_from"),
        feature_refs=tuple(data.get("feature_refs", ())),
        context_description=data.get("context_description"),
        outcome_metric=data.get("outcome_metric"),
        expected_relationship=data.get("expected_relationship"),
        superseded_by=data.get("superseded_by"),
        fingerprint=data.get("fingerprint"),
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
        "realization_id": experiment.realization_id,
        "dataset_manifests": [dataset_manifest_to_dict(m) for m in experiment.dataset_manifests],
        "evaluation_mode": experiment.evaluation_mode.value,
        "seed": experiment.seed,
        "status": experiment.status.value,
        "provenance": experiment.provenance.value,
        "semantic_fingerprint": experiment.semantic_fingerprint,
        "execution_fingerprint": experiment.execution_fingerprint,
    }


def experiment_from_dict(data: dict[str, Any]) -> Experiment:
    return Experiment(
        experiment_id=data["experiment_id"], hypothesis_id=data["hypothesis_id"],
        executed_at=data["executed_at"], code_version=data["code_version"],
        dataset_manifest=dataset_manifest_from_dict(data["dataset_manifest"]),
        criteria_results=tuple(criterion_result_from_dict(r) for r in data["criteria_results"]),
        passed=data["passed"], profiling_report_path=data["profiling_report_path"],
        realization_id=data.get("realization_id"),
        dataset_manifests=tuple(dataset_manifest_from_dict(m) for m in data.get("dataset_manifests", ())),
        evaluation_mode=EvaluationMode(data.get("evaluation_mode", EvaluationMode.SINGLE.value)),
        seed=data.get("seed"),
        status=ExperimentStatus(data.get("status", ExperimentStatus.COMPLETED.value)),
        provenance=ProvenanceKind(data.get("provenance", ProvenanceKind.HUMAN.value)),
        semantic_fingerprint=data.get("semantic_fingerprint"),
        execution_fingerprint=data.get("execution_fingerprint"),
    )


def feature_to_dict(feature: Feature) -> dict[str, Any]:
    return {
        "feature_id": feature.feature_id,
        "name": feature.name,
        "tier": feature.tier.value,
        "version": feature.version,
        "description": feature.description,
        "definition": dict(feature.definition),
        "status": feature.status.value,
        "provenance": feature.provenance.value,
        "created_at": feature.created_at,
        "fingerprint": feature.fingerprint,
        "superseded_by": feature.superseded_by,
    }


def feature_from_dict(data: dict[str, Any]) -> Feature:
    return Feature(
        feature_id=data["feature_id"], name=data["name"], tier=FeatureTier(data["tier"]),
        version=data["version"], description=data["description"], definition=data["definition"],
        status=FeatureStatus(data["status"]), provenance=ProvenanceKind(data["provenance"]),
        created_at=data["created_at"], fingerprint=data["fingerprint"],
        superseded_by=data.get("superseded_by"),
    )


def finding_to_dict(finding: Finding) -> dict[str, Any]:
    return {
        "finding_id": finding.finding_id,
        "discovered_at": finding.discovered_at,
        "discovery_method": finding.discovery_method,
        "discovery_method_version": finding.discovery_method_version,
        "dataset_manifest": dataset_manifest_to_dict(finding.dataset_manifest),
        "feature_refs": list(finding.feature_refs),
        "description": finding.description,
        "metrics": dict(finding.metrics),
        "status": finding.status.value,
        "fingerprint": finding.fingerprint,
        "claim_strength": finding.claim_strength.value,
        "formalized_into": finding.formalized_into,
    }


def finding_from_dict(data: dict[str, Any]) -> Finding:
    return Finding(
        finding_id=data["finding_id"], discovered_at=data["discovered_at"],
        discovery_method=data["discovery_method"], discovery_method_version=data["discovery_method_version"],
        dataset_manifest=dataset_manifest_from_dict(data["dataset_manifest"]),
        feature_refs=tuple(data["feature_refs"]), description=data["description"],
        metrics=data["metrics"], status=FindingStatus(data["status"]), fingerprint=data["fingerprint"],
        claim_strength=ClaimStrength(data.get("claim_strength", ClaimStrength.ASSOCIATIVE.value)),
        formalized_into=data.get("formalized_into"),
    )


def realization_to_dict(realization: Realization) -> dict[str, Any]:
    return {
        "realization_id": realization.realization_id,
        "hypothesis_id": realization.hypothesis_id,
        "kind": realization.kind.value,
        "version": realization.version,
        "parameters": dict(realization.parameters),
        "status": realization.status.value,
        "provenance": realization.provenance.value,
        "created_at": realization.created_at,
        "fingerprint": realization.fingerprint,
    }


def realization_from_dict(data: dict[str, Any]) -> Realization:
    return Realization(
        realization_id=data["realization_id"], hypothesis_id=data["hypothesis_id"],
        kind=RealizationKind(data["kind"]), version=data["version"], parameters=data["parameters"],
        status=RealizationStatus(data["status"]), provenance=ProvenanceKind(data["provenance"]),
        created_at=data["created_at"], fingerprint=data["fingerprint"],
    )


def evidence_to_dict(evidence: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "experiment_id": evidence.experiment_id,
        "computed_at": evidence.computed_at,
        "metrics": dict(evidence.metrics),
        "fingerprint": evidence.fingerprint,
        "decision_sequence_path": evidence.decision_sequence_path,
    }


def evidence_from_dict(data: dict[str, Any]) -> Evidence:
    return Evidence(
        evidence_id=data["evidence_id"], experiment_id=data["experiment_id"],
        computed_at=data["computed_at"], metrics=data["metrics"], fingerprint=data["fingerprint"],
        decision_sequence_path=data.get("decision_sequence_path"),
    )


def validation_result_to_dict(result: ValidationResult) -> dict[str, Any]:
    return {
        "validation_id": result.validation_id,
        "hypothesis_id": result.hypothesis_id,
        "evidence_ids": list(result.evidence_ids),
        "verdict": result.verdict.value,
        "criteria_results": [criterion_result_to_dict(r) for r in result.criteria_results],
        "justification": result.justification,
        "validated_at": result.validated_at,
        "out_of_sample": result.out_of_sample,
        "multiple_testing_correction": result.multiple_testing_correction,
        "fingerprint": result.fingerprint,
    }


def validation_result_from_dict(data: dict[str, Any]) -> ValidationResult:
    return ValidationResult(
        validation_id=data["validation_id"], hypothesis_id=data["hypothesis_id"],
        evidence_ids=tuple(data["evidence_ids"]), verdict=ValidationVerdict(data["verdict"]),
        criteria_results=tuple(criterion_result_from_dict(r) for r in data["criteria_results"]),
        justification=data["justification"], validated_at=data["validated_at"],
        out_of_sample=data["out_of_sample"],
        multiple_testing_correction=data["multiple_testing_correction"],
        fingerprint=data["fingerprint"],
    )


def leaderboard_entry_to_dict(entry: LeaderboardEntry) -> dict[str, Any]:
    return {
        "hypothesis_id": entry.hypothesis_id,
        "realization_id": entry.realization_id,
        "rank": entry.rank,
        "score": entry.score,
        "score_description": entry.score_description,
    }


def leaderboard_entry_from_dict(data: dict[str, Any]) -> LeaderboardEntry:
    return LeaderboardEntry(
        hypothesis_id=data["hypothesis_id"], realization_id=data["realization_id"],
        rank=data["rank"], score=data["score"], score_description=data["score_description"],
    )


def leaderboard_snapshot_to_dict(snapshot: LeaderboardSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "created_at": snapshot.created_at,
        "entries": [leaderboard_entry_to_dict(e) for e in snapshot.entries],
        "fingerprint": snapshot.fingerprint,
        "benchmark_description": snapshot.benchmark_description,
    }


def leaderboard_snapshot_from_dict(data: dict[str, Any]) -> LeaderboardSnapshot:
    return LeaderboardSnapshot(
        snapshot_id=data["snapshot_id"], created_at=data["created_at"],
        entries=tuple(leaderboard_entry_from_dict(e) for e in data["entries"]),
        fingerprint=data["fingerprint"], benchmark_description=data.get("benchmark_description"),
    )


def promotion_record_to_dict(record: PromotionRecord) -> dict[str, Any]:
    return {
        "promotion_id": record.promotion_id,
        "hypothesis_id": record.hypothesis_id,
        "realization_id": record.realization_id,
        "decision": record.decision.value,
        "reviewer": record.reviewer,
        "rationale": record.rationale,
        "evidence_snapshot_ref": record.evidence_snapshot_ref,
        "decided_at": record.decided_at,
        "fingerprint": record.fingerprint,
        "resulting_production_change_ref": record.resulting_production_change_ref,
    }


def promotion_record_from_dict(data: dict[str, Any]) -> PromotionRecord:
    return PromotionRecord(
        promotion_id=data["promotion_id"], hypothesis_id=data["hypothesis_id"],
        realization_id=data["realization_id"], decision=PromotionDecision(data["decision"]),
        reviewer=data["reviewer"], rationale=data["rationale"],
        evidence_snapshot_ref=data["evidence_snapshot_ref"], decided_at=data["decided_at"],
        fingerprint=data["fingerprint"],
        resulting_production_change_ref=data.get("resulting_production_change_ref"),
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
