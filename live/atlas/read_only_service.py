"""Dedicated structurally read-only TraderNow FastAPI service."""

from __future__ import annotations

import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from atlas.api.security import require_api_key
from atlas.api.v1 import operations, trader_now
from atlas.application.trader_now_production import (
    TraderNowProductionConfig,
    build_trader_now_application,
)
from atlas.config import settings
from atlas.logging_config import configure_logging
from atlas.market_engine.repositories.postgres import PostgresMarketStateRepository
from atlas.read_only_db import create_read_only_pool, verify_read_only_access

configure_logging()
logger = logging.getLogger("atlas.read_only_service")


def _validate_configuration() -> TraderNowProductionConfig:
    if settings.environment not in ("production", "development"):
        raise RuntimeError("ENVIRONMENT must be 'production' or 'development'")
    if settings.trader_now_service_mode != "read_only":
        raise RuntimeError("TRADER_NOW_SERVICE_MODE must be exactly 'read_only'")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    if not settings.api_key:
        raise RuntimeError("API_KEY is required")
    required = {
        "TRADER_NOW_PRODUCT": settings.trader_now_product,
        "TRADER_NOW_MARKET_DATA_PROVIDER": settings.trader_now_market_data_provider,
        "TRADER_NOW_MARKET_DATA_SERIES_SYMBOL": (
            settings.trader_now_market_data_series_symbol
        ),
        "TRADER_NOW_MARKET_DATA_SERIES_TYPE": (
            settings.trader_now_market_data_series_type
        ),
        "TRADER_NOW_SERIES_RESOLUTION_VERSION": (
            settings.trader_now_series_resolution_version
        ),
        "TRADER_NOW_SERIES_EFFECTIVE_DATE": (
            settings.trader_now_series_effective_date
        ),
        "TRADER_NOW_CALENDAR_VERSION": settings.trader_now_calendar_version,
        "TRADER_NOW_HOLIDAYS_JSON": settings.trader_now_holidays_json,
        "TRADER_NOW_EARLY_CLOSES_JSON": settings.trader_now_early_closes_json,
        "TRADER_NOW_BUILD_COMMIT": settings.trader_now_build_commit,
        "TRADER_NOW_RELEASE_TAG": settings.trader_now_release_tag,
        "TRADER_NOW_BUILD_TIMESTAMP": settings.trader_now_build_timestamp,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} required by TraderNow read-only service"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", settings.trader_now_build_commit):
        raise RuntimeError("TRADER_NOW_BUILD_COMMIT must be a full lowercase Git SHA")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", settings.trader_now_release_tag
    ):
        raise RuntimeError("TRADER_NOW_RELEASE_TAG has an invalid format")
    try:
        build_timestamp = datetime.fromisoformat(
            settings.trader_now_build_timestamp.replace("Z", "+00:00")
        )
    except ValueError:
        raise RuntimeError("TRADER_NOW_BUILD_TIMESTAMP must be ISO-8601") from None
    if build_timestamp.tzinfo is None or build_timestamp.utcoffset() is None:
        raise RuntimeError("TRADER_NOW_BUILD_TIMESTAMP must be timezone-aware")
    return TraderNowProductionConfig.from_settings(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = None
    startup_stage = "configuration"
    try:
        config = _validate_configuration()
        startup_stage = "database"
        pool = await create_read_only_pool(settings.database_url)
        startup_stage = "assembly"
        repository = PostgresMarketStateRepository(pool)
        application = build_trader_now_application(
            repository=repository,
            config=config,
        )
    except Exception:
        if pool is not None:
            await pool.close()
        logger.error(
            "trader_now_read_service_startup_failed",
            extra={
                "error_code": "startup_validation_failed",
                "failure_category": startup_stage,
            },
        )
        raise RuntimeError(
            f"TraderNow read-only startup failed ({startup_stage})"
        ) from None

    app.state.started_at = datetime.now(timezone.utc)
    app.state.pool = pool
    app.state.market_state_repository = repository
    app.state.trader_now_application = application
    app.state.configuration_valid = True
    app.state.last_success_at = None
    app.state.last_response_duration_ms = None
    logger.info(
        "trader_now_read_service_started",
        extra={
            "service": "trader-now-read-only",
            "calendar_version": config.calendar.version,
            "series_resolution_version": config.resolution_version,
        },
    )
    try:
        yield
    finally:
        await pool.close()
        logger.info("trader_now_read_service_stopped")


app = FastAPI(
    title="TraderNow Read-Only Analysis API",
    version="1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    supplied = request.headers.get("X-Correlation-ID", "")
    try:
        correlation_id = str(UUID(supplied)) if supplied else str(uuid4())
    except ValueError:
        correlation_id = str(uuid4())
    started = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - started) * 1000
    if 200 <= response.status_code < 400:
        request.app.state.last_success_at = (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
        request.app.state.last_response_duration_ms = round(elapsed_ms, 3)
    response.headers["X-Correlation-ID"] = correlation_id
    logger.info(
        "read_only_request_completed",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "route": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round(elapsed_ms, 3),
        },
    )
    return response


@app.get("/health")
async def health():
    """Process liveness only; deliberately independent of PostgreSQL."""
    return {"ok": True, "service": "trader-now-read-only"}


@app.get("/readiness", dependencies=[Depends(require_api_key)])
async def readiness(request: Request):
    """Authenticated database and assembly readiness without composition."""
    if not getattr(request.app.state, "configuration_valid", False):
        return JSONResponse(
            {"ok": False, "code": "configuration_unavailable"},
            status_code=503,
        )
    application = getattr(request.app.state, "trader_now_application", None)
    pool = getattr(request.app.state, "pool", None)
    if application is None or pool is None:
        return JSONResponse(
            {"ok": False, "code": "application_unavailable"},
            status_code=503,
        )
    try:
        await verify_read_only_access(pool)
    except Exception:
        logger.warning(
            "trader_now_readiness_failed",
            extra={"error_code": "database_read_failed"},
        )
        return JSONResponse(
            {"ok": False, "code": "database_unavailable"},
            status_code=503,
        )
    return {"ok": True, "service": "trader-now-read-only"}


app.include_router(
    trader_now.router,
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
)
app.include_router(
    operations.router,
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
)
