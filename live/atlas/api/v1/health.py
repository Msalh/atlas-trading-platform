"""
GET /health - liveness/readiness check. Verifies the Postgres pool can actually serve
a query, not just that the process is running - a healthy process with a dead DB
connection is exactly the kind of failure that should show as unhealthy, both for
Railway's own health checks and for the Connection Status screen in the future
frontend.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from atlas.api.deps import get_repository
from atlas.repositories.base import TradeRepository

router = APIRouter()


@router.get("/health")
async def health(repository: TradeRepository = Depends(get_repository)):
    try:
        await repository.ping()
        return {"ok": True, "database": "ok"}
    except Exception as e:
        return JSONResponse({"ok": False, "database": f"error: {e}"}, status_code=503)
