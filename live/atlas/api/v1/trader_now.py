"""Authenticated read-only transport adapter for canonical TraderNow composition."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from atlas.api.trader_now_deps import get_trader_now_application
from atlas.api_models import (
    TraderNowResponse,
    project_trader_now_response,
    trader_now_response_to_dict,
)
from atlas.application import InvalidCompositionTimeError, TraderNowApplication
from atlas.trader_now.errors import (
    TraderNowError,
    UnsupportedTraderNowIdentityError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/trader-now", response_model=TraderNowResponse)
async def read_trader_now(
    symbol: str,
    timeframe: str,
    strategy_id: str,
    application: TraderNowApplication = Depends(get_trader_now_application),
):
    """Compose once, then expose only the approved transport projection."""
    try:
        result = await application.compose_latest(
            symbol=symbol,
            timeframe=timeframe,
            strategy_id=strategy_id,
        )
        response = project_trader_now_response(result)
        return trader_now_response_to_dict(response)
    except UnsupportedTraderNowIdentityError as error:
        return JSONResponse(
            {
                "detail": {
                    "code": "unsupported_trader_now_identity",
                    "field": error.field,
                    "supplied": error.supplied,
                    "supported": error.supported,
                }
            },
            status_code=422,
        )
    except InvalidCompositionTimeError:
        logger.error("TraderNow composition rejected the server-owned clock")
        return JSONResponse(
            {"detail": {"code": "trader_now_composition_invalid"}},
            status_code=500,
        )
    except TraderNowError:
        logger.error("TraderNow composition failed a structural invariant")
        return JSONResponse(
            {"detail": {"code": "trader_now_composition_failed"}},
            status_code=500,
        )
    except (TypeError, ValueError):
        logger.error("TraderNow transport projection failed validation")
        return JSONResponse(
            {"detail": {"code": "trader_now_projection_failed"}},
            status_code=500,
        )
    except Exception:
        logger.error("Unexpected TraderNow request failure")
        return JSONResponse(
            {"detail": {"code": "internal_server_error"}},
            status_code=500,
        )
