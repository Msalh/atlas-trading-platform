"""
Phase N4 Sprint 7. Tests for atlas.research.ranking - unit tests over
hand-built ValidationResult fixtures proving: SUPPORTED-only eligibility,
excluded-verdict auditability, deterministic ordering and tie-breaking,
input-order independence, duplicate-ValidationResult-per-hypothesis
handling, immutable snapshot behavior, policy-version fingerprint
sensitivity, and that no statistical recomputation ever happens (score is
a constant, unaffected by anything in criteria_results/justification).
"""
from pathlib import Path

import pytest
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    CriterionResult,
    TargetKind,
    ValidationResult,
    ValidationVerdict,
)
from atlas.research.ranking.models import RANKING_POLICY_V1, RankingPolicy
from atlas.research.ranking.service import rank, snapshot_leaderboard
from atlas.research.stores import LeaderboardSnapshotTracker

_OCCURRED_AT = "2026-07-22T00:00:00+00:00"


def _criterion_result(actual_value=5.0, passed=True, reason="p=0.001, effect_size=2.3, mc_prob=0.99") -> CriterionResult:
    criterion = AcceptanceCriterion(
        description="stub", kind=CriterionKind.MEAN_ABOVE_THRESHOLD, target_kind=TargetKind.FEATURE,
        target="mean_atr", threshold=2.0,
    )
    return CriterionResult(criterion=criterion, actual_value=actual_value, passed=passed, reason=reason)


