"""
Analytics endpoints - three resources over the same closed-trade history, matching the
three distinct shapes the frontend needs (scalar summary cards, a time series for the
equity/drawdown chart, and grouped breakdown tables), rather than one endpoint mixing
all three response shapes together. See atlas/analytics.py for the actual computation
(pure functions, tested in isolation) - this module is fetch-trades-and-serialize only.
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends

from atlas.analytics import compute_breakdown, compute_equity_curve, compute_summary
from atlas.api.deps import get_repository
from atlas.config import settings
from atlas.repositories.base import TradeRepository

router = APIRouter()

# Same reasoning as stats.py/risk.py: Python-side aggregation over a generously-sized
# recent window is fine at this strategy's trade volume, revisit if that stops being true.
SCAN_LIMIT = 2000


@router.get("/analytics/summary")
async def analytics_summary(repository: TradeRepository = Depends(get_repository)):
    trades = await repository.list_recent(limit=SCAN_LIMIT)
    return asdict(compute_summary(trades, point_value=settings.account_point_value))


@router.get("/analytics/equity-curve")
async def analytics_equity_curve(repository: TradeRepository = Depends(get_repository)):
    trades = await repository.list_recent(limit=SCAN_LIMIT)
    return asdict(compute_equity_curve(trades, starting_balance=settings.account_starting_balance))


@router.get("/analytics/breakdown")
async def analytics_breakdown(repository: TradeRepository = Depends(get_repository)):
    trades = await repository.list_recent(limit=SCAN_LIMIT)
    return asdict(compute_breakdown(trades))
