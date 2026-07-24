"""Sanitized operational projection for the dedicated read-only service."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from atlas.api_models.operations import (
    OperationsBuildResponse,
    OperationsDatabaseResponse,
    OperationsRequestsResponse,
    OperationsServiceResponse,
    OperationsStatusResponse,
)
from atlas.api_models.trader_now import TRADER_NOW_RESPONSE_SCHEMA_VERSION
from atlas.config import settings
from atlas.read_only_db import verify_read_only_access

router = APIRouter()
DOMAIN_SCHEMA_VERSION = "trader_now.v2"


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


@router.get("/operations/status", response_model=OperationsStatusResponse)
async def read_operations_status(request: Request) -> OperationsStatusResponse:
    """Return an allowlisted status snapshot without infrastructure identity."""
    now = datetime.now(timezone.utc)
    started_at: datetime = request.app.state.started_at
    pool = getattr(request.app.state, "pool", None)
    probe_started = time.monotonic()
    database_ready = False
    if pool is not None:
        try:
            await verify_read_only_access(pool)
            database_ready = True
        except Exception:  # noqa: BLE001 - boundary deliberately sanitizes all drivers
            database_ready = False
    probe_ms = round((time.monotonic() - probe_started) * 1000, 3)
    service_status = "healthy" if database_ready else "degraded"

    return OperationsStatusResponse(
        service=OperationsServiceResponse(
            status=service_status,
            started_at=_timestamp(started_at),
            uptime_seconds=round(max(0.0, (now - started_at).total_seconds()), 3),
        ),
        build=OperationsBuildResponse(
            commit=settings.trader_now_build_commit,
            release_tag=settings.trader_now_release_tag,
            build_timestamp=settings.trader_now_build_timestamp,
            response_schema_version=TRADER_NOW_RESPONSE_SCHEMA_VERSION,
            domain_schema_version=DOMAIN_SCHEMA_VERSION,
        ),
        database=OperationsDatabaseResponse(
            ready=database_ready,
            transaction_read_only=database_ready,
            pool_status="open" if database_ready else "unavailable",
            latest_probe_duration_ms=probe_ms,
        ),
        requests=OperationsRequestsResponse(
            last_success_at=getattr(request.app.state, "last_success_at", None),
            last_response_duration_ms=getattr(
                request.app.state, "last_response_duration_ms", None
            ),
        ),
    )
