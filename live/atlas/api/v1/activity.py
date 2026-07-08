"""
GET /api/v1/activity - unified chronological activity feed for the frontend's
Activity Center, aggregating existing trades/ai_notes/risk/status data into one list.
See atlas/activity.py for the actual event-building logic (kept pure and testable in
isolation, same pattern as atlas/api/v1/risk.py -> atlas/risk.py). Visibility only:
this endpoint only reads data the trades/risk/status endpoints already expose; it
can't affect order execution.
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from atlas.activity import build_activity_feed
from atlas.api.deps import get_repository, get_system_status
from atlas.config import settings
from atlas.events import types as event_types
from atlas.repositories.base import TradeRepository
from atlas.risk import compute_risk_snapshot
from atlas.status import SystemStatus

router = APIRouter()

# Same reasoning as risk.py/stats.py: Python-side aggregation over a generously-sized
# recent window is fine at this strategy's trade volume, revisit if that stops being true.
TRADE_SCAN_LIMIT = 1000
AI_NOTES_SCAN_LIMIT = 500

PICKMYTRADE_EVENT_TYPES = [event_types.TRADE_ENTRY_FORWARDED, event_types.TRADE_ENTRY_FORWARD_FAILED]
CLAUDE_EVENT_TYPES = [event_types.AI_ENTRY_SCORED, event_types.AI_TRADE_REVIEWED, event_types.AI_REPORT_GENERATED]


@router.get("/activity")
async def activity(
    limit: int = Query(default=150, ge=1, le=500),
    repository: TradeRepository = Depends(get_repository),
    system_status: SystemStatus = Depends(get_system_status),
):
    trades = await repository.list_recent(limit=TRADE_SCAN_LIMIT)
    ai_notes = await repository.list_ai_notes(limit=AI_NOTES_SCAN_LIMIT)

    risk_snapshot = compute_risk_snapshot(
        trades,
        starting_balance=settings.account_starting_balance,
        daily_loss_limit=settings.account_daily_loss_limit,
        trailing_drawdown_limit=settings.account_trailing_drawdown_limit,
        max_contracts=settings.account_max_contracts,
        point_value=settings.account_point_value,
        account_configured=settings.account_configured,
    )

    try:
        await repository.ping()
        database_ok, database_detail = True, "ok"
    except Exception as e:
        database_ok, database_detail = False, f"error: {e}"

    pmt_type, pmt_at = system_status.most_recent(PICKMYTRADE_EVENT_TYPES)
    pmt_payload = system_status.last_payload(pmt_type) if pmt_type else None

    claude_type, claude_at = system_status.most_recent(CLAUDE_EVENT_TYPES)
    claude_payload = system_status.last_payload(claude_type) if claude_type else None

    events = build_activity_feed(
        trades=trades,
        ai_notes=ai_notes,
        risk_snapshot=risk_snapshot,
        database_ok=database_ok,
        database_detail=database_detail,
        pmt_configured=bool(settings.pickmytrade_webhook_url),
        pmt_last_error=pmt_payload.get("pmt_error") if pmt_payload else None,
        pmt_last_forward_at=pmt_at,
        claude_configured=bool(settings.anthropic_api_key),
        claude_last_error=claude_payload.get("error") if claude_payload else None,
        claude_last_at=claude_at,
        limit=limit,
    )
    return {"count": len(events), "events": [asdict(e) for e in events]}
