"""
GET /status - powers the Connection Status panel. Distinct from GET /health (which
answers "is this process up and can it reach the database", used for infra health
checks) - this answers "who has this process actually heard from recently", derived
from the in-process SystemStatus event tracker (see atlas/status.py). Resets on every
deploy/restart by design - see that module's docstring.

Production-hardening amendment 3: also exposes the one-time startup
research-snapshot readiness check (atlas/research_export/startup_check.py)
here, not inside the frozen /research/dataset-health payload - this is
operational/deployment state, not a fact about the research baseline
itself, so it belongs on the same operational surface as the database/
webhook/PickMyTrade/Claude checks below, never folded into FROZEN
content.

Sprint 8.2: research_ledger exposes the same one-time startup readiness
check for the Research Ledger's nine JSONL stores
(atlas/research_deploy/startup_check.py) - the write-side counterpart to
research_snapshots above.
"""
import logging

from fastapi import APIRouter, Depends

from atlas.api.deps import get_ledger_readiness, get_repository, get_snapshots_readiness, get_system_status
from atlas.config import settings
from atlas.events import types as event_types
from atlas.repositories.base import TradeRepository
from atlas.research_deploy.startup_check import LedgerReadiness
from atlas.research_export.startup_check import SnapshotsReadiness
from atlas.status import SystemStatus

logger = logging.getLogger(__name__)

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
CLAUDE_EVENT_TYPES = [
    event_types.AI_ENTRY_SCORED,
    event_types.AI_TRADE_REVIEWED,
    event_types.AI_REPORT_GENERATED,
]


@router.get("/status")
async def status(
    repository: TradeRepository = Depends(get_repository),
    system_status: SystemStatus = Depends(get_system_status),
    snapshots_readiness: SnapshotsReadiness = Depends(get_snapshots_readiness),
    ledger_readiness: LedgerReadiness = Depends(get_ledger_readiness),
):
    try:
        await repository.ping()
        database = {"ok": True, "reason": None, "detail": "ok"}
    except Exception:
        # The raw exception (str(e)) is deliberately never put in the response - a
        # Postgres connection error commonly embeds the DSN itself (host, port, and
        # sometimes the password) in its message, e.g. psycopg's
        # "connection failed: connection to server at "10.0.0.5", port 5432 failed:
        # FATAL: password authentication failed for user "atlas"". That text is fine
        # in the server's own log stream (an operator-only surface - see
        # atlas/logging_config.py), but GET /status is a client-facing endpoint this
        # backend serves to the frontend, so it gets a stable, sanitized message
        # instead. `reason` is the machine-readable half of the same contract
        # research_snapshots already uses (a stable code, never free text).
        logger.exception("database ping failed in GET /status")
        database = {
            "ok": False,
            "reason": "ping_failed",
            "detail": "database ping failed - see server logs for details",
        }

    tv_type, tv_at = system_status.most_recent(TRADINGVIEW_EVENT_TYPES)

    pmt_type, pmt_at = system_status.most_recent(PICKMYTRADE_EVENT_TYPES)
    pmt_payload = system_status.last_payload(pmt_type) if pmt_type else None

    claude_type, claude_at = system_status.most_recent(CLAUDE_EVENT_TYPES)
    claude_payload = system_status.last_payload(claude_type) if claude_type else None

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
        "research_snapshots": snapshots_readiness.to_dict(),
        "research_ledger": ledger_readiness.to_dict(),
    }
