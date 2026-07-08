"""
GET /health - liveness/readiness check. Verifies the Postgres pool can actually serve
a query, not just that the process is running - a healthy process with a dead DB
connection is exactly the kind of failure that should show as unhealthy, both for
Railway's own health checks and for the Connection Status screen in the frontend.

Deliberately stays lightweight and infra-focused - the richer "who has this process
actually heard from recently" connectivity summary (TradingView/PickMyTrade/Claude)
already lives at GET /status (Sprint 2, see atlas/api/v1/status.py's own docstring for
why the two are kept separate). Sprint 10 adds `uptime_seconds`/`started_at` only -
enough for a monitoring dashboard to detect an unexpected restart without needing to
duplicate /status's connectivity checks here.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from atlas.api.deps import get_repository
from atlas.repositories.base import TradeRepository

router = APIRouter()


@router.get("/health")
async def health(request: Request, repository: TradeRepository = Depends(get_repository)):
    started_at = getattr(request.app.state, "started_at", None)
    uptime_seconds = (datetime.now(timezone.utc) - started_at).total_seconds() if started_at else None

    try:
        await repository.ping()
        return {
            "ok": True,
            "database": "ok",
            "started_at": started_at.isoformat() if started_at else None,
            "uptime_seconds": uptime_seconds,
        }
    except Exception as e:
        return JSONResponse(
            {
                "ok": False,
                "database": f"error: {e}",
                "started_at": started_at.isoformat() if started_at else None,
                "uptime_seconds": uptime_seconds,
            },
            status_code=503,
        )
