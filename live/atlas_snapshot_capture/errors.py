"""Stable, sanitized failures for the explicit capture use case."""

from __future__ import annotations

from enum import Enum


class CaptureFailureCode(str, Enum):
    INVALID_REQUEST = "invalid_operator_request"
    INVALID_IDENTITY = "invalid_identity"
    TRADER_NOW_AUTHENTICATION = "trader_now_authentication_failed"
    TRADER_NOW_AUTHORIZATION = "trader_now_authorization_failed"
    TRADER_NOW_TIMEOUT = "trader_now_timeout"
    TRADER_NOW_NETWORK = "trader_now_network_failed"
    TRADER_NOW_RESPONSE = "trader_now_response_invalid"
    UNSUPPORTED_SOURCE_SCHEMA = "unsupported_source_schema"
    SDK_PROJECTION = "snapshot_projection_failed"
    SDK_VALIDATION = "snapshot_validation_failed"
    SDK_SERIALIZATION = "snapshot_serialization_failed"
    STORE_UNAVAILABLE = "snapshot_store_unavailable"
    STORE_TRANSACTION = "snapshot_store_transaction_failed"
    IDEMPOTENCY_CONFLICT = "snapshot_idempotency_conflict"
    INTEGRITY = "persisted_snapshot_integrity_failed"
    CONFIGURATION = "capture_configuration_unavailable"
    SERVICE_DISABLED = "capture_service_disabled"


_SAFE_MESSAGES = {
    CaptureFailureCode.INVALID_REQUEST: "capture request is invalid",
    CaptureFailureCode.INVALID_IDENTITY: "capture identity is not approved",
    CaptureFailureCode.TRADER_NOW_AUTHENTICATION: "upstream authentication failed",
    CaptureFailureCode.TRADER_NOW_AUTHORIZATION: "upstream authorization failed",
    CaptureFailureCode.TRADER_NOW_TIMEOUT: "upstream request timed out",
    CaptureFailureCode.TRADER_NOW_NETWORK: "upstream service is unavailable",
    CaptureFailureCode.TRADER_NOW_RESPONSE: "upstream response is malformed",
    CaptureFailureCode.UNSUPPORTED_SOURCE_SCHEMA: "upstream schema is unsupported",
    CaptureFailureCode.SDK_PROJECTION: "snapshot projection failed",
    CaptureFailureCode.SDK_VALIDATION: "snapshot validation failed",
    CaptureFailureCode.SDK_SERIALIZATION: "snapshot serialization failed",
    CaptureFailureCode.STORE_UNAVAILABLE: "snapshot store is unavailable",
    CaptureFailureCode.STORE_TRANSACTION: "snapshot transaction failed",
    CaptureFailureCode.IDEMPOTENCY_CONFLICT: "snapshot idempotency conflict",
    CaptureFailureCode.INTEGRITY: "persisted snapshot failed integrity verification",
    CaptureFailureCode.CONFIGURATION: "capture configuration is unavailable",
    CaptureFailureCode.SERVICE_DISABLED: "capture service is disabled",
}


class CaptureFailure(RuntimeError):
    """An operator-safe failure; causes remain internal and are never rendered."""

    def __init__(self, code: CaptureFailureCode) -> None:
        self.code = code
        self.safe_message = _SAFE_MESSAGES[code]
        super().__init__(self.safe_message)


class TraderNowClientFailure(CaptureFailure):
    """Typed upstream-client failure mapped by the application service."""
