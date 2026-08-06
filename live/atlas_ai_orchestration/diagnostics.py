"""Process-local sanitized provider-failure classification."""

from __future__ import annotations

from enum import Enum
from threading import Lock


class ProviderFailureClassification(str, Enum):
    CONNECTIVITY = "connectivity"
    TIMEOUT = "timeout"
    HTTP_4XX = "http_4xx"
    HTTP_429 = "http_429"
    HTTP_5XX = "http_5xx"
    RESPONSE_TOO_LARGE = "response_too_large"
    RESPONSE_DECODE = "response_decode"
    PHASE18B_INVALID_OUTPUT = "phase18b_invalid_output"
    UNKNOWN = "unknown"


class ProviderFailureDiagnostics:
    """Bounded in-memory counters; no provider material is accepted or retained."""

    __slots__ = ("_counts", "_lock")

    def __init__(self) -> None:
        self._counts = {classification: 0 for classification in ProviderFailureClassification}
        self._lock = Lock()

    def record(self, classification: ProviderFailureClassification) -> None:
        selected = (
            classification
            if type(classification) is ProviderFailureClassification
            else ProviderFailureClassification.UNKNOWN
        )
        with self._lock:
            self._counts[selected] += 1

    def snapshot(self) -> dict[ProviderFailureClassification, int]:
        """Return a detached sanitized snapshot for local assertions only."""

        with self._lock:
            return dict(self._counts)
