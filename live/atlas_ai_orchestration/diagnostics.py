"""Process-local sanitized provider-failure classification."""

from __future__ import annotations

from enum import Enum
from threading import Lock

from atlas_ai_analysis.errors import OutputRejectionClassification


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

    __slots__ = ("_counts", "_lock", "_phase18b_counts")

    def __init__(self) -> None:
        self._counts = {classification: 0 for classification in ProviderFailureClassification}
        self._phase18b_counts = {
            classification: 0 for classification in OutputRejectionClassification
        }
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

    def record_phase18b(self, classification: OutputRejectionClassification) -> None:
        selected = (
            classification
            if type(classification) is OutputRejectionClassification
            else OutputRejectionClassification.OTHER_SEMANTIC_REJECTION
        )
        with self._lock:
            self._phase18b_counts[selected] += 1

    def phase18b_snapshot(self) -> dict[OutputRejectionClassification, int]:
        """Return detached, bounded Phase 18B rule counters for local inspection."""

        with self._lock:
            return dict(self._phase18b_counts)


class ProviderTransportDiagnostics:
    """Content-free count of actual provider transport attempts."""

    __slots__ = ("_attempts", "_lock")

    def __init__(self) -> None:
        self._attempts = 0
        self._lock = Lock()

    def record_attempt(self) -> None:
        with self._lock:
            self._attempts += 1

    def snapshot(self) -> int:
        with self._lock:
            return self._attempts
