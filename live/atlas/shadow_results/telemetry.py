"""Process-scoped counters for the Shadow results operational projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProcessTelemetrySnapshot:
    reset_at: datetime
    authentication_failures: int
    http_5xx_responses: int
    runtime_errors: int
    duplicate_webhooks: int
    rejected_webhooks: int


class ProcessTelemetry:
    """In-memory counters that intentionally reset on every process start."""

    def __init__(self, *, reset_at: datetime | None = None) -> None:
        self._reset_at = reset_at or _utc_now()
        self._authentication_failures = 0
        self._http_5xx_responses = 0
        self._runtime_errors = 0
        self._duplicate_webhooks = 0
        self._rejected_webhooks = 0

    def observe_response(self, *, path: str, status_code: int) -> None:
        if status_code == 401:
            self._authentication_failures += 1
        if status_code >= 500:
            self._http_5xx_responses += 1
        if path in {"/webhook", "/api/v1/webhook", "/api/v1/market-state"}:
            if status_code == 208:
                self._duplicate_webhooks += 1
            elif status_code in {400, 401, 422, 429}:
                self._rejected_webhooks += 1

    def observe_runtime_error(self) -> None:
        self._runtime_errors += 1

    def snapshot(self) -> ProcessTelemetrySnapshot:
        return ProcessTelemetrySnapshot(
            reset_at=self._reset_at,
            authentication_failures=self._authentication_failures,
            http_5xx_responses=self._http_5xx_responses,
            runtime_errors=self._runtime_errors,
            duplicate_webhooks=self._duplicate_webhooks,
            rejected_webhooks=self._rejected_webhooks,
        )
