"""Authenticated, read-only Shadow Results endpoint."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from atlas.api.deps import get_market_state_repository, get_repository
from atlas.api.security import require_trader_now_results_api_key
from atlas.api.trader_now_deps import get_trader_now_application
from atlas.api_models.shadow_results import ShadowResultsResponse
from atlas.api_models.trader_now import project_trader_now_response
from atlas.application import TraderNowApplication
from atlas.config import settings
from atlas.market_engine.ports import MarketStateRepository
from atlas.repositories.base import TradeRepository
from atlas.shadow_results import build_shadow_results

logger = logging.getLogger(__name__)
router = APIRouter()
STRATEGY_ID = "displacement_volume_context"
TIMEFRAME = "5m"


@router.get("/trader-now/results", response_model=ShadowResultsResponse)
async def read_shadow_results(
    request: Request,
    _authentication: None = Depends(require_trader_now_results_api_key),
    repository: TradeRepository = Depends(get_repository),  # noqa: B008
    market_repository: MarketStateRepository = Depends(  # noqa: B008
        get_market_state_repository
    ),
    application: TraderNowApplication = Depends(  # noqa: B008
        get_trader_now_application
    ),
):
    try:
        trader_now = await application.compose_latest(
            symbol=settings.trader_now_product,
            timeframe=TIMEFRAME,
            strategy_id=STRATEGY_ID,
        )
        return await build_shadow_results(
            repository=repository,
            market_repository=market_repository,
            trader_now=project_trader_now_response(trader_now),
            telemetry=request.app.state.shadow_results_telemetry,
            market_symbol=settings.trader_now_market_data_series_symbol,
            market_timeframe=TIMEFRAME,
            pickmytrade_configured=bool(settings.pickmytrade_webhook_url),
        )
    except Exception:  # noqa: BLE001 - boundary returns one sanitized failure
        logger.error("Shadow results aggregation failed")
        return JSONResponse(
            {"detail": {"code": "shadow_results_unavailable"}},
            status_code=503,
        )
