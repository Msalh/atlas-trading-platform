"""
GET /stats/today - a lightweight, honestly-scoped account/risk summary computed
directly from the `trades` table. This is explicitly a placeholder for Sprint 2, not
the institutional-quality analytics engine from the platform roadmap (equity curve,
drawdown, expectancy, etc. - see docs from the V2 architecture review) - it exists so
the dashboard has *something real* to show today, using only data that already exists.

"Today" is the UTC calendar day, compared against the received_at/closed_at ISO-8601
strings (which sort/compare correctly as plain strings for this purpose). This is a
simplification - it does not account for trading-session boundaries (e.g. a NY session
that starts the previous UTC day) - documented here rather than silently assumed.

Aggregation happens in Python over `list_recent`, not in SQL - acceptable at this
strategy's trade volume (a handful of trades per day). Revisit with a real SQL
aggregate (or the `daily_stats` materialized table from the architecture doc) if/when
this stops being true.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from atlas.api.deps import get_repository
from atlas.repositories.base import TradeRepository

router = APIRouter()

# How many recent rows to scan for "today" - generously above any plausible daily
# trade count for this strategy, so we never miss an entry from today.
SCAN_LIMIT = 500


@router.get("/stats/today")
async def stats_today(repository: TradeRepository = Depends(get_repository)):
    today = datetime.now(timezone.utc).date().isoformat()
    trades = await repository.list_recent(limit=SCAN_LIMIT)

    entered_today = [t for t in trades if (t["received_at"] or "").startswith(today)]
    closed_today = [t for t in trades if (t["closed_at"] or "").startswith(today)]
    wins_today = [t for t in closed_today if t["status"] == "won"]
    losses_today = [t for t in closed_today if t["status"] == "lost"]
    forward_failures_today = [t for t in entered_today if not t["pmt_forwarded"]]

    open_trade = next((t for t in trades if t["status"] == "open"), None)
    open_risk_points = None
    open_reward_points = None
    if open_trade and open_trade["entry_price"] is not None and open_trade["sl"] is not None and open_trade["tp"] is not None:
        if open_trade["direction"] == "long":
            open_risk_points = open_trade["entry_price"] - open_trade["sl"]
            open_reward_points = open_trade["tp"] - open_trade["entry_price"]
        else:
            open_risk_points = open_trade["sl"] - open_trade["entry_price"]
            open_reward_points = open_trade["entry_price"] - open_trade["tp"]

    return {
        "date_utc": today,
        "trades_entered_today": len(entered_today),
        "trades_closed_today": len(closed_today),
        "wins_today": len(wins_today),
        "losses_today": len(losses_today),
        "realized_pnl_today": sum(t["realized_pnl"] or 0 for t in closed_today),
        "pmt_forward_failures_today": len(forward_failures_today),
        "open_position": {
            "correlation_id": open_trade["correlation_id"] if open_trade else None,
            "risk_points": open_risk_points,
            "reward_points": open_reward_points,
        },
    }
