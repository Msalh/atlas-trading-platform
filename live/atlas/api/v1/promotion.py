"""
Sprint 9 (Promotion & Certification). GET /api/v1/research/promotion/
candidates, POST /api/v1/research/promotion/decide, GET /api/v1/research/
promotion - the minimal API surface the Sprint 9 architectural review
concluded Promotion actually needs, matching the frozen roadmap's own two
named public interfaces (list_promotion_candidates()/record_decision(),
renamed from the roadmap's own submit_for_review() per an explicit,
disclosed naming correction - see atlas.research.promotion's own
__init__.py) plus one read endpoint for audit history, a direct
requirement of the review's own Auditability section. No update or delete
endpoint - PromotionRecord is immutable by construction (the Ledger's own
append-only, conflict-on-differing-content discipline), so there is
nothing here to expose.

A separate router from atlas.api.v1.research_pipeline's mode-based
POST /research/run by deliberate choice (per the architectural review):
that endpoint's mode vocabulary (smoke/replay/experiment/benchmark) is
about executing pipeline stages; recording a human's promotion decision is
a different kind of action and doesn't fit that shape.

Same ledger-readiness gating as research_pipeline.py's own endpoints (503
when the Research Ledger is degraded - see atlas.research_deploy.
startup_check), and the same shared API_KEY every other authenticated
router in this app uses.
"""
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from atlas.api.deps import get_ledger_readiness, get_ledger_stores
from atlas.research.models import PromotionDecision, TargetKind
from atlas.research.promotion.service import list_promotion_candidates, record_decision
from atlas.research.serialization import promotion_record_to_dict
from atlas.research_deploy.startup_check import LedgerReadiness, LedgerStores

router = APIRouter()


class PromotionDecisionRequest(BaseModel):
    """realization_id is deliberately NOT a field here - a reviewer must
    never be able to supply it manually (that would let a human assert
    lineage rather than the Ledger proving it). decide_promotion() below
    resolves the exact realization_id itself, straight from the same
    Experiment/Evidence/Validation lineage that produced the candidate's
    LeaderboardEntry - see _resolve_realization_id()."""

    hypothesis_id: str
    decision: Literal["approved", "declined", "deferred"]
    reviewer: str
    rationale: str
    evidence_snapshot_ref: str


def _degraded_response(readiness: LedgerReadiness) -> Optional[JSONResponse]:
    if readiness.status == "ready":
        return None
    return JSONResponse(
        {"ok": False, "error": f"research ledger storage is degraded: {readiness.reason}", "reason": readiness.reason},
        status_code=503,
    )


def _resolve_realization_id(hypothesis_id: str, ledger_stores: LedgerStores) -> tuple[Optional[str], Optional[JSONResponse]]:
    """The one place a promotion decision's realization_id comes from -
    never the reviewer, never inferred, never a 'latest Realization for
    this Hypothesis' lookup. Reads the exact realization_id straight off
    the hypothesis's own entry in the latest LeaderboardSnapshot (the same
    snapshot list_promotion_candidates() itself scopes to) - that entry's
    realization_id is itself only ever set by rank() reading it directly
    off the ValidationResult that produced it (see
    atlas.research.ranking.service.rank()), so this is the exact lineage,
    not a separate lookup. Deliberately does NOT consult
    ledger_stores.hypotheses - the current pipeline (see
    atlas.api.v1.research_pipeline._run_smoke_test) never persists
    Hypothesis objects into the Ledger, so that registry cannot be relied
    on as a signal here.

    When the entry's own realization_id is None, whether that is the
    correct decision-free answer or a lost-lineage problem is
    disambiguated using the exact ValidationResult that produced the
    entry (entry.validation_id -> its criteria_results' own
    AcceptanceCriterion.target_kind) - never the Hypothesis, never a
    separate hypothesis_id-only lookup.

    Returns (realization_id, None) on success - realization_id may
    legitimately be None for a decision-free hypothesis, or when there is
    no current candidate entry to resolve against at all (pre-existing,
    unchanged behavior for ad hoc/manual decisions the promotion API has
    always allowed). Returns (None, error_response) if the entry is
    decision-bearing (its ValidationResult used a DECISION_SEQUENCE
    criterion) but no realization_id could be resolved - refusing to
    record rather than guessing."""
    snapshots = ledger_stores.leaderboard_snapshots.all()
    if not snapshots:
        return None, None

    latest = max(snapshots, key=lambda s: s.created_at)
    matching_entry = next((e for e in latest.entries if e.hypothesis_id == hypothesis_id), None)
    if matching_entry is None:
        return None, None
    if matching_entry.realization_id is not None:
        return matching_entry.realization_id, None

    validation_result = ledger_stores.validation_results.get(matching_entry.validation_id)
    if validation_result is None:
        return None, None

    is_decision_bearing = any(
        cr.criterion.target_kind == TargetKind.DECISION_SEQUENCE for cr in validation_result.criteria_results
    )
    if is_decision_bearing:
        return None, JSONResponse(
            {
                "ok": False,
                "error": (
                    f"hypothesis {hypothesis_id!r}'s current candidate entry is decision-bearing "
                    "(validated against a DECISION_SEQUENCE criterion) but carries no realization_id "
                    "- refusing to record a promotion decision without exact Realization lineage"
                ),
                "reason": "realization_id_unresolved",
            },
            status_code=422,
        )
    return None, None


