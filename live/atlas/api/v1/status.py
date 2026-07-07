"""
GET /status - powers the Connection Status panel. Distinct from GET /health (which
answers "is this process up and can it reach the database", used for infra health
checks) - this answers "who has this process actually heard from recently", derived
from the in-process SystemStatus event tracker (see atlas/status.py). Resets on every
deploy/restart by design - see that module's docstring.
"""
from fastapi import APIRouter, Depends

from atlas.api.deps import get_repository, get_system_status
from atlas.config import settings
from atlas.events import types as event_types
from atlas.repositories.base import TradeRepository
from atlas.status import SystemStatus

router = APIRouter()

TRADINGVIEW_EVENT_TYPES = [
    event_types.TRADE_ENTRY_RECEIVED,
    event_types.TRADE_PRICE_UPDATED,
    event_types.TRADE_EXIT,
]
PICKMYTRADE_EVENT_TYPES = [
    event_types.TRADE_ENTRY_FORWARDED,
    event_types.TRADE_ENTRY_FORWARD_FAILED,
]


@router.get("/status")
async def status(
    repository: TradeRepository = Depends(get_repository),
    system_status: SystemStatus = Depends(get_system_status),
):
    try:
        await repository.ping()
        database = {"ok": True, "detail": "ok"}
    except Exception as e:
        database = {"ok": False, "detail": f"error: {e}"}

    tv_type, tv_at = system_status.most_recent(TRADINGVIEW_EVENT_TYPES)

    pmt_type, pmt_at = system_status.most_recent(PICKMYTRADE_EVENT_TYPES)
    pmt_payload = system_status.last_payload(pmt_type) if pmt_type else None

    claude_at = system_status.last_at(event_types.TRADE_AI_ANALYZED)
    claude_payload = system_status.last_payload(event_types.TRADE_AI_ANALYZED)

    return {
        "database": database,
        "tradingview": {
            "last_webhook_at": tv_at,
            "last_webhook_type": tv_type,
        },
        "pickmytrade": {
            "configured": bool(settings.pickmytrade_webhook_url),
            "last_forward_at": pmt_at,
            "last_forward_ok": (pmt_type == event_types.TRADE_ENTRY_FORWARDED) if pmt_type else None,
            "last_error": pmt_payload.get("pmt_error") if pmt_payload else None,
        },
        "claude": {
            "configured": bool(settings.anthropic_api_key),
            "last_analysis_at": claude_at,
            "last_error": claude_payload.get("error") if claude_payload else None,
        },
    }
