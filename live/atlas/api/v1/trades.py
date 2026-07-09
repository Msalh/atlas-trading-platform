"""
Read-only trade endpoints for the frontend: current position, trade history, and a
single trade's detail + derived lifecycle timeline. Purely additive on top of the
existing `trades` table - no schema change, no effect on the webhook/relay path.

Timeline note: there is still no `trade_events` table for price updates (see
docs/sprint2/api-contracts-addendum.md), so the timeline still reflects the *latest*
known price update, not a full history of every price_update webhook received. AI
notes are different as of Sprint 6: they come from the real `ai_notes` table (one row
per AI pass, with a real timestamp), not the single-slot `llm_analysis` column - a
trade can now show both its entry score and its post-trade review as distinct,
correctly-timed timeline entries. Pre-Sprint-6 trades that only have the old
`llm_analysis`/`llm_error` columns populated (and no matching ai_notes rows) still
show that as a single legacy entry, so old data doesn't just disappear.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from atlas.api.deps import get_repository
from atlas.repositories.base import TradeRepository

router = APIRouter()

# test_closed (developer E2E cleanup, see scripts/close_e2e_test_trades.py) is a real,
# queryable status - "searchable through the API" - not a performance outcome, so it's
# excluded everywhere analytics/risk/stats compute over won/lost trades (see
# atlas/api/v1/stats.py), but a valid filter value here.
VALID_STATUSES = {"open", "won", "lost", "test_closed"}


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
    ai_notes = await repository.list_ai_notes(trade_correlation_id=correlation_id)
    return {"trade": trade, "timeline": build_timeline(trade, ai_notes)}


def build_timeline(t: dict[str, Any], ai_notes: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
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

    ai_notes = ai_notes or []
    entry_score_notes = [n for n in ai_notes if n["note_type"] == "entry_score"]
    review_notes = [n for n in ai_notes if n["note_type"] == "post_trade_review"]

    if entry_score_notes:
        for n in entry_score_notes:
            events.append({
                "type": "entry_score",
                "at": n["created_at"],
                "score": n["score"],
                "score_label": n["score_label"],
                "content": n["content"],
                "error": n["error"],
                # Sprint 7: deterministic numbers atlas/intelligence.py computed before
                # Claude was ever called - see atlas/ai.py::run_entry_score.
                "expected_r": n["expected_r"],
                "historical_win_rate_pct": n["historical_win_rate_pct"],
                "similar_trade_count": n["similar_trade_count"],
                "factors": n["factors"],
            })
    elif t["llm_analysis"] or t["llm_error"]:
        # Legacy (pre-Sprint-6) single-slot analysis - only shown when there are no
        # real ai_notes rows for this trade, so old data doesn't disappear but new
        # trades never show both.
        events.append({
            "type": "ai_analysis",
            "at": None,  # never had a per-analysis timestamp - see module docstring
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

    for n in review_notes:
        events.append({
            "type": "post_trade_review",
            "at": n["created_at"],
            "content": n["content"],
            "error": n["error"],
        })

    return events
