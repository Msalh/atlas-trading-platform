"""
Phase N4 Sprint 2 (Ledger). Tests for the seven new stores.py registries/
trackers, ports.py's Protocol boundaries, and find_similar_hypotheses().

test_research.py (Sprint 28's own suite) already covers HypothesisRegistry/
ExperimentTracker's register/record/get/all/conflict/idempotency behavior
and is left untouched - it is re-run as the regression proof that neither
class was modified this sprint. This file covers the same behavior for the
seven new stores, plus what is genuinely new this sprint: Protocol
conformance and the duplicate-hypothesis check.
"""
import ast
from pathlib import Path

import pytest
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    DatasetManifest,
    Evidence,
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
    TargetKind,
    ValidationResult,
    ValidationVerdict,
)
from atlas.research.ports import (
    EvidenceStore,
    ExperimentStore,
    FeatureStore,
    FindingStore,
    HypothesisStore,
    LeaderboardSnapshotStore,
    PromotionRecordStore,
    RealizationStore,
    ValidationResultStore,
)
from atlas.research.stores import (
    EvidenceTracker,
    ExperimentTracker,
    FeatureRegistry,
    FindingTracker,
    HypothesisRegistry,
    LeaderboardSnapshotTracker,
    PromotionRecordTracker,
    RealizationRegistry,
    RecordConflictError,
    ValidationResultTracker,
    find_similar_hypotheses,
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
        criteria_results=(), justification="clears threshold with p<0.01",
        validated_at=_OCCURRED_AT, out_of_sample=True, multiple_testing_correction=None,
        fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    # ValidationResult requires at least one criteria_results entry; supply one by default.
    if not fields["criteria_results"]:
        from atlas.research.models import CriterionResult
        fields["criteria_results"] = (
            CriterionResult(criterion=_acceptance_criterion(), actual_value=0.5, passed=True, reason=None),
        )
    return ValidationResult(**fields)


def _leaderboard_snapshot(**overrides) -> LeaderboardSnapshot:
    fields = dict(
        snapshot_id="s1", created_at=_OCCURRED_AT,
        entries=(LeaderboardEntry(hypothesis_id="h1", realization_id="r1", rank=1, score=0.9, score_description="x"),),
        fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return LeaderboardSnapshot(**fields)


def _promotion_record(**overrides) -> PromotionRecord:
    fields = dict(
        promotion_id="p1", hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear, reproducible, out-of-sample evidence", evidence_snapshot_ref="v1",
        decided_at=_OCCURRED_AT, fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return PromotionRecord(**fields)


# ---- register/get/all, idempotency, conflict - one parametrized suite per new store ----

def test_feature_registry_register_get_all(tmp_path: Path):
    store = FeatureRegistry(tmp_path / "features.jsonl")
    f = _feature()
    store.register(f)
    assert store.get("f1") == f
    assert store.get("missing") is None
    assert store.all() == [f]


def test_feature_registry_idempotent_resubmission_is_a_noop(tmp_path: Path):
    store = FeatureRegistry(tmp_path / "features.jsonl")
    store.register(_feature())
    store.register(_feature())  # identical content - safe no-op
    assert len(store.all()) == 1


def test_feature_registry_conflicting_resubmission_raises(tmp_path: Path):
    store = FeatureRegistry(tmp_path / "features.jsonl")
    store.register(_feature())
    with pytest.raises(RecordConflictError):
        store.register(_feature(name="changed_name"))


def test_finding_tracker_record_get_all(tmp_path: Path):
    store = FindingTracker(tmp_path / "findings.jsonl")
    f = _finding()
    store.record(f)
    assert store.get("fnd1") == f
    assert store.all() == [f]


def test_finding_tracker_conflicting_resubmission_raises(tmp_path: Path):
    store = FindingTracker(tmp_path / "findings.jsonl")
    store.record(_finding())
    with pytest.raises(RecordConflictError):
        store.record(_finding(description="changed"))


def test_realization_registry_register_get_all(tmp_path: Path):
    store = RealizationRegistry(tmp_path / "realizations.jsonl")
    r = _realization()
    store.register(r)
    assert store.get("r1") == r
    assert store.all() == [r]


def test_realization_registry_conflicting_resubmission_raises(tmp_path: Path):
    store = RealizationRegistry(tmp_path / "realizations.jsonl")
    store.register(_realization())
    with pytest.raises(RecordConflictError):
        store.register(_realization(version="2.0"))


def test_evidence_tracker_record_get_all(tmp_path: Path):
    store = EvidenceTracker(tmp_path / "evidence.jsonl")
    e = _evidence()
    store.record(e)
    assert store.get("ev1") == e
    assert store.all() == [e]


def test_evidence_tracker_conflicting_resubmission_raises(tmp_path: Path):
    store = EvidenceTracker(tmp_path / "evidence.jsonl")
    store.record(_evidence())
    with pytest.raises(RecordConflictError):
        store.record(_evidence(metrics={"effect_size": 0.9}))


def test_validation_result_tracker_record_get_all(tmp_path: Path):
    store = ValidationResultTracker(tmp_path / "validation.jsonl")
    v = _validation_result()
    store.record(v)
    assert store.get("v1") == v
    assert store.all() == [v]


def test_validation_result_tracker_conflicting_resubmission_raises(tmp_path: Path):
    store = ValidationResultTracker(tmp_path / "validation.jsonl")
    store.record(_validation_result())
    with pytest.raises(RecordConflictError):
        store.record(_validation_result(verdict=ValidationVerdict.NOT_SUPPORTED))


def test_leaderboard_snapshot_tracker_record_get_all(tmp_path: Path):
    store = LeaderboardSnapshotTracker(tmp_path / "leaderboard.jsonl")
    s = _leaderboard_snapshot()
    store.record(s)
    assert store.get("s1") == s
    assert store.all() == [s]


def test_leaderboard_snapshot_tracker_conflicting_resubmission_raises(tmp_path: Path):
    store = LeaderboardSnapshotTracker(tmp_path / "leaderboard.jsonl")
    store.record(_leaderboard_snapshot())
    with pytest.raises(RecordConflictError):
        store.record(_leaderboard_snapshot(benchmark_description="changed"))


def test_promotion_record_tracker_record_get_all(tmp_path: Path):
    store = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    p = _promotion_record()
    store.record(p)
    assert store.get("p1") == p
    assert store.all() == [p]


def test_promotion_record_tracker_conflicting_resubmission_raises(tmp_path: Path):
    store = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    store.record(_promotion_record())
    with pytest.raises(RecordConflictError):
        store.record(_promotion_record(rationale="a different rationale entirely"))


# ---- REJECTED/DECLINED records must never be silently filtered ----

def test_rejected_hypothesis_survives_get_and_all(tmp_path: Path):
    store = HypothesisRegistry(tmp_path / "hypotheses.jsonl")
    h = _hypothesis(status=HypothesisStatus.REJECTED)
    store.register(h)
    assert store.get("h1") == h
    assert store.all() == [h]


def test_declined_promotion_record_survives_get_and_all(tmp_path: Path):
    store = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    p = _promotion_record(decision=PromotionDecision.DECLINED, rationale="insufficient out-of-sample evidence")
    store.record(p)
    assert store.get("p1") == p
    assert store.all() == [p]


def test_declined_promotion_record_survives_alongside_an_approved_one(tmp_path: Path):
    """A store must never default to hiding a declined/rejected record even
    when other, more 'successful' records exist alongside it."""
    store = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    approved = _promotion_record(promotion_id="p1", decision=PromotionDecision.APPROVED)
    declined = _promotion_record(promotion_id="p2", hypothesis_id="h2", decision=PromotionDecision.DECLINED)
    store.record(approved)
    store.record(declined)
    all_records = store.all()
    assert approved in all_records
    assert declined in all_records
    assert len(all_records) == 2


# ---- find_similar_hypotheses(): structural, not textual ----

def test_find_similar_hypotheses_matches_on_structural_anchors_not_statement():
    existing = _hypothesis(
        hypothesis_id="h1", statement="completely different wording",
        feature_refs=("f1", "f2"), context_description="compressed regime", outcome_metric="15-bar forward return",
    )
    candidate = _hypothesis(
        hypothesis_id="h2", statement="a totally unrelated sentence",
        feature_refs=("f2", "f1"),  # same set, different order
        context_description="compressed regime", outcome_metric="15-bar forward return",
    )
    matches = find_similar_hypotheses(candidate, [existing])
    assert matches == (existing,)


def test_find_similar_hypotheses_does_not_match_on_different_feature_refs():
    existing = _hypothesis(
        hypothesis_id="h1", feature_refs=("f1", "f2"),
        context_description="compressed regime", outcome_metric="15-bar forward return",
    )
    candidate = _hypothesis(
        hypothesis_id="h2", feature_refs=("f3",),
        context_description="compressed regime", outcome_metric="15-bar forward return",
    )
    assert find_similar_hypotheses(candidate, [existing]) == ()


def test_find_similar_hypotheses_never_matches_when_candidate_has_no_anchors():
    existing = _hypothesis(
        hypothesis_id="h1", feature_refs=("f1",), context_description="ctx", outcome_metric="metric",
    )
    candidate = _hypothesis(hypothesis_id="h2")  # no feature_refs/context/outcome set
    assert find_similar_hypotheses(candidate, [existing]) == ()


def test_find_similar_hypotheses_never_matches_when_existing_has_no_anchors():
    existing = _hypothesis(hypothesis_id="h1")  # no anchors
    candidate = _hypothesis(hypothesis_id="h2", feature_refs=("f1",), context_description="ctx", outcome_metric="m")
    assert find_similar_hypotheses(candidate, [existing]) == ()


def test_find_similar_hypotheses_excludes_the_candidates_own_id():
    candidate = _hypothesis(
        hypothesis_id="h1", feature_refs=("f1",), context_description="ctx", outcome_metric="m",
    )
    assert find_similar_hypotheses(candidate, [candidate]) == ()


# ---- Protocol conformance: mechanical proof, not a docstring claim ----

def test_every_concrete_store_satisfies_its_protocol(tmp_path: Path):
    assert isinstance(HypothesisRegistry(tmp_path / "a.jsonl"), HypothesisStore)
    assert isinstance(ExperimentTracker(tmp_path / "b.jsonl"), ExperimentStore)
    assert isinstance(FeatureRegistry(tmp_path / "c.jsonl"), FeatureStore)
    assert isinstance(FindingTracker(tmp_path / "d.jsonl"), FindingStore)
    assert isinstance(RealizationRegistry(tmp_path / "e.jsonl"), RealizationStore)
    assert isinstance(EvidenceTracker(tmp_path / "f.jsonl"), EvidenceStore)
    assert isinstance(ValidationResultTracker(tmp_path / "g.jsonl"), ValidationResultStore)
    assert isinstance(LeaderboardSnapshotTracker(tmp_path / "h.jsonl"), LeaderboardSnapshotStore)
    assert isinstance(PromotionRecordTracker(tmp_path / "i.jsonl"), PromotionRecordStore)


# ---- dependency audit: Sprint 2 introduces no new cross-package import ----

_STORES_FILE = Path(__file__).resolve().parent.parent / "atlas" / "research" / "stores.py"
_SERIALIZATION_FILE = Path(__file__).resolve().parent.parent / "atlas" / "research" / "serialization.py"
_PORTS_FILE = Path(__file__).resolve().parent.parent / "atlas" / "research" / "ports.py"


def _imported_module_roots(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def _atlas_imports_outside_research(file_path: Path) -> set[str]:
    imported = _imported_module_roots(file_path)
    return {name for name in imported if name.startswith("atlas.") and not name.startswith("atlas.research")}


def test_stores_module_introduces_no_new_cross_package_import():
    assert _atlas_imports_outside_research(_STORES_FILE) == set()


def test_serialization_module_introduces_no_new_cross_package_import():
    assert _atlas_imports_outside_research(_SERIALIZATION_FILE) == set()


def test_ports_module_introduces_no_new_cross_package_import():
    assert _atlas_imports_outside_research(_PORTS_FILE) == set()
