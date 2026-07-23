"""
Phase N4 Sprint 9. list_promotion_candidates()/record_decision() - see
this package's own __init__.py for the full boundary.
"""
from dataclasses import dataclass
from typing import Optional

from atlas.research.fingerprint import compute_fingerprint
from atlas.research.models import LeaderboardEntry, LeaderboardSnapshot, PromotionDecision, PromotionRecord
from atlas.research.ports import PromotionRecordStore


@dataclass(frozen=True)
class PromotionCandidate:
    """Package-local, not a new Ledger entity (mirrors
    atlas.research.ranking.models.RankingPolicy's own precedent of a
    package-owned supporting type) - list_promotion_candidates()'s own
    return shape, never persisted. prior_decisions is empty for a
    candidate that has never been reviewed before; non-empty (DECLINED/
    DEFERRED only - see list_promotion_candidates()'s own docstring for
    why APPROVED is filtered out upstream) for one a human is
    reconsidering."""

    entry: LeaderboardEntry
    prior_decisions: tuple[PromotionRecord, ...]


def list_promotion_candidates(
    snapshot: LeaderboardSnapshot, existing_promotions: tuple[PromotionRecord, ...],
) -> tuple[PromotionCandidate, ...]:
    """Pure - no Ledger access, mirrors atlas.research.ranking.rank()'s own
    'pure, no Ledger access' shape exactly. `snapshot` is already filtered
    to SUPPORTED-verdict entries by construction (Ranking's own job, not
    re-verified here). Excludes only entries that already carry an
    APPROVED PromotionRecord for their own (hypothesis_id, realization_id)
    pair - already promoted, nothing left to decide. A DECLINED or
    DEFERRED prior decision does NOT exclude a candidate; it is retained
    and surfaced via PromotionCandidate.prior_decisions instead, so a
    reviewer sees the full history rather than a silently-repeated
    question."""
    candidates = []
    for entry in snapshot.entries:
        prior = tuple(
            p for p in existing_promotions
            if p.hypothesis_id == entry.hypothesis_id and p.realization_id == entry.realization_id
        )
        if any(p.decision == PromotionDecision.APPROVED for p in prior):
            continue
        candidates.append(PromotionCandidate(entry=entry, prior_decisions=prior))
    return tuple(candidates)


def record_decision(
    hypothesis_id: str, realization_id: Optional[str], decision: PromotionDecision,
    reviewer: str, rationale: str, evidence_snapshot_ref: str,
    promotion_id: str, decided_at: str, tracker: PromotionRecordStore,
) -> PromotionRecord:
    """The one function in this package that writes. rationale/reviewer
    non-blank is enforced by PromotionRecord.__post_init__ itself (Sprint
    1, unchanged) - never re-validated here, never defaulted. fingerprint
    is a curated projection excluding promotion_id (storage key) and
    decided_at (timestamp), the same lifecycle/identity split every other
    entity's own fingerprint already uses. resulting_production_change_ref
    is deliberately never accepted as a parameter here - see this
    package's own __init__.py for why Research must know nothing about
    production artifacts."""
    fingerprint = compute_fingerprint({
        "hypothesis_id": hypothesis_id,
        "realization_id": realization_id,
        "decision": decision.value,
        "reviewer": reviewer,
        "rationale": rationale,
        "evidence_snapshot_ref": evidence_snapshot_ref,
    })
    record = PromotionRecord(
        promotion_id=promotion_id, hypothesis_id=hypothesis_id, realization_id=realization_id,
        decision=decision, reviewer=reviewer, rationale=rationale, evidence_snapshot_ref=evidence_snapshot_ref,
        decided_at=decided_at, fingerprint=fingerprint,
    )
    tracker.record(record)
    return record
