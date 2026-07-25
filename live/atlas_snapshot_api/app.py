"""Private authenticated API over the frozen capture and store boundaries."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from atlas_snapshot import (
    SnapshotIntegrityError,
    SnapshotMetadata,
    extract_metadata,
    serialize,
    verify,
)
from atlas_snapshot_capture import (
    CaptureFailure,
    CaptureFailureCode,
    CaptureRequest,
    SnapshotCaptureService,
)
from atlas_snapshot_store import (
    SnapshotCorruptionError,
    SnapshotNotFoundError,
    SnapshotRepository,
    SnapshotStoreError,
)

from .auth import (
    SnapshotAuthConfig,
    SnapshotPrincipal,
    require_operator,
    require_reader,
)
from .cursors import decode_cursor, encode_cursor
from .models import (
    CaptureBody,
    CaptureResponse,
    ErrorResponse,
    IntegrityResponse,
    MetadataResponse,
    SnapshotListResponse,
    SnapshotResponse,
    StatusResponse,
)
from .rate_limit import FixedWindowRateLimiter

logger = logging.getLogger("atlas.snapshot_api")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _metadata(metadata: SnapshotMetadata) -> MetadataResponse:
    return MetadataResponse(**asdict(metadata))


def _capture_status(code: CaptureFailureCode) -> int:
    if code in {CaptureFailureCode.INVALID_REQUEST, CaptureFailureCode.INVALID_IDENTITY}:
        return 400
    if code is CaptureFailureCode.IDEMPOTENCY_CONFLICT:
        return 409
    if code in {
        CaptureFailureCode.CONFIGURATION,
        CaptureFailureCode.SERVICE_DISABLED,
        CaptureFailureCode.STORE_UNAVAILABLE,
        CaptureFailureCode.TRADER_NOW_NETWORK,
        CaptureFailureCode.TRADER_NOW_TIMEOUT,
    }:
        return 503
    return 502


def create_snapshot_app(
    *,
    capture_service: SnapshotCaptureService,
    reader_repository: SnapshotRepository,
    auth: SnapshotAuthConfig,
    limiter: FixedWindowRateLimiter | None = None,
    manage_lifecycle: bool = True,
    startup_callbacks: Sequence[Callable[[], Awaitable[None]]] = (),
    shutdown_callbacks: Sequence[Callable[[], Awaitable[None]]] = (),
) -> FastAPI:
    auth.validate()
    rate_limiter = limiter or FixedWindowRateLimiter()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        started_callbacks: list[Callable[[], Awaitable[None]]] = []
        try:
            for callback in startup_callbacks:
                await callback()
                started_callbacks.append(callback)
            if manage_lifecycle:
                await capture_service.start()
            yield
        finally:
            if manage_lifecycle:
                await capture_service.close()
            for callback in reversed(shutdown_callbacks[: len(started_callbacks)]):
                await callback()

    app = FastAPI(
        title="Atlas Private Snapshot API",
        version="1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.capture_service = capture_service
    app.state.reader_repository = reader_repository
    app.state.snapshot_auth = auth
    app.state.rate_limiter = rate_limiter

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation_id = (
            supplied
            if supplied and _CORRELATION_ID.fullmatch(supplied)
            else str(uuid4())
        )
        request.state.correlation_id = correlation_id
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            "snapshot_api_request_completed",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "route": request.url.path,
                "status_code": response.status_code,
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            },
        )
        return response

    @app.exception_handler(CaptureFailure)
    async def capture_failure(request: Request, error: CaptureFailure):
        return JSONResponse(
            ErrorResponse(
                code=error.code.value,
                message=error.safe_message,
                correlation_id=request.state.correlation_id,
            ).model_dump(),
            status_code=_capture_status(error.code),
        )

    @app.exception_handler(SnapshotNotFoundError)
    async def not_found(request: Request, _: SnapshotNotFoundError):
        return JSONResponse(
            ErrorResponse(
                code="snapshot_not_found",
                message="snapshot was not found",
                correlation_id=request.state.correlation_id,
            ).model_dump(),
            status_code=404,
        )

    @app.exception_handler(SnapshotCorruptionError)
    async def corruption(request: Request, _: SnapshotCorruptionError):
        return JSONResponse(
            ErrorResponse(
                code="snapshot_integrity_failed",
                message="snapshot integrity verification failed",
                correlation_id=request.state.correlation_id,
            ).model_dump(),
            status_code=409,
        )

    @app.exception_handler(SnapshotStoreError)
    async def store_failure(request: Request, _: SnapshotStoreError):
        return JSONResponse(
            ErrorResponse(
                code="snapshot_store_unavailable",
                message="snapshot store is unavailable",
                correlation_id=request.state.correlation_id,
            ).model_dump(),
            status_code=503,
        )

    @app.get("/health", response_model=StatusResponse)
    async def health() -> StatusResponse:
        status = capture_service.health()
        return StatusResponse(ok=status.status == "healthy")

    @app.get("/readiness", response_model=StatusResponse)
    async def readiness(
        _: Annotated[SnapshotPrincipal, Depends(require_reader)],
    ) -> StatusResponse | JSONResponse:
        capture_readiness = await capture_service.readiness()
        if not capture_readiness.ready:
            return JSONResponse(
                StatusResponse(ok=False, code=capture_readiness.code).model_dump(),
                status_code=503,
            )
        try:
            await reader_repository.list_metadata(limit=1)
        except SnapshotStoreError:
            return JSONResponse(
                StatusResponse(
                    ok=False, code="snapshot_reader_unavailable"
                ).model_dump(),
                status_code=503,
            )
        return StatusResponse(ok=True)

    @app.post(
        "/api/v1/snapshots/capture",
        response_model=CaptureResponse,
        status_code=201,
    )
    async def capture(
        body: CaptureBody,
        request: Request,
        principal: Annotated[SnapshotPrincipal, Depends(require_operator)],
    ) -> CaptureResponse | JSONResponse:
        rate_limiter.check(f"capture:{principal.role.value}", 10)
        result = await capture_service.capture(
            CaptureRequest(
                symbol=body.symbol,
                timeframe=body.timeframe,
                strategy_id=body.strategy_id,
                correlation_id=request.state.correlation_id,
            )
        )
        response = CaptureResponse(
            disposition=result.disposition.value,
            snapshot_id=result.snapshot_id,
            evidence_digest=result.evidence_digest,
            idempotency_key=result.idempotency_key,
            correlation_id=result.correlation_id,
            metadata=_metadata(result.metadata),
        )
        if result.disposition.value == "duplicate":
            return JSONResponse(response.model_dump(), status_code=200)
        return response

    @app.get(
        "/api/v1/snapshots/{snapshot_id}",
        response_model=SnapshotResponse,
    )
    async def get_snapshot(
        snapshot_id: UUID,
        principal: Annotated[SnapshotPrincipal, Depends(require_reader)],
    ) -> SnapshotResponse:
        rate_limiter.check(f"read:{principal.role.value}", 120)
        snapshot = await reader_repository.get_by_snapshot_id(str(snapshot_id))
        return SnapshotResponse(snapshot=json.loads(serialize(snapshot)))

    @app.get(
        "/api/v1/snapshots/{snapshot_id}/metadata",
        response_model=MetadataResponse,
    )
    async def get_metadata(
        snapshot_id: UUID,
        principal: Annotated[SnapshotPrincipal, Depends(require_reader)],
    ) -> MetadataResponse:
        rate_limiter.check(f"read:{principal.role.value}", 120)
        snapshot = await reader_repository.get_by_snapshot_id(str(snapshot_id))
        return _metadata(extract_metadata(snapshot))

    @app.get(
        "/api/v1/snapshots/{snapshot_id}/integrity",
        response_model=IntegrityResponse,
    )
    async def integrity(
        snapshot_id: UUID,
        principal: Annotated[SnapshotPrincipal, Depends(require_reader)],
    ) -> IntegrityResponse:
        rate_limiter.check(f"read:{principal.role.value}", 120)
        snapshot = await reader_repository.get_by_snapshot_id(str(snapshot_id))
        try:
            verify(snapshot)
            metadata = extract_metadata(snapshot)
        except SnapshotIntegrityError as error:
            raise SnapshotCorruptionError("snapshot integrity failed") from error
        return IntegrityResponse(
            snapshot_id=metadata.snapshot_id,
            evidence_digest=metadata.evidence_digest,
        )

    @app.get(
        "/api/v1/snapshots",
        response_model=SnapshotListResponse,
    )
    async def list_snapshots(
        principal: Annotated[SnapshotPrincipal, Depends(require_reader)],
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1024),
    ) -> SnapshotListResponse:
        rate_limiter.check(f"read:{principal.role.value}", 120)
        try:
            decoded = decode_cursor(cursor)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="invalid cursor") from error
        page = await reader_repository.list_metadata(limit=limit, cursor=decoded)
        return SnapshotListResponse(
            items=tuple(_metadata(item) for item in page.items),
            next_cursor=encode_cursor(page.next_cursor),
        )

    return app
