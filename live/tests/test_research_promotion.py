"""
Phase N4 Sprint 9. Tests for atlas.research.promotion.service -
list_promotion_candidates()'s own filtering/surfacing contract and
record_decision()'s construction/persistence contract.
"""
from datetime import datetime, timezone

import pytest

from atlas.research.models import LeaderboardEntry, LeaderboardSnapshot, PromotionDecision, PromotionRecord
from atlas.research.promotion.service import list_promotion_candidates, record_decision
from atlas.research.stores import PromotionRecordTracker

_OCCURRED_AT = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc).isoformat()


def _entry(hypothesis_id="h1", realization_id=None, rank=1, validation_id="v1") -> LeaderboardEntry:
    return LeaderboardEntry(
        hypothesis_id=hypothesis_id, realization_id=realization_id, rank=rank,
        score=1.0, score_description="stub", validation_id=validation_id,
    )


def _snapshot(entries: tuple) -> LeaderboardSnapshot:
    return LeaderboardSnapshot(
        snapshot_id="snap1", created_at=_OCCURRED_AT, entries=entries, fingerprint="0123456789abcdef",
    )


def _promotion(
    promotion_id="p1", hypothesis_id="h1", realization_id=None,
    decision=PromotionDecision.APPROVED, rationale="clear, reproducible evidence",
) -> PromotionRecord:
    return PromotionRecord(
        promotion_id=promotion_id, hypothesis_id=hypothesis_id, realization_id=realization_id,
        decision=decision, reviewer="tester", rationale=rationale, evidence_snapshot_ref="v1",
        decided_at=_OCCURRED_AT, fingerprint="0123456789abcdef",
    )


# ---- list_promotion_candidates() ----

def test_list_promotion_candidates_returns_every_entry_when_nothing_reviewed_yet():
    snapshot = _snapshot((_entry("h1", rank=1), _entry("h2", rank=2)))
    candidates = list_promotion_candidates(snapshot, ())
    assert len(candidates) == 2
    assert all(c.prior_decisions == () for c in candidates)


def test_list_promotion_candidates_excludes_an_already_approved_entry():
    snapshot = _snapshot((_entry("h1", rank=1), _entry("h2", rank=2)))
    prior = (_promotion(hypothesis_id="h1", decision=PromotionDecision.APPROVED),)
    candidates = list_promotion_candidates(snapshot, prior)
    assert {c.entry.hypothesis_id for c in candidates} == {"h2"}


def test_list_promotion_candidates_retains_and_surfaces_a_declined_entry():
    """Design Principle V.3 (roadmap's own required test): a DECLINED
    record is retained and surfaces on a resubmission attempt - never
    silently hidden, and never silently excluded either."""
    snapshot = _snapshot((_entry("h1"),))
    prior = (_promotion(hypothesis_id="h1", decision=PromotionDecision.DECLINED, rationale="insufficient effect size"),)
    candidates = list_promotion_candidates(snapshot, prior)
    assert len(candidates) == 1
    assert candidates[0].prior_decisions == prior
    assert candidates[0].prior_decisions[0].decision == PromotionDecision.DECLINED


def test_list_promotion_candidates_retains_and_surfaces_a_deferred_entry():
    """The blueprint's own lifecycle: DEFERRED can re-enter review later -
    it must still appear in the queue, with its own history attached."""
    snapshot = _snapshot((_entry("h1"),))
    prior = (_promotion(hypothesis_id="h1", decision=PromotionDecision.DEFERRED),)
    candidates = list_promotion_candidates(snapshot, prior)
    assert len(candidates) == 1
    assert candidates[0].prior_decisions[0].decision == PromotionDecision.DEFERRED


def test_list_promotion_candidates_distinguishes_by_realization_id():
    """A decision-free (realization_id=None) and a decision-bearing
    Realization of the SAME hypothesis are distinct promotion candidates -
    an APPROVED decision on one must never exclude the other."""
    snapshot = _snapshot((_entry("h1", realization_id=None, rank=1), _entry("h1", realization_id="r1", rank=2)))
    prior = (_promotion(hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED),)
    candidates = list_promotion_candidates(snapshot, prior)
    assert len(candidates) == 1
    assert candidates[0].entry.realization_id == "r1"


