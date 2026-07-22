"""
Phase N4 Sprint 2 (Ledger). Round-trip and backward-compatibility tests for
atlas.research.serialization's Sprint 1 additions.

test_research.py (Sprint 28's own suite) already covers
hypothesis_to_dict/experiment_to_dict round-tripping the ORIGINAL fields and
is left untouched. This file covers two things that suite cannot: that the
Sprint 1 fields Sprint 2 just wired up round-trip too, and that a pre-Sprint-2
JSONL line (missing every Sprint 1 key) still loads with the exact defaults
the dataclass itself declares - the backward-compatibility guarantee the
roadmap requires.
"""
from atlas.research.models import (
    AcceptanceCriterion,
    ClaimStrength,
    CriterionKind,
    CriterionResult,
    DatasetManifest,
    EvaluationMode,
    Evidence,
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
    TargetKind,
    ValidationResult,
    ValidationVerdict,
)
from atlas.research.serialization import (
    evidence_from_dict,
    evidence_to_dict,
    experiment_from_dict,
    experiment_to_dict,
    feature_from_dict,
    feature_to_dict,
    finding_from_dict,
    finding_to_dict,
    hypothesis_from_dict,
    hypothesis_to_dict,
    leaderboard_snapshot_from_dict,
    leaderboard_snapshot_to_dict,
    promotion_record_from_dict,
    promotion_record_to_dict,
    realization_from_dict,
    realization_to_dict,
    validation_result_from_dict,
    validation_result_to_dict,
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


def _criterion_result() -> CriterionResult:
    return CriterionResult(criterion=_acceptance_criterion(), actual_value=0.5, passed=True, reason=None)


def _hypothesis(**overrides) -> Hypothesis:
    fields = dict(
        hypothesis_id="h1", registered_at=_OCCURRED_AT, author="tester", statement="stub claim",
        dataset_symbol="MNQU6", dataset_timeframe="5m", dataset_start=_OCCURRED_AT, dataset_end=_OCCURRED_AT,
        acceptance_criteria=(_acceptance_criterion(),),
        status=HypothesisStatus.PROMOTION_CANDIDATE, provenance=ProvenanceKind.DISCOVERY_ENGINE,
        origin_finding_id="fnd1", derived_from="h0", feature_refs=("f1", "f2"),
        context_description="compressed regime", outcome_metric="15-bar forward return",
        expected_relationship="positive", superseded_by="h2", fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return Hypothesis(**fields)


def _experiment(**overrides) -> Experiment:
    fields = dict(
        experiment_id="e1", hypothesis_id="h1", executed_at=_OCCURRED_AT, code_version="abc123",
        dataset_manifest=_dataset_manifest(), criteria_results=(_criterion_result(),), passed=True,
        profiling_report_path=None,
        realization_id="r1", dataset_manifests=(_dataset_manifest(), _dataset_manifest()),
        evaluation_mode=EvaluationMode.WALK_FORWARD, seed=42, status=ExperimentStatus.RUNNING,
        provenance=ProvenanceKind.AI_ASSISTANT,
        semantic_fingerprint="aaaaaaaaaaaaaaaa", execution_fingerprint="bbbbbbbbbbbbbbbb",
    )
    fields.update(overrides)
    return Experiment(**fields)


def _feature(**overrides) -> Feature:
    fields = dict(
        feature_id="f1", name="stub_feature", tier=FeatureTier.CANDIDATE, version="1.0",
        description="stub", definition={"window": 5}, status=FeatureStatus.PROPOSED,
        provenance=ProvenanceKind.HUMAN, created_at=_OCCURRED_AT, fingerprint="0123456789abcdef",
        superseded_by="f2",
    )
    fields.update(overrides)
    return Feature(**fields)


def _finding(**overrides) -> Finding:
    fields = dict(
        finding_id="fnd1", discovered_at=_OCCURRED_AT, discovery_method="correlation", discovery_method_version="1.0",
        dataset_manifest=_dataset_manifest(), feature_refs=("f1", "f2"), description="stub",
        metrics={"correlation": 0.3}, status=FindingStatus.FORMALIZED, fingerprint="0123456789abcdef",
        claim_strength=ClaimStrength.CAUSAL, formalized_into="h1",
    )
    fields.update(overrides)
    return Finding(**fields)


def _realization(**overrides) -> Realization:
    fields = dict(
        realization_id="r1", hypothesis_id="h1", kind=RealizationKind.STATISTICAL_TEST, version="1.0",
        parameters={"lookback": 20}, status=RealizationStatus.DRAFTED, provenance=ProvenanceKind.HUMAN,
        created_at=_OCCURRED_AT, fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return Realization(**fields)


def _evidence(**overrides) -> Evidence:
    fields = dict(
        evidence_id="ev1", experiment_id="e1", computed_at=_OCCURRED_AT, metrics={"effect_size": 0.2},
        fingerprint="0123456789abcdef", decision_sequence_path="/tmp/seq.json",
    )
    fields.update(overrides)
    return Evidence(**fields)


def _validation_result(**overrides) -> ValidationResult:
    fields = dict(
        validation_id="v1", hypothesis_id="h1", evidence_ids=("ev1", "ev2"), verdict=ValidationVerdict.SUPPORTED,
        criteria_results=(_criterion_result(),), justification="clears threshold with p<0.01",
        validated_at=_OCCURRED_AT, out_of_sample=True, multiple_testing_correction="bonferroni",
        fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return ValidationResult(**fields)


def _leaderboard_entry(**overrides) -> LeaderboardEntry:
    fields = dict(
        hypothesis_id="h1", realization_id="r1", rank=1, score=0.9, score_description="stub",
        validation_id="v1",
    )
    fields.update(overrides)
    return LeaderboardEntry(**fields)


def _leaderboard_snapshot(**overrides) -> LeaderboardSnapshot:
    fields = dict(
        snapshot_id="s1", created_at=_OCCURRED_AT, entries=(_leaderboard_entry(),),
        fingerprint="0123456789abcdef", benchmark_description="buy-and-hold",
        ranking_policy_id="recency_organizational", ranking_policy_version="1.0",
        excluded_validation_ids=("v2", "v3"),
    )
    fields.update(overrides)
    return LeaderboardSnapshot(**fields)


def _promotion_record(**overrides) -> PromotionRecord:
    fields = dict(
        promotion_id="p1", hypothesis_id="h1", realization_id="r1", decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear, reproducible, out-of-sample evidence", evidence_snapshot_ref="v1",
        decided_at=_OCCURRED_AT, fingerprint="0123456789abcdef", resulting_production_change_ref="PR-42",
    )
    fields.update(overrides)
    return PromotionRecord(**fields)


# ---- round-trip: every Sprint 1 field, not just the Sprint 28 ones ----

def test_hypothesis_round_trip_preserves_every_sprint1_field():
    h = _hypothesis()
    assert hypothesis_from_dict(hypothesis_to_dict(h)) == h


def test_experiment_round_trip_preserves_every_sprint1_field():
    e = _experiment()
    assert experiment_from_dict(experiment_to_dict(e)) == e


def test_feature_round_trips():
    f = _feature()
    assert feature_from_dict(feature_to_dict(f)) == f


def test_finding_round_trips():
    f = _finding()
    assert finding_from_dict(finding_to_dict(f)) == f


def test_realization_round_trips():
    r = _realization()
    assert realization_from_dict(realization_to_dict(r)) == r


def test_evidence_round_trips():
    e = _evidence()
    assert evidence_from_dict(evidence_to_dict(e)) == e


def test_validation_result_round_trips():
    v = _validation_result()
    assert validation_result_from_dict(validation_result_to_dict(v)) == v


def test_leaderboard_snapshot_round_trips():
    s = _leaderboard_snapshot()
    assert leaderboard_snapshot_from_dict(leaderboard_snapshot_to_dict(s)) == s


def test_leaderboard_snapshot_from_dict_loads_a_pre_sprint7_record_missing_every_new_key():
    """Exactly what a pre-Sprint-7 LeaderboardSnapshotTracker line looked
    like - no ranking_policy_id/ranking_policy_version/
    excluded_validation_ids, and no per-entry validation_id."""
    old_record = {
        "snapshot_id": "s1", "created_at": _OCCURRED_AT,
        "entries": [
            {"hypothesis_id": "h1", "realization_id": "r1", "rank": 1, "score": 0.9, "score_description": "stub"},
        ],
        "fingerprint": "0123456789abcdef", "benchmark_description": "buy-and-hold",
    }
    snapshot = leaderboard_snapshot_from_dict(old_record)
    assert snapshot.ranking_policy_id is None
    assert snapshot.ranking_policy_version is None
    assert snapshot.excluded_validation_ids == ()
    assert snapshot.entries[0].validation_id is None


def test_promotion_record_round_trips():
    p = _promotion_record()
    assert promotion_record_from_dict(promotion_record_to_dict(p)) == p


# ---- backward compatibility: a pre-Sprint-2 JSONL line still loads ----

def test_hypothesis_from_dict_loads_a_pre_sprint2_record_missing_every_new_key():
    """Exactly what a Sprint 28 HypothesisRegistry file's own line looked
    like - only the original 9 keys, none of Sprint 1's."""
    old_record = {
        "hypothesis_id": "h1", "registered_at": _OCCURRED_AT, "author": "tester", "statement": "stub claim",
        "dataset_symbol": "MNQU6", "dataset_timeframe": "5m",
        "dataset_start": _OCCURRED_AT, "dataset_end": _OCCURRED_AT,
        "acceptance_criteria": [
            {"description": "stub", "kind": "min_firing_rate", "target_kind": "fact",
             "target": "trend_5m", "threshold": 0.1}
        ],
        "status": "registered",
    }
    h = hypothesis_from_dict(old_record)
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


def test_experiment_from_dict_loads_a_pre_sprint2_record_missing_every_new_key():
    """Exactly what a Sprint 28 ExperimentTracker file's own line looked
    like - only the original 8 keys, none of Sprint 1's."""
    old_record = {
        "experiment_id": "e1", "hypothesis_id": "h1", "executed_at": _OCCURRED_AT, "code_version": "abc123",
        "dataset_manifest": {
            "symbol": "MNQU6", "timeframe": "5m", "requested_start": _OCCURRED_AT, "requested_end": _OCCURRED_AT,
            "row_count": 1, "first_occurred_at": _OCCURRED_AT, "last_occurred_at": _OCCURRED_AT,
            "source_description": "test", "generated_at": _OCCURRED_AT,
        },
        "criteria_results": [],
        "passed": True,
        "profiling_report_path": None,
    }
    e = experiment_from_dict(old_record)
    assert e.realization_id is None
    assert e.dataset_manifests == ()
    assert e.evaluation_mode == EvaluationMode.SINGLE
    assert e.seed is None
    assert e.status == ExperimentStatus.COMPLETED
    assert e.provenance == ProvenanceKind.HUMAN
    assert e.semantic_fingerprint is None
    assert e.execution_fingerprint is None
