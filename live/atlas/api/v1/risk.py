"""
GET /api/v1/risk - account risk snapshot: balance, daily loss, trailing drawdown,
current exposure, unrealized risk on the open position, and a display-only kill
switch status. See atlas/risk.py for the actual computation (kept as pure functions,
tested in isolation) - this module is just fetch-trades-and-serialize.

Sprint 4 is explicitly display only: nothing here blocks order execution or enforces
anything. atlas/api/v1/webhook.py is untouched by this sprint.
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends

from atlas.api.deps import get_repository
from atlas.config import settings
from atlas.repositories.base import TradeRepository
from atlas.risk import compute_risk_snapshot

router = APIRouter()

# Same reasoning as stats.py: Python-side aggregation over a generously-sized recent
# window is fine at this strategy's trade volume, revisit if that stops being true.
SCAN_LIMIT = 1000


@router.get("/risk")
async def risk(repository: TradeRepository = Depends(get_repository)):
    trades = await repository.list_recent(limit=SCAN_LIMIT)
    snapshot = compute_risk_snapshot(
        trades,
        starting_balance=settings.account_starting_balance,
        daily_loss_limit=settings.account_daily_loss_limit,
        trailing_drawdown_limit=settings.account_trailing_drawdown_limit,
        max_contracts=settings.account_max_contracts,
        point_value=settings.account_point_value,
        account_configured=settings.account_configured,
    )
    return asdict(snapshot)
