"""Authenticated read-only transport adapter for canonical TraderNow composition."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from atlas.api.trader_now_deps import get_trader_now_application
from atlas.api_models import (
    TraderNowResponse,
    project_trader_now_response,
    trader_now_response_to_dict,
)
from atlas.application import InvalidCompositionTimeError, TraderNowApplication
from atlas.manual_ai_advisory import (
    ManualAIExplanationService,
    explanation_to_dict,
    unavailable_explanation,
)
from atlas.trader_now.errors import (
    TraderNowError,
    UnsupportedTraderNowIdentityError,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class ManualAdvisoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Literal["MNQ"]
    timeframe: Literal["5m"]
    strategy_id: Literal["displacement_volume_context"]


def get_manual_ai_explanation_service(
    request: Request,
) -> ManualAIExplanationService | None:
    """Optional, default-disabled manual AI composition boundary."""
    return getattr(request.app.state, "manual_ai_explanation_service", None)


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


@router.post("/trader-now/manual-advisory")
async def analyze_manual_advisory(
    request: ManualAdvisoryRequest,
    application: TraderNowApplication = Depends(get_trader_now_application),  # noqa: B008
    ai_service: ManualAIExplanationService | None = Depends(  # noqa: B008
        get_manual_ai_explanation_service
    ),
):
    """Compose once on a manual request; AI remains optional and fail-closed."""
    try:
        result = await application.compose_latest(
            symbol=request.symbol,
            timeframe=request.timeframe,
            strategy_id=request.strategy_id,
        )
        projected = trader_now_response_to_dict(project_trader_now_response(result))
        explanation = (
            ai_service.explain(projected)
            if ai_service is not None
            else unavailable_explanation()
        )
        return {
            "schema_version": "manual_advisory_response.v1",
            "trader_now": projected,
            "ai_explanation": explanation_to_dict(explanation),
        }
    except (UnsupportedTraderNowIdentityError, InvalidCompositionTimeError, TraderNowError, TypeError, ValueError):
        logger.error("Manual advisory composition failed closed")
        return JSONResponse(
            {"detail": {"code": "manual_advisory_unavailable"}}, status_code=503
        )
    except Exception:  # noqa: BLE001 - public route must sanitize unknown failures
        logger.error("Unexpected manual advisory failure")
        return JSONResponse(
            {"detail": {"code": "manual_advisory_unavailable"}}, status_code=503
        )
