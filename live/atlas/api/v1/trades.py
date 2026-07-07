"""
Read-only trade endpoints for the frontend: current position, trade history, and a
single trade's detail + derived lifecycle timeline. Purely additive on top of the
existing `trades` table - no schema change, no effect on the webhook/relay path.

Timeline note: this sprint does not add a `trade_events` table (see
docs/sprint2/api-contracts-addendum.md), so the "timeline" here is derived from the
single trade row's own fields - entry, latest known price update, exit, AI note. It
reflects the *latest* known price update, not a full history of every price_update
webhook received. A true multi-event timeline needs an append-only events table,
which is a natural, well-scoped follow-up sprint, not a change made silently here.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from atlas.api.deps import get_repository
from atlas.repositories.base import TradeRepository

router = APIRouter()

VALID_STATUSES = {"open", "won", "lost"}


@router.get("/trades/current")
async def current_trade(repository: TradeRepository = Depends(get_repository)):
    trade = await repository.get_open_trade()
    return {"open": trade is not None, "trade": trade}


@router.get("/trades")
async def list_trades(
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    repository: TradeRepository = Depends(get_repository),
):
    if status is not None and status not in VALID_STATUSES:
        return JSONResponse(
            {"ok": False, "error": f"invalid status '{status}', must be one of {sorted(VALID_STATUSES)}"},
            status_code=400,
        )
    trades = await repository.list_recent(limit=limit, status=status)
    return {"count": len(trades), "trades": trades}


@router.get("/trades/{correlation_id}")
async def trade_detail(correlation_id: str, repository: TradeRepository = Depends(get_repository)):
    trade = await repository.get_by_correlation_id(correlation_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"no trade found for correlation_id {correlation_id}")
    return {"trade": trade, "timeline": build_timeline(trade)}


def build_timeline(t: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{
        "type": "entry_received",
        "at": t["received_at"],
        "direction": t["direction"],
        "setup_tag": t["setup_tag"],
        "entry_price": t["entry_price"],
        "sl": t["sl"],
        "tp": t["tp"],
    }]

    if t["pmt_forwarded"]:
        events.append({
            "type": "pmt_forwarded",
            "at": t["received_at"],
            "status_code": t["pmt_status_code"],
        })
    else:
        events.append({
            "type": "pmt_forward_failed",
            "at": t["received_at"],
            "error": t["pmt_error"],
        })

    if t["llm_analysis"] or t["llm_error"]:
        events.append({
            "type": "ai_analysis",
            "at": None,  # not tracked per-analysis yet - see module docstring
            "analysis": t["llm_analysis"],
            "error": t["llm_error"],
        })

    if t["last_update_at"]:
        events.append({
            "type": "price_update",
            "at": t["last_update_at"],
            "current_price": t["current_price"],
            "unrealized_pnl": t["unrealized_pnl"],
            "note": "latest known price update, not a full history",
        })

    if t["closed_at"]:
        events.append({
            "type": "exit",
            "at": t["closed_at"],
            "status": t["status"],
            "exit_price": t["exit_price"],
            "realized_pnl": t["realized_pnl"],
        })

    return events
