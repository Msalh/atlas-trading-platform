"""
Phase N4 Sprint 1 (Research Engine Core Entities). Tests for the new and
generalized types in atlas.research.models - Feature, Finding, Realization,
Evidence, ValidationResult, LeaderboardEntry/LeaderboardSnapshot,
PromotionRecord, and the additive extensions to the pre-existing Sprint 28
Hypothesis/Experiment. No behavior is exercised here beyond construction,
invariant enforcement, and immutability - this sprint is data only.

test_research.py (Sprint 28's own suite, covering models/service/
serialization/stores) is deliberately left untouched and is re-run as its
own regression proof that every existing call site
(atlas.research.service.run_experiment/build_research_report,
atlas.research.serialization, atlas.research.stores) still constructs
Hypothesis/Experiment exactly as before.
"""
import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType

import pytest
from atlas.research.fingerprint import compute_fingerprint
from atlas.research.models import (
    AcceptanceCriterion,
    ClaimStrength,
    CriterionKind,
    CriterionResult,
    DatasetManifest,
    Evidence,
    Experiment,
    EvaluationMode,
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
    RealizationTemplateKind,
    TargetKind,
    ValidationResult,
    ValidationVerdict,
)

_OCCURRED_AT = "2026-07-21T12:00:00+00:00"


def _dataset_manifest() -> DatasetManifest:
    return DatasetManifest(
        symbol="MNQU6", timeframe="5m", requested_start=_OCCURRED_AT, requested_end=_OCCURRED_AT,
        row_count=1, first_occurred_at=_OCCURRED_AT, last_occurred_at=_OCCURRED_AT,
        source_description="test", generated_at=_OCCURRED_AT,
    )


def _acceptance_criterion() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        description="stub", kind=CriterionKind.MIN_FIRING_RATE, target_kind=TargetKind.FACT,
        target="trend_5m", threshold=0.1,
    )


def _hypothesis(**overrides) -> Hypothesis:
    fields = dict(
        hypothesis_id="h1", registered_at=_OCCURRED_AT, author="tester", statement="stub claim",
        dataset_symbol="MNQU6", dataset_timeframe="5m", dataset_start=_OCCURRED_AT, dataset_end=_OCCURRED_AT,
        acceptance_criteria=(_acceptance_criterion(),),
    )
    fields.update(overrides)
    return Hypothesis(**fields)


def _criterion_result() -> CriterionResult:
    return CriterionResult(criterion=_acceptance_criterion(), actual_value=0.5, passed=True, reason=None)


# ---- Sprint 8.1: TargetKind.DECISION_SEQUENCE ----

def test_target_kind_is_closed_at_exactly_four_members():
    assert {k.value for k in TargetKind} == {"fact", "setup", "feature", "decision_sequence"}


def test_acceptance_criterion_representable_with_decision_sequence_target_kind():
    criterion = AcceptanceCriterion(
        description="enter_long_rate clears 0.05", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.DECISION_SEQUENCE, target="enter_long_rate", threshold=0.05,
    )
    assert criterion.target_kind == TargetKind.DECISION_SEQUENCE


def _experiment(**overrides) -> Experiment:
    fields = dict(
        experiment_id="e1", hypothesis_id="h1", executed_at=_OCCURRED_AT, code_version="abc123",
        dataset_manifest=_dataset_manifest(), criteria_results=(_criterion_result(),), passed=True,
        profiling_report_path=None,
    )
    fields.update(overrides)
    return Experiment(**fields)


