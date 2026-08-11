"""One explicit, operator-triggered snapshot capture use case."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from atlas_snapshot import (
    SOURCE_DOMAIN_SCHEMA_VERSION,
    SOURCE_RESPONSE_SCHEMA_VERSION,
    SnapshotIntegrityError,
    SnapshotProjectionError,
    SnapshotRecordIdentity,
    SnapshotValidationError,
    digest,
    extract_metadata,
    project,
    serialize,
    validate,
    verify,
)
from atlas_snapshot_store import (
    SnapshotCorruptionError,
    SnapshotIdempotencyConflictError,
    SnapshotNotFoundError,
    SnapshotRepository,
    SnapshotStoreError,
)

from .config import CaptureServiceConfig
from .errors import CaptureFailure, CaptureFailureCode, TraderNowClientFailure
from .models import (
    CaptureDisposition,
    CaptureRequest,
    CaptureResult,
    HealthStatus,
    ReadinessStatus,
)
from .ports import SnapshotCompletedObserver, TraderNowClient
from .uuid7 import generate_uuid7

logger = logging.getLogger("atlas.snapshot_capture")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class SnapshotCaptureService:
    """Coordinates HTTP evidence acquisition and append-only persistence."""

    def __init__(
        self,
        *,
        config: CaptureServiceConfig,
        client: TraderNowClient,
        repository: SnapshotRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        uuid7_factory: Callable[[], str] | None = None,
        completed_observer: SnapshotCompletedObserver | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._repository = repository
        self._clock = clock
        self._uuid7_factory = uuid7_factory or (lambda: generate_uuid7(now=self._clock))
        self._completed_observer = completed_observer
        self._started = False

    async def start(self) -> None:
        self._config.validate()
        await self._client.start()
        self._started = True

    async def close(self) -> None:
        try:
            await self._client.close()
        finally:
            self._started = False

    def health(self) -> HealthStatus:
        """Process health never depends on business-data availability."""
        return HealthStatus()

    async def readiness(self) -> ReadinessStatus:
        if not self._started:
            return ReadinessStatus(False, "not_started")
        try:
            self._config.validate()
        except CaptureFailure:
            return ReadinessStatus(False, "configuration_unavailable")
        if not self._config.enabled:
            return ReadinessStatus(False, "service_disabled")
        try:
            await self._repository.list_metadata(limit=1)
        except SnapshotStoreError:
            return ReadinessStatus(False, "snapshot_store_unavailable")
        return ReadinessStatus(True, "ready")

    async def capture(self, request: CaptureRequest) -> CaptureResult:
        correlation_id = self._correlation_id(request.correlation_id)
        started = time.monotonic()
        try:
            self._require_available()
            self._validate_request(request)
            response = await self._fetch(request, correlation_id)
            self._validate_source(response)
            self._validate_approved_response_identity(response)
            created_at = self._clock()
            record = SnapshotRecordIdentity(
                snapshot_id=self._uuid7_factory(),
                created_at=created_at,
            )
            snapshot = self._project(response, record)
            payload = self._serialize(snapshot)
            evidence_digest = digest(snapshot)
            idempotency_key = snapshot["idempotency_key"]

            existing = await self._existing_by_digest(evidence_digest)
            if existing is not None:
                return self._duplicate_result(
                    existing,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )

            try:
                appended = await self._repository.append(payload)
            except SnapshotIdempotencyConflictError as error:
                existing = await self._existing_by_digest(evidence_digest)
                if existing is not None:
                    return self._duplicate_result(
                        existing,
                        idempotency_key=idempotency_key,
                        correlation_id=correlation_id,
                    )
                raise CaptureFailure(CaptureFailureCode.IDEMPOTENCY_CONFLICT) from error
            except SnapshotStoreError as error:
                raise CaptureFailure(CaptureFailureCode.STORE_TRANSACTION) from error

            persisted = await self._retrieve(appended.metadata.snapshot_id)
            if serialize(persisted) != payload:
                raise CaptureFailure(CaptureFailureCode.INTEGRITY)
            verify(persisted)
            metadata = extract_metadata(persisted)
            result = CaptureResult(
                disposition=(
                    CaptureDisposition.CREATED
                    if appended.created
                    else CaptureDisposition.DUPLICATE
                ),
                snapshot_id=metadata.snapshot_id,
                evidence_digest=metadata.evidence_digest,
                idempotency_key=persisted["idempotency_key"],
                correlation_id=correlation_id,
                metadata=metadata,
            )
            self._log_success(result, started)
            self._notify_completed(persisted)
            return result
        except CaptureFailure as error:
            logger.warning(
                "snapshot_capture_failed",
                extra={
                    "correlation_id": correlation_id,
                    "failure_code": error.code.value,
                },
            )
            raise

    def _require_available(self) -> None:
        if not self._started:
            raise CaptureFailure(CaptureFailureCode.CONFIGURATION)
        try:
            self._config.validate()
        except CaptureFailure as error:
            raise CaptureFailure(CaptureFailureCode.CONFIGURATION) from error
        if not self._config.enabled:
            raise CaptureFailure(CaptureFailureCode.SERVICE_DISABLED)

    def _validate_request(self, request: CaptureRequest) -> None:
        approved = self._config.approved_identity
        if not request.symbol or not request.timeframe or not request.strategy_id:
            raise CaptureFailure(CaptureFailureCode.INVALID_REQUEST)
        if (
            request.symbol != approved.product
            or request.timeframe != approved.timeframe
            or request.strategy_id != approved.strategy_id
        ):
            raise CaptureFailure(CaptureFailureCode.INVALID_IDENTITY)

    async def _fetch(
        self, request: CaptureRequest, correlation_id: str
    ) -> Mapping[str, Any]:
        try:
            return await self._client.fetch_latest(
                request,
                correlation_id=correlation_id,
            )
        except TraderNowClientFailure:
            raise
        except Exception as error:
            raise CaptureFailure(CaptureFailureCode.TRADER_NOW_NETWORK) from error

    @staticmethod
    def _validate_source(response: Mapping[str, Any]) -> None:
        if (
            response.get("schema_version") != SOURCE_RESPONSE_SCHEMA_VERSION
            or response.get("domain_schema_version") != SOURCE_DOMAIN_SCHEMA_VERSION
        ):
            raise CaptureFailure(CaptureFailureCode.UNSUPPORTED_SOURCE_SCHEMA)
        required = {
            "evaluated_at",
            "input_snapshot_at",
            "identity",
            "trust",
            "availability",
            "market",
            "source_trust",
            "rules",
            "setups",
            "context",
            "interpretations",
            "strategy",
            "risk",
            "decision",
        }
        if not required.issubset(response):
            raise CaptureFailure(CaptureFailureCode.TRADER_NOW_RESPONSE)

    def _validate_approved_response_identity(self, response: Mapping[str, Any]) -> None:
        approved = self._config.approved_identity
        identity = response.get("identity")
        market = response.get("market")
        if not isinstance(identity, Mapping) or not isinstance(market, Mapping):
            raise CaptureFailure(CaptureFailureCode.TRADER_NOW_RESPONSE)
        if (
            identity.get("product") != approved.product
            or identity.get("timeframe") != approved.timeframe
            or identity.get("strategy_id") != approved.strategy_id
        ):
            raise CaptureFailure(CaptureFailureCode.INVALID_IDENTITY)
        series = market.get("market_data_series")
        if series is None:
            return
        if not isinstance(series, Mapping):
            raise CaptureFailure(CaptureFailureCode.TRADER_NOW_RESPONSE)
        if (
            series.get("provider") != approved.market_data_provider
            or series.get("symbol") != approved.market_data_series_symbol
            or series.get("series_type") != approved.market_data_series_type
            or series.get("resolution_version")
            != approved.market_data_resolution_version
        ):
            raise CaptureFailure(CaptureFailureCode.INVALID_IDENTITY)

    @staticmethod
    def _project(
        response: Mapping[str, Any],
        record: SnapshotRecordIdentity,
    ) -> Mapping[str, Any]:
        try:
            snapshot = project(response, record)
        except SnapshotProjectionError as error:
            raise CaptureFailure(CaptureFailureCode.SDK_PROJECTION) from error
        except SnapshotValidationError as error:
            raise CaptureFailure(CaptureFailureCode.SDK_VALIDATION) from error
        try:
            validate(snapshot)
            verify(snapshot)
        except (SnapshotValidationError, SnapshotIntegrityError) as error:
            raise CaptureFailure(CaptureFailureCode.SDK_VALIDATION) from error
        return snapshot

    @staticmethod
    def _serialize(snapshot: Mapping[str, Any]) -> bytes:
        try:
            return serialize(snapshot)
        except SnapshotValidationError as error:
            raise CaptureFailure(CaptureFailureCode.SDK_SERIALIZATION) from error

    async def _existing_by_digest(
        self, evidence_digest: str
    ) -> Mapping[str, Any] | None:
        try:
            return await self._repository.get_by_evidence_digest(evidence_digest)
        except SnapshotNotFoundError:
            return None
        except SnapshotCorruptionError as error:
            raise CaptureFailure(CaptureFailureCode.INTEGRITY) from error
        except SnapshotStoreError as error:
            raise CaptureFailure(CaptureFailureCode.STORE_UNAVAILABLE) from error

    async def _retrieve(self, snapshot_id: str) -> Mapping[str, Any]:
        try:
            return await self._repository.get_by_snapshot_id(snapshot_id)
        except SnapshotCorruptionError as error:
            raise CaptureFailure(CaptureFailureCode.INTEGRITY) from error
        except SnapshotStoreError as error:
            raise CaptureFailure(CaptureFailureCode.STORE_UNAVAILABLE) from error

    @staticmethod
    def _duplicate_result(
        existing: Mapping[str, Any],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> CaptureResult:
        try:
            verify(existing)
            metadata = extract_metadata(existing)
        except (SnapshotValidationError, SnapshotIntegrityError) as error:
            raise CaptureFailure(CaptureFailureCode.INTEGRITY) from error
        if existing.get("idempotency_key") != idempotency_key:
            raise CaptureFailure(CaptureFailureCode.IDEMPOTENCY_CONFLICT)
        result = CaptureResult(
            disposition=CaptureDisposition.DUPLICATE,
            snapshot_id=metadata.snapshot_id,
            evidence_digest=metadata.evidence_digest,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            metadata=metadata,
        )
        logger.info(
            "snapshot_capture_duplicate",
            extra={
                "correlation_id": correlation_id,
                "snapshot_id": metadata.snapshot_id,
                "evidence_digest": metadata.evidence_digest,
            },
        )
        return result

    def _notify_completed(self, snapshot: Mapping[str, Any]) -> None:
        observer = self._completed_observer
        if observer is None:
            return
        try:
            observer.submit(snapshot)
        except Exception:  # noqa: BLE001 - analysis cannot affect capture
            logger.error("shadow_analysis_trigger_failed")

    @staticmethod
    def _correlation_id(supplied: str | None) -> str:
        value = supplied or str(uuid4())
        if not _CORRELATION_ID.fullmatch(value):
            raise CaptureFailure(CaptureFailureCode.INVALID_REQUEST)
        return value

    @staticmethod
    def _log_success(result: CaptureResult, started: float) -> None:
        logger.info(
            "snapshot_capture_completed",
            extra={
                "correlation_id": result.correlation_id,
                "snapshot_id": result.snapshot_id,
                "evidence_digest": result.evidence_digest,
                "disposition": result.disposition.value,
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
            },
        )
