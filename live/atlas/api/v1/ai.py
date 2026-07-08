"""
AI Copilot endpoints: read access to AI notes (entry scores, post-trade reviews,
reports) and report generation triggers (Sprint 6), plus on-demand intelligence
snapshots (Sprint 7). Entry scoring and post-trade review themselves are not
triggered here - those are scheduled automatically from atlas/api/v1/webhook.py on
entry/exit respectively. This module only exposes what's already been generated, plus
ways to compute things on demand.

Report generation is deliberately request-then-poll, not request-then-wait: POST
returns 202 immediately and the actual Claude call happens in a background task (see
atlas/ai.py) - consistent with "AI must run async/background only" applying to every
AI-triggering endpoint in this system, not just the ones on the webhook path.

GET /ai/intelligence/{correlation_id} is different in kind, not just degree: it makes
no Claude call and persists nothing. It's a synchronous re-run of
atlas/intelligence.py's pure computation against the trade's current state and the
current historical dataset, for "what would we compute right now" access at zero cost
- works for any trade, open or closed, not just the one that was scored at entry time.

Sprint 9: POST /ai/reports/{period} is rate limited (5/minute) - it's the one
endpoint in this router that costs real money per call (a real Anthropic API call),
and unlike the webhook it isn't gated by anything TradingView-specific, so a leaked/
guessed API key hitting it in a loop would otherwise be an open-ended billing risk.
"""
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse

from atlas.ai import HISTORY_SCAN_LIMIT, run_report_generation
from atlas.api.deps import get_event_bus, get_repository
from atlas.config import settings
from atlas.events.bus import EventBus
from atlas.intelligence import compute_intelligence_snapshot
from atlas.rate_limit import limiter
from atlas.repositories.base import TradeRepository

router = APIRouter()

VALID_PERIODS = {"daily", "weekly"}
VALID_NOTE_TYPES = {"entry_score", "post_trade_review", "daily_report", "weekly_report"}


@router.get("/ai/notes")
async def list_ai_notes(
    trade_correlation_id: Optional[str] = Query(default=None),
    note_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    repository: TradeRepository = Depends(get_repository),
):
    if note_type is not None and note_type not in VALID_NOTE_TYPES:
        return JSONResponse(
            {"ok": False, "error": f"invalid note_type '{note_type}', must be one of {sorted(VALID_NOTE_TYPES)}"},
            status_code=400,
        )
    notes = await repository.list_ai_notes(
        trade_correlation_id=trade_correlation_id, note_type=note_type, limit=limit,
    )
    return {"count": len(notes), "notes": notes}


@router.get("/ai/reports")
async def list_reports(
    period: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    repository: TradeRepository = Depends(get_repository),
):
    if period is not None and period not in VALID_PERIODS:
        return JSONResponse(
            {"ok": False, "error": f"invalid period '{period}', must be one of {sorted(VALID_PERIODS)}"},
            status_code=400,
        )
    note_type = f"{period}_report" if period else None
    if note_type:
        reports = await repository.list_ai_notes(note_type=note_type, limit=limit)
    else:
        daily = await repository.list_ai_notes(note_type="daily_report", limit=limit)
        weekly = await repository.list_ai_notes(note_type="weekly_report", limit=limit)
        reports = sorted(daily + weekly, key=lambda n: n["created_at"], reverse=True)[:limit]
    return {"count": len(reports), "reports": reports}


@router.post("/ai/reports/{period}")
@limiter.limit("5/minute")
async def trigger_report(
    request: Request,
    period: str,
    background_tasks: BackgroundTasks,
    repository: TradeRepository = Depends(get_repository),
    event_bus: EventBus = Depends(get_event_bus),
):
    if period not in VALID_PERIODS:
        return JSONResponse(
            {"ok": False, "error": f"period must be one of {sorted(VALID_PERIODS)}"}, status_code=400,
        )
    # Scheduled, not awaited - the response goes out before Claude is ever called.
    background_tasks.add_task(run_report_generation, period, repository, event_bus)
    return JSONResponse({"ok": True, "status": "generating", "period": period}, status_code=202)


@router.get("/ai/intelligence/{correlation_id}")
async def get_intelligence(
    correlation_id: str,
    repository: TradeRepository = Depends(get_repository),
):
    trade = await repository.get_by_correlation_id(correlation_id)
    if trade is None:
        return JSONResponse(
            {"ok": False, "error": f"no trade found for correlation_id {correlation_id}"}, status_code=404,
        )

    trades = await repository.list_recent(limit=HISTORY_SCAN_LIMIT)
    snapshot = compute_intelligence_snapshot(trade, trades, point_value=settings.account_point_value)

    return {
        "correlation_id": correlation_id,
        "similar_trade_count": snapshot.similar_trade_count,
        "confidence_score": snapshot.confidence_score,
        "confidence_label": snapshot.confidence_label,
        "summary": asdict(snapshot.summary),
        "factors": [asdict(f) for f in snapshot.factors],
    }
