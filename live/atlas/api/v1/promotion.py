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
from atlas.research.models import PromotionDecision
from atlas.research.promotion.service import list_promotion_candidates, record_decision
from atlas.research.serialization import promotion_record_to_dict
from atlas.research_deploy.startup_check import LedgerReadiness, LedgerStores

router = APIRouter()


class PromotionDecisionRequest(BaseModel):
    hypothesis_id: str
    realization_id: Optional[str] = None
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

    promotion_id = f"promotion_{uuid.uuid4().hex[:12]}"
    decided_at = datetime.now(timezone.utc).isoformat()
    try:
        record = record_decision(
            hypothesis_id=body.hypothesis_id, realization_id=body.realization_id,
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