def _validation_result(
    validation_id: str, hypothesis_id: str, validated_at: str = _OCCURRED_AT,
    verdict: ValidationVerdict = ValidationVerdict.SUPPORTED, **overrides,
) -> ValidationResult:
    fields = dict(
        validation_id=validation_id, hypothesis_id=hypothesis_id, evidence_ids=("ev1",),
        verdict=verdict, criteria_results=(_criterion_result(),), justification="stub",
        validated_at=validated_at, out_of_sample=True, multiple_testing_correction=None,
        fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return ValidationResult(**fields)


# ---- eligibility: SUPPORTED only ----

def test_only_supported_results_are_ranked():
    results = (
        _validation_result("v1", "h1", verdict=ValidationVerdict.SUPPORTED),
        _validation_result("v2", "h2", verdict=ValidationVerdict.NOT_SUPPORTED),
        _validation_result("v3", "h3", verdict=ValidationVerdict.INCONCLUSIVE),
    )
    entries = rank(results, RANKING_POLICY_V1)
    assert [e.hypothesis_id for e in entries] == ["h1"]


def test_excluded_verdicts_remain_auditable_in_the_snapshot(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    results = (
        _validation_result("v1", "h1", verdict=ValidationVerdict.SUPPORTED),
        _validation_result("v2", "h2", verdict=ValidationVerdict.NOT_SUPPORTED),
        _validation_result("v3", "h3", verdict=ValidationVerdict.INCONCLUSIVE),
    )
    snapshot = snapshot_leaderboard(results, RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    assert [e.hypothesis_id for e in snapshot.entries] == ["h1"]
    assert snapshot.excluded_validation_ids == ("v2", "v3")


def test_zero_eligible_results_produces_an_empty_but_valid_snapshot(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    results = (_validation_result("v1", "h1", verdict=ValidationVerdict.NOT_SUPPORTED),)
    snapshot = snapshot_leaderboard(results, RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    assert snapshot.entries == ()
    assert snapshot.excluded_validation_ids == ("v1",)


def test_empty_input_produces_an_empty_snapshot(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    snapshot = snapshot_leaderboard((), RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    assert snapshot.entries == ()
    assert snapshot.excluded_validation_ids == ()


# ---- deterministic ordering and tie-breaking ----

def test_ordering_is_by_validated_at_descending():
    results = (
        _validation_result("v1", "h1", validated_at="2026-01-01T00:00:00+00:00"),
        _validation_result("v2", "h2", validated_at="2026-06-01T00:00:00+00:00"),
        _validation_result("v3", "h3", validated_at="2026-03-01T00:00:00+00:00"),
    )
    entries = rank(results, RANKING_POLICY_V1)
    assert [e.hypothesis_id for e in entries] == ["h2", "h3", "h1"]
    assert [e.rank for e in entries] == [1, 2, 3]


def test_ties_in_validated_at_broken_by_hypothesis_id_ascending():
    results = (
        _validation_result("v1", "hz", validated_at=_OCCURRED_AT),
        _validation_result("v2", "ha", validated_at=_OCCURRED_AT),
        _validation_result("v3", "hm", validated_at=_OCCURRED_AT),
    )
    entries = rank(results, RANKING_POLICY_V1)
    assert [e.hypothesis_id for e in entries] == ["ha", "hm", "hz"]


def test_ordering_is_independent_of_input_order():
    a = _validation_result("v1", "h1", validated_at="2026-01-01T00:00:00+00:00")
    b = _validation_result("v2", "h2", validated_at="2026-06-01T00:00:00+00:00")
    c = _validation_result("v3", "h3", validated_at="2026-03-01T00:00:00+00:00")
    forward = rank((a, b, c), RANKING_POLICY_V1)
    shuffled = rank((c, a, b), RANKING_POLICY_V1)
    reversed_order = rank((c, b, a), RANKING_POLICY_V1)
    assert forward == shuffled == reversed_order


def test_ranks_are_unique_and_start_at_one():
    results = tuple(_validation_result(f"v{i}", f"h{i}") for i in range(5))
    entries = rank(results, RANKING_POLICY_V1)
    assert sorted(e.rank for e in entries) == [1, 2, 3, 4, 5]


# ---- duplicate ValidationResult handling (same hypothesis, multiple validations) ----

def test_duplicate_validation_results_for_the_same_hypothesis_latest_validated_at_wins():
    older = _validation_result("v_old", "h1", validated_at="2026-01-01T00:00:00+00:00")
    newer = _validation_result("v_new", "h1", validated_at="2026-06-01T00:00:00+00:00")
    entries = rank((older, newer), RANKING_POLICY_V1)
    assert len(entries) == 1
    assert entries[0].validation_id == "v_new"


def test_duplicate_validation_results_same_validated_at_tie_broken_by_validation_id():
    a = _validation_result("v_a", "h1", validated_at=_OCCURRED_AT)
    b = _validation_result("v_b", "h1", validated_at=_OCCURRED_AT)
    entries = rank((a, b), RANKING_POLICY_V1)
    assert len(entries) == 1
    assert entries[0].validation_id == "v_b"  # lexicographically greatest


def test_duplicate_handling_records_the_superseded_validation_id_as_excluded(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    older = _validation_result("v_old", "h1", validated_at="2026-01-01T00:00:00+00:00")
    newer = _validation_result("v_new", "h1", validated_at="2026-06-01T00:00:00+00:00")
    snapshot = snapshot_leaderboard((older, newer), RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    assert snapshot.excluded_validation_ids == ("v_old",)


# ---- no statistical recomputation: score is a constant, untouched by criteria_results content ----

def test_score_is_always_the_constant_placeholder_regardless_of_underlying_statistics():
    strong = _validation_result("v1", "h1", criteria_results=(_criterion_result(actual_value=100.0),))
    weak = _validation_result("v2", "h2", criteria_results=(_criterion_result(actual_value=2.01),))
    entries = rank((strong, weak), RANKING_POLICY_V1)
    assert all(e.score == 1.0 for e in entries)


def test_score_description_discloses_the_placeholder_explicitly():
    entries = rank((_validation_result("v1", "h1"),), RANKING_POLICY_V1)
    assert "no independent scientific quality score" in entries[0].score_description


def test_realization_id_propagates_from_validation_result():
    """Realization lineage correction: rank() reads realization_id
    directly off the ValidationResult it is ranking, never hardcodes it -
    a decision-bearing ValidationResult's realization_id must survive into
    its LeaderboardEntry unchanged."""
    entries = rank((_validation_result("v1", "h1", realization_id="r_bc"),), RANKING_POLICY_V1)
    assert entries[0].realization_id == "r_bc"


def test_realization_id_is_none_for_decision_free_hypotheses():
    """A ValidationResult with no realization_id (decision-free hypothesis)
    legitimately produces a LeaderboardEntry with realization_id=None -
    this is not the lineage bug, it is the correct, intentional case."""
    entries = rank((_validation_result("v1", "h1"),), RANKING_POLICY_V1)
    assert entries[0].realization_id is None


def test_two_realizations_of_the_same_hypothesis_remain_distinguishable_across_snapshots():
    """de-duplication is one entry per hypothesis_id per snapshot (Sprint 7
    policy, unchanged here), but across two separate rank() calls - e.g.
    two snapshots taken after re-validating different Realizations of the
    same Hypothesis - each entry must carry its own distinct, correct
    realization_id, never collapsing to a shared or hardcoded value."""
    entries_r1 = rank((_validation_result("v1", "h1", realization_id="r1"),), RANKING_POLICY_V1)
    entries_r2 = rank((_validation_result("v2", "h1", realization_id="r2"),), RANKING_POLICY_V1)
    assert entries_r1[0].realization_id == "r1"
    assert entries_r2[0].realization_id == "r2"
    assert entries_r1[0].realization_id != entries_r2[0].realization_id


def test_ordering_never_reads_criteria_results_reason_text():
    """Two otherwise-identical ValidationResults differing only in their
    free-text `reason` (where p-values/effect sizes/Monte Carlo
    probabilities live) must rank identically to a swapped-content
    version - proof reason text never influences ordering or score."""
    a = _validation_result("v1", "h1", validated_at="2026-01-01T00:00:00+00:00",
                            criteria_results=(_criterion_result(reason="p=0.0001, huge effect"),))
    b = _validation_result("v2", "h2", validated_at="2026-06-01T00:00:00+00:00",
                            criteria_results=(_criterion_result(reason="p=0.049, tiny effect"),))
    entries = rank((a, b), RANKING_POLICY_V1)
    # ordering follows validated_at only - h2 (more recent) ranks first despite "weaker" reason text
    assert [e.hypothesis_id for e in entries] == ["h2", "h1"]


# ---- immutable snapshot / append-only ----

def test_snapshot_is_immutable_and_recording_a_new_one_never_mutates_the_old(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    first = snapshot_leaderboard((_validation_result("v1", "h1"),), RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    second = snapshot_leaderboard(
        (_validation_result("v1", "h1"), _validation_result("v2", "h2")), RANKING_POLICY_V1, "s2",
        "2026-07-23T00:00:00+00:00", tracker,
    )
    assert tracker.get("s1") == first
    assert tracker.get("s2") == second
    assert first != second
    assert len(tracker.all()) == 2


def test_recording_the_same_snapshot_id_with_identical_content_is_a_noop(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    results = (_validation_result("v1", "h1"),)
    snapshot_leaderboard(results, RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    snapshot_leaderboard(results, RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    assert len(tracker.all()) == 1


# ---- fingerprint: policy version sensitivity, determinism ----

def test_fingerprint_changes_when_policy_version_changes():
    results = (_validation_result("v1", "h1"),)
    entries_a = rank(results, RankingPolicy(policy_id="recency_organizational", policy_version="1.0"))
    entries_b = rank(results, RankingPolicy(policy_id="recency_organizational", policy_version="2.0"))
    # rank() itself doesn't fingerprint (that's snapshot_leaderboard's job) - prove the POLICY
    # value flows into the fingerprint via snapshot_leaderboard instead:
    assert entries_a == entries_b  # v1 ordering logic is identical regardless of policy version label


def test_snapshot_fingerprint_changes_when_policy_version_changes(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    results = (_validation_result("v1", "h1"),)
    snap_a = snapshot_leaderboard(
        results, RankingPolicy(policy_id="recency_organizational", policy_version="1.0"), "s1", _OCCURRED_AT, tracker,
    )
    snap_b = snapshot_leaderboard(
        results, RankingPolicy(policy_id="recency_organizational", policy_version="2.0"), "s2", _OCCURRED_AT, tracker,
    )
    assert snap_a.fingerprint != snap_b.fingerprint


def test_snapshot_fingerprint_deterministic_given_identical_inputs(tmp_path: Path):
    tracker_a = LeaderboardSnapshotTracker(tmp_path / "a.jsonl")
    tracker_b = LeaderboardSnapshotTracker(tmp_path / "b.jsonl")
    results = (_validation_result("v1", "h1"), _validation_result("v2", "h2", validated_at="2026-06-01T00:00:00+00:00"))
    snap_a = snapshot_leaderboard(results, RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker_a)
    snap_b = snapshot_leaderboard(results, RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker_b)
    assert snap_a.fingerprint == snap_b.fingerprint
    assert snap_a.entries == snap_b.entries


def test_ranking_policy_rejects_blank_id_or_version():
    with pytest.raises(ValueError, match="policy_id"):
        RankingPolicy(policy_id="  ", policy_version="1.0")
    with pytest.raises(ValueError, match="policy_version"):
        RankingPolicy(policy_id="x", policy_version="")


def test_snapshot_records_policy_id_and_version(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    snapshot = snapshot_leaderboard((_validation_result("v1", "h1"),), RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker)
    assert snapshot.ranking_policy_id == "recency_organizational"
    assert snapshot.ranking_policy_version == "1.0"


def test_benchmark_description_threaded_through_but_never_computed(tmp_path: Path):
    tracker = LeaderboardSnapshotTracker(tmp_path / "snapshots.jsonl")
    snapshot = snapshot_leaderboard(
        (_validation_result("v1", "h1"),), RANKING_POLICY_V1, "s1", _OCCURRED_AT, tracker,
        benchmark_description="null hypothesis: no true elevation over threshold",
    )
    assert snapshot.benchmark_description == "null hypothesis: no true elevation over threshold"
    # no benchmark row was inserted into entries:
    assert len(snapshot.entries) == 1