def _candidate_to_dict(candidate) -> dict:
    entry = candidate.entry
    return {
        "hypothesis_id": entry.hypothesis_id,
        "realization_id": entry.realization_id,
        "rank": entry.rank,
        "score": entry.score,
        "validation_id": entry.validation_id,
        "prior_decisions": [promotion_record_to_dict(p) for p in candidate.prior_decisions],
    }


@router.get("/research/promotion/candidates")
async def read_promotion_candidates(
    ledger_readiness: LedgerReadiness = Depends(get_ledger_readiness),
    ledger_stores: Optional[LedgerStores] = Depends(get_ledger_stores),
):
    degraded = _degraded_response(ledger_readiness)
    if degraded is not None:
        return degraded
    if ledger_stores is None:
        return JSONResponse(
            {"ok": False, "error": "research ledger stores are unavailable", "reason": "internal_error"},
            status_code=503,
        )

    all_snapshots = ledger_stores.leaderboard_snapshots.all()
    if not all_snapshots:
        return JSONResponse({"ok": True, "snapshot_id": None, "candidates": []})

    latest = max(all_snapshots, key=lambda s: s.created_at)
    existing = tuple(ledger_stores.promotions.all())
    candidates = list_promotion_candidates(latest, existing)

    return JSONResponse({
        "ok": True,
        "snapshot_id": latest.snapshot_id,
        "candidates": [_candidate_to_dict(c) for c in candidates],
    })


@router.post("/research/promotion/decide")
async def decide_promotion(
    body: PromotionDecisionRequest,
    ledger_readiness: LedgerReadiness = Depends(get_ledger_readiness),
    ledger_stores: Optional[LedgerStores] = Depends(get_ledger_stores),
):
    degraded = _degraded_response(ledger_readiness)
    if degraded is not None:
        return degraded
    if ledger_stores is None:
        return JSONResponse(
            {"ok": False, "error": "research ledger stores are unavailable", "reason": "internal_error"},
            status_code=503,
        )

    resolved_realization_id, resolution_error = _resolve_realization_id(body.hypothesis_id, ledger_stores)
    if resolution_error is not None:
        return resolution_error

    promotion_id = f"promotion_{uuid.uuid4().hex[:12]}"
    decided_at = datetime.now(timezone.utc).isoformat()
    try:
        record = record_decision(
            hypothesis_id=body.hypothesis_id, realization_id=resolved_realization_id,
            decision=PromotionDecision(body.decision), reviewer=body.reviewer, rationale=body.rationale,
            evidence_snapshot_ref=body.evidence_snapshot_ref, promotion_id=promotion_id, decided_at=decided_at,
            tracker=ledger_stores.promotions,
        )
    except ValueError as e:
        # PromotionRecord.__post_init__'s own blank-rationale/reviewer
        # guard - a real, expected client error, never a 500.
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)

    return JSONResponse({"ok": True, "record": promotion_record_to_dict(record)})


@router.get("/research/promotion")
async def read_promotion_history(
    promotion_id: Optional[str] = None,
    ledger_readiness: LedgerReadiness = Depends(get_ledger_readiness),
    ledger_stores: Optional[LedgerStores] = Depends(get_ledger_stores),
):
    degraded = _degraded_response(ledger_readiness)
    if degraded is not None:
        return degraded
    if ledger_stores is None:
        return JSONResponse(
            {"ok": False, "error": "research ledger stores are unavailable", "reason": "internal_error"},
            status_code=503,
        )

    if promotion_id is not None:
        record = ledger_stores.promotions.get(promotion_id)
        if record is None:
            return JSONResponse({"ok": False, "error": f"no promotion record with id {promotion_id!r}"}, status_code=404)
        return JSONResponse({"ok": True, "record": promotion_record_to_dict(record)})

    records = ledger_stores.promotions.all()
    return JSONResponse({"ok": True, "records": [promotion_record_to_dict(r) for r in records]})