def _feature(**overrides) -> Feature:
    fields = dict(
        feature_id="f1", name="stub_feature", tier=FeatureTier.CANDIDATE, version="1.0",
        description="stub", definition={"window": 5}, status=FeatureStatus.PROPOSED,
        provenance=ProvenanceKind.HUMAN, created_at=_OCCURRED_AT, fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return Feature(**fields)


def _finding(**overrides) -> Finding:
    fields = dict(
        finding_id="fnd1", discovered_at=_OCCURRED_AT, discovery_method="correlation", discovery_method_version="1.0",
        dataset_manifest=_dataset_manifest(), feature_refs=("f1", "f2"), description="stub",
        metrics={"correlation": 0.3}, status=FindingStatus.DISCOVERED, fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return Finding(**fields)


def _realization(**overrides) -> Realization:
    fields = dict(
        realization_id="r1", hypothesis_id="h1", kind=RealizationKind.STATISTICAL_TEST, version="1.0",
        parameters={}, status=RealizationStatus.DRAFTED, provenance=ProvenanceKind.HUMAN,
        created_at=_OCCURRED_AT, fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return Realization(**fields)


def _evidence(**overrides) -> Evidence:
    fields = dict(
        evidence_id="ev1", experiment_id="e1", computed_at=_OCCURRED_AT, metrics={"effect_size": 0.2},
        fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return Evidence(**fields)


def _validation_result(**overrides) -> ValidationResult:
    fields = dict(
        validation_id="v1", hypothesis_id="h1", evidence_ids=("ev1",), verdict=ValidationVerdict.SUPPORTED,
        criteria_results=(_criterion_result(),), justification="clears threshold with p<0.01",
        validated_at=_OCCURRED_AT, out_of_sample=True, multiple_testing_correction=None,
        fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return ValidationResult(**fields)


def _leaderboard_entry(**overrides) -> LeaderboardEntry:
    fields = dict(hypothesis_id="h1", realization_id=None, rank=1, score=0.9, score_description="effect size")
    fields.update(overrides)
    return LeaderboardEntry(**fields)


def _promotion_record(**overrides) -> PromotionRecord:
    fields = dict(
        promotion_id="p1", hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear, reproducible, out-of-sample evidence", evidence_snapshot_ref="v1",
        decided_at=_OCCURRED_AT, fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return PromotionRecord(**fields)


# ---- Hypothesis: backward compatibility with Sprint 28 construction ----

def test_hypothesis_constructs_with_only_the_original_sprint_28_fields():
    """The exact call shape test_research.py's own suite already uses -
    proves every new field truly defaults, nothing new is required."""
    h = Hypothesis(
        hypothesis_id="h1", registered_at=_OCCURRED_AT, author="tester", statement="stub",
        dataset_symbol="MNQU6", dataset_timeframe="5m", dataset_start=_OCCURRED_AT, dataset_end=_OCCURRED_AT,
        acceptance_criteria=(_acceptance_criterion(),),
    )
    assert h.status == HypothesisStatus.REGISTERED
    assert h.provenance == ProvenanceKind.HUMAN
    assert h.origin_finding_id is None
    assert h.derived_from is None
    assert h.feature_refs == ()
    assert h.context_description is None
    assert h.outcome_metric is None
    assert h.expected_relationship is None
    assert h.superseded_by is None
    assert h.fingerprint is None


def test_hypothesis_still_rejects_empty_acceptance_criteria():
    with pytest.raises(ValueError, match="at least one acceptance criterion"):
        _hypothesis(acceptance_criteria=())


def test_hypothesis_status_original_four_values_unchanged():
    assert HypothesisStatus.REGISTERED.value == "registered"
    assert HypothesisStatus.VALIDATED.value == "validated"
    assert HypothesisStatus.REJECTED.value == "rejected"
    assert HypothesisStatus.INCONCLUSIVE.value == "inconclusive"


def test_hypothesis_status_extended_with_eight_new_values():
    new_values = {
        HypothesisStatus.PROPOSED, HypothesisStatus.UNDER_EXPERIMENT, HypothesisStatus.REALIZED,
        HypothesisStatus.PROMOTION_CANDIDATE, HypothesisStatus.PROMOTED, HypothesisStatus.DECLINED,
        HypothesisStatus.SUPERSEDED, HypothesisStatus.WITHDRAWN,
    }
    assert len(new_values) == 8
    assert len(list(HypothesisStatus)) == 12


def test_hypothesis_new_fields_can_be_populated():
    h = _hypothesis(
        provenance=ProvenanceKind.DISCOVERY_ENGINE, origin_finding_id="fnd1", feature_refs=("f1", "f2"),
        context_description="compressed regime", outcome_metric="15-bar forward return",
        expected_relationship="positive", fingerprint=compute_fingerprint({"stub": True}),
    )
    assert h.provenance == ProvenanceKind.DISCOVERY_ENGINE
    assert h.origin_finding_id == "fnd1"
    assert h.feature_refs == ("f1", "f2")
    assert h.fingerprint is not None


def test_hypothesis_is_frozen():
    h = _hypothesis()
    with pytest.raises(FrozenInstanceError):
        h.status = HypothesisStatus.VALIDATED


# ---- Experiment: backward compatibility with Sprint 28 construction ----

def test_experiment_constructs_with_only_the_original_sprint_28_fields():
    e = Experiment(
        experiment_id="e1", hypothesis_id="h1", executed_at=_OCCURRED_AT, code_version="abc123",
        dataset_manifest=_dataset_manifest(), criteria_results=(_criterion_result(),), passed=True,
        profiling_report_path=None,
    )
    assert e.realization_id is None
    assert e.dataset_manifests == ()
    assert e.evaluation_mode == EvaluationMode.SINGLE
    assert e.seed is None
    assert e.status == ExperimentStatus.COMPLETED
    assert e.provenance == ProvenanceKind.HUMAN
    assert e.semantic_fingerprint is None
    assert e.execution_fingerprint is None


def test_experiment_new_fields_can_be_populated():
    semantic = compute_fingerprint({"stub": "semantic"})
    e = _experiment(
        realization_id="r1", dataset_manifests=(_dataset_manifest(), _dataset_manifest()),
        evaluation_mode=EvaluationMode.WALK_FORWARD, seed=42, status=ExperimentStatus.RUNNING,
        semantic_fingerprint=semantic,
        execution_fingerprint=compute_fingerprint({"semantic_fingerprint": semantic, "code_version": "abc123"}),
    )
    assert e.realization_id == "r1"
    assert len(e.dataset_manifests) == 2
    assert e.evaluation_mode == EvaluationMode.WALK_FORWARD
    assert e.seed == 42
    assert e.semantic_fingerprint == semantic
    assert e.execution_fingerprint is not None
    assert e.execution_fingerprint != e.semantic_fingerprint


def test_experiment_is_frozen():
    e = _experiment()
    with pytest.raises(FrozenInstanceError):
        e.passed = False


def test_same_semantic_fingerprint_with_different_code_version_yields_different_execution_fingerprint():
    """Two Experiments re-running the identical research question
    (same hypothesis/realization/dataset/mode) against different code
    should share semantic_fingerprint but diverge on execution_fingerprint
    - the ledger's representation of "same question, different execution,
    potentially different Evidence"."""
    semantic = compute_fingerprint({"hypothesis_id": "h1", "realization_id": None, "evaluation_mode": "single"})
    first = _experiment(semantic_fingerprint=semantic, execution_fingerprint=compute_fingerprint(
        {"semantic_fingerprint": semantic, "code_version": "abc123"}
    ))
    second = _experiment(semantic_fingerprint=semantic, execution_fingerprint=compute_fingerprint(
        {"semantic_fingerprint": semantic, "code_version": "def456"}
    ))
    assert first.semantic_fingerprint == second.semantic_fingerprint
    assert first.execution_fingerprint != second.execution_fingerprint


# ---- Feature ----

def test_feature_constructs_and_normalizes_definition():
    f = _feature(definition={"b": 2, "a": 1})
    assert isinstance(f.definition, MappingProxyType)
    assert dict(f.definition) == {"b": 2, "a": 1}


def test_feature_rejects_blank_name():
    with pytest.raises(ValueError, match="must not be blank"):
        _feature(name="  ")


def test_feature_definition_is_immutable():
    f = _feature()
    with pytest.raises(TypeError):
        f.definition["new_key"] = 1


def test_feature_is_frozen():
    f = _feature()
    with pytest.raises(FrozenInstanceError):
        f.status = FeatureStatus.PROMOTED


# ---- Finding ----

def test_finding_constructs_and_normalizes_metrics():
    finding = _finding(metrics={"b": 2, "a": 1})
    assert isinstance(finding.metrics, MappingProxyType)
    assert dict(finding.metrics) == {"b": 2, "a": 1}


def test_finding_claim_strength_defaults_to_associative():
    assert _finding().claim_strength == ClaimStrength.ASSOCIATIVE


def test_finding_formalized_status_requires_formalized_into():
    with pytest.raises(ValueError, match="requires formalized_into"):
        _finding(status=FindingStatus.FORMALIZED, formalized_into=None)


def test_finding_non_formalized_status_rejects_formalized_into():
    with pytest.raises(ValueError, match="not FORMALIZED"):
        _finding(status=FindingStatus.DISCOVERED, formalized_into="h1")


def test_finding_formalized_with_formalized_into_is_valid():
    finding = _finding(status=FindingStatus.FORMALIZED, formalized_into="h1")
    assert finding.formalized_into == "h1"


def test_finding_is_frozen():
    finding = _finding()
    with pytest.raises(FrozenInstanceError):
        finding.status = FindingStatus.DISMISSED


# ---- Realization ----

def test_realization_constructs_and_normalizes_parameters():
    r = _realization(parameters={"lookback": 20})
    assert isinstance(r.parameters, MappingProxyType)
    assert dict(r.parameters) == {"lookback": 20}


def test_realization_all_five_kinds_are_representable():
    kinds = {
        RealizationKind.STATISTICAL_TEST, RealizationKind.TEMPLATED_STRATEGY, RealizationKind.STRATEGY_VARIANT,
        RealizationKind.CONTEXT_FILTER, RealizationKind.RISK_INPUT,
    }
    assert len(kinds) == 5
    requires_template = {RealizationKind.TEMPLATED_STRATEGY, RealizationKind.STRATEGY_VARIANT}
    for kind in kinds:
        template_kind = RealizationTemplateKind.THRESHOLD_CROSS if kind in requires_template else None
        r = _realization(kind=kind, template_kind=template_kind)
        assert r.kind == kind


def test_realization_is_frozen():
    r = _realization()
    with pytest.raises(FrozenInstanceError):
        r.status = RealizationStatus.RETAINED


def test_realization_template_kind_defaults_to_none():
    r = _realization()
    assert r.template_kind is None


def test_realization_templated_strategy_requires_template_kind():
    with pytest.raises(ValueError, match="requires template_kind"):
        _realization(kind=RealizationKind.TEMPLATED_STRATEGY, template_kind=None)


def test_realization_strategy_variant_requires_template_kind():
    with pytest.raises(ValueError, match="requires template_kind"):
        _realization(kind=RealizationKind.STRATEGY_VARIANT, template_kind=None)


def test_realization_templated_strategy_accepts_template_kind():
    r = _realization(kind=RealizationKind.TEMPLATED_STRATEGY, template_kind=RealizationTemplateKind.THRESHOLD_CROSS)
    assert r.template_kind == RealizationTemplateKind.THRESHOLD_CROSS


@pytest.mark.parametrize("kind", [
    RealizationKind.STATISTICAL_TEST, RealizationKind.CONTEXT_FILTER, RealizationKind.RISK_INPUT,
])
def test_realization_non_executable_kinds_forbid_template_kind(kind):
    with pytest.raises(ValueError, match="must not set template_kind"):
        _realization(kind=kind, template_kind=RealizationTemplateKind.THRESHOLD_CROSS)


# ---- Evidence ----

def test_evidence_constructs_and_normalizes_metrics():
    ev = _evidence(metrics={"b": 2, "a": 1})
    assert isinstance(ev.metrics, MappingProxyType)
    assert dict(ev.metrics) == {"b": 2, "a": 1}


def test_evidence_decision_sequence_path_defaults_to_none():
    assert _evidence().decision_sequence_path is None


def test_evidence_is_frozen():
    ev = _evidence()
    with pytest.raises(FrozenInstanceError):
        ev.evidence_id = "changed"


# ---- ValidationResult ----

def test_validation_result_requires_at_least_one_evidence_id():
    with pytest.raises(ValueError, match="at least one Evidence"):
        _validation_result(evidence_ids=())


def test_validation_result_requires_at_least_one_criterion_result():
    with pytest.raises(ValueError, match="at least one criterion result"):
        _validation_result(criteria_results=())


def test_validation_result_rejects_blank_justification():
    with pytest.raises(ValueError, match="justification must not be blank"):
        _validation_result(justification="   ")


def test_validation_result_all_three_verdicts_are_representable():
    for verdict in (ValidationVerdict.SUPPORTED, ValidationVerdict.NOT_SUPPORTED, ValidationVerdict.INCONCLUSIVE):
        assert _validation_result(verdict=verdict).verdict == verdict


def test_validation_result_is_frozen():
    v = _validation_result()
    with pytest.raises(FrozenInstanceError):
        v.verdict = ValidationVerdict.NOT_SUPPORTED


# ---- LeaderboardSnapshot ----

def test_leaderboard_snapshot_constructs_with_unique_ranks():
    snapshot = LeaderboardSnapshot(
        snapshot_id="s1", created_at=_OCCURRED_AT,
        entries=(_leaderboard_entry(rank=1), _leaderboard_entry(rank=2, hypothesis_id="h2")),
        fingerprint="0123456789abcdef",
    )
    assert len(snapshot.entries) == 2


def test_leaderboard_snapshot_rejects_duplicate_ranks():
    with pytest.raises(ValueError, match="unique ranks"):
        LeaderboardSnapshot(
            snapshot_id="s1", created_at=_OCCURRED_AT,
            entries=(_leaderboard_entry(rank=1), _leaderboard_entry(rank=1, hypothesis_id="h2")),
            fingerprint="0123456789abcdef",
        )


def test_leaderboard_entry_realization_id_may_be_none_for_descriptive_hypotheses():
    entry = _leaderboard_entry(realization_id=None)
    assert entry.realization_id is None


def test_leaderboard_snapshot_is_frozen():
    snapshot = LeaderboardSnapshot(
        snapshot_id="s1", created_at=_OCCURRED_AT, entries=(_leaderboard_entry(),), fingerprint="0123456789abcdef",
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.snapshot_id = "changed"


# ---- PromotionRecord ----

def test_promotion_record_rejects_blank_rationale():
    with pytest.raises(ValueError, match="non-blank rationale"):
        _promotion_record(rationale="  ")


def test_promotion_record_rejects_blank_reviewer():
    with pytest.raises(ValueError, match="non-blank reviewer"):
        _promotion_record(reviewer="")


def test_promotion_record_all_three_decisions_are_representable():
    for decision in (PromotionDecision.APPROVED, PromotionDecision.DECLINED, PromotionDecision.DEFERRED):
        assert _promotion_record(decision=decision).decision == decision


def test_promotion_record_resulting_production_change_ref_defaults_to_none():
    assert _promotion_record().resulting_production_change_ref is None


def test_promotion_record_is_frozen():
    p = _promotion_record()
    with pytest.raises(FrozenInstanceError):
        p.decision = PromotionDecision.DECLINED


# ---- fingerprint determinism across the new types ----

def test_fingerprint_is_stable_for_identical_new_entity_values():
    a = _finding()
    b = _finding()
    assert a is not b
    assert compute_fingerprint(a.metrics) == compute_fingerprint(b.metrics)


# ---- dependency audit: no cross-package import introduced this sprint ----

_MODELS_FILE = Path(__file__).resolve().parent.parent / "atlas" / "research" / "models.py"
_FINGERPRINT_FILE = Path(__file__).resolve().parent.parent / "atlas" / "research" / "fingerprint.py"


def _imported_module_roots(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def test_models_module_introduces_no_new_cross_package_import():
    """Sprint 1's own scope claim: zero dependency changes. models.py must
    still import nothing beyond the standard library."""
    imported = _imported_module_roots(_MODELS_FILE)
    atlas_imports = {name for name in imported if name.startswith("atlas.")}
    assert atlas_imports == set()


def test_fingerprint_module_imports_only_the_standard_library():
    imported = _imported_module_roots(_FINGERPRINT_FILE)
    atlas_imports = {name for name in imported if name.startswith("atlas.")}
    assert atlas_imports == set()