def test_list_promotion_candidates_is_pure_no_ledger_access():
    """No tracker/store parameter anywhere in the signature - already
    proven structurally, this test just documents the intent with a call
    that only ever touches its own arguments."""
    snapshot = _snapshot((_entry("h1"),))
    result_a = list_promotion_candidates(snapshot, ())
    result_b = list_promotion_candidates(snapshot, ())
    assert result_a == result_b


# ---- record_decision() ----

def test_record_decision_constructs_and_persists(tmp_path):
    tracker = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    record = record_decision(
        hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear, reproducible, out-of-sample evidence",
        evidence_snapshot_ref="v1", promotion_id="p1", decided_at=_OCCURRED_AT, tracker=tracker,
    )
    assert tracker.get("p1") == record
    assert record.decision == PromotionDecision.APPROVED


def test_record_decision_never_sets_resulting_production_change_ref(tmp_path):
    """The user's own explicit requirement: Sprint 9 must not know
    anything about production artifacts - record_decision() doesn't even
    accept a parameter for this field."""
    import inspect
    assert "resulting_production_change_ref" not in inspect.signature(record_decision).parameters

    tracker = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    record = record_decision(
        hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear evidence", evidence_snapshot_ref="v1",
        promotion_id="p1", decided_at=_OCCURRED_AT, tracker=tracker,
    )
    assert record.resulting_production_change_ref is None


def test_record_decision_requires_non_blank_rationale(tmp_path):
    """Enforced by PromotionRecord.__post_init__ itself (Sprint 1,
    unchanged) - never re-validated here, proven by letting the real
    error surface."""
    tracker = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    with pytest.raises(ValueError, match="rationale"):
        record_decision(
            hypothesis_id="h1", realization_id=None, decision=PromotionDecision.DECLINED,
            reviewer="tester", rationale="   ", evidence_snapshot_ref="v1",
            promotion_id="p1", decided_at=_OCCURRED_AT, tracker=tracker,
        )


def test_record_decision_fingerprint_deterministic(tmp_path):
    tracker_a = PromotionRecordTracker(tmp_path / "a.jsonl")
    tracker_b = PromotionRecordTracker(tmp_path / "b.jsonl")
    kwargs = dict(
        hypothesis_id="h1", realization_id="r1", decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear evidence", evidence_snapshot_ref="v1",
        promotion_id="p1", decided_at=_OCCURRED_AT,
    )
    a = record_decision(**kwargs, tracker=tracker_a)
    b = record_decision(**kwargs, tracker=tracker_b)
    assert a.fingerprint == b.fingerprint


def test_record_decision_fingerprint_changes_with_decision(tmp_path):
    tracker = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    approved = record_decision(
        hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear evidence", evidence_snapshot_ref="v1",
        promotion_id="p1", decided_at=_OCCURRED_AT, tracker=tracker,
    )
    declined = record_decision(
        hypothesis_id="h2", realization_id=None, decision=PromotionDecision.DECLINED,
        reviewer="tester", rationale="clear evidence", evidence_snapshot_ref="v1",
        promotion_id="p2", decided_at=_OCCURRED_AT, tracker=tracker,
    )
    assert approved.fingerprint != declined.fingerprint


def test_record_decision_conflicting_resubmission_raises(tmp_path):
    from atlas.research.stores import RecordConflictError
    tracker = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    record_decision(
        hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear evidence", evidence_snapshot_ref="v1",
        promotion_id="p1", decided_at=_OCCURRED_AT, tracker=tracker,
    )
    with pytest.raises(RecordConflictError):
        record_decision(
            hypothesis_id="h1", realization_id=None, decision=PromotionDecision.DECLINED,
            reviewer="tester", rationale="different rationale entirely", evidence_snapshot_ref="v1",
            promotion_id="p1", decided_at=_OCCURRED_AT, tracker=tracker,
        )


def test_record_decision_identical_resubmission_is_a_safe_no_op(tmp_path):
    tracker = PromotionRecordTracker(tmp_path / "promotions.jsonl")
    kwargs = dict(
        hypothesis_id="h1", realization_id=None, decision=PromotionDecision.APPROVED,
        reviewer="tester", rationale="clear evidence", evidence_snapshot_ref="v1",
        promotion_id="p1", decided_at=_OCCURRED_AT, tracker=tracker,
    )
    record_decision(**kwargs)
    record_decision(**kwargs)  # must not raise
    assert len(tracker.all()) == 1
