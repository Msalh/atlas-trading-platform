"""Sanitized transport contract for read-only service operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OperationsServiceResponse:
    status: str
    started_at: str
    uptime_seconds: float


@dataclass(frozen=True)
class OperationsBuildResponse:
    commit: str
    release_tag: str
    build_timestamp: str
    response_schema_version: str
    domain_schema_version: str


@dataclass(frozen=True)
class OperationsDatabaseResponse:
    ready: bool
    transaction_read_only: bool
    pool_status: str
    latest_probe_duration_ms: float


@dataclass(frozen=True)
class OperationsRequestsResponse:
    last_success_at: str | None
    last_response_duration_ms: float | None


@dataclass(frozen=True)
class OperationsStatusResponse:
    service: OperationsServiceResponse
    build: OperationsBuildResponse
    database: OperationsDatabaseResponse
    requests: OperationsRequestsResponse
