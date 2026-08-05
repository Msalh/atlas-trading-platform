"""Immutable public value types for the pure AI Analysis Contract SDK."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

RefusalReason = Literal[
    "snapshot_stale",
    "snapshot_unavailable",
    "snapshot_integrity_failed",
    "snapshot_schema_unsupported",
]
FailureReason = Literal[
    "provider_timeout",
    "provider_unavailable",
    "invalid_output",
    "missing_citation",
    "deterministic_state_contradiction",
    "prohibited_content",
    "cost_limit",
    "internal_unavailable",
]

_VALIDATED_OUTPUT_CAPABILITY = object()


class ValidatedAnalysisOutput:
    """Immutable output produced only by the Phase 18B validation authority."""

    __slots__ = ("__value",)

    def __init__(self, value: Mapping[str, Any], capability: object) -> None:
        if capability is not _VALIDATED_OUTPUT_CAPABILITY:
            raise TypeError("validated output construction is private")
        object.__setattr__(self, "_ValidatedAnalysisOutput__value", value)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("validated output is immutable")

    @property
    def value(self) -> Mapping[str, Any]:
        return self.__value

    @property
    def status(self) -> Literal["available", "unavailable"]:
        return cast(Literal["available", "unavailable"], self.__value["status"])

    @property
    def unavailable_reason(self) -> FailureReason | None:
        return cast(FailureReason | None, self.__value["unavailable_reason"])


def _validated_analysis_output(value: Mapping[str, Any]) -> ValidatedAnalysisOutput:
    return ValidatedAnalysisOutput(value, _VALIDATED_OUTPUT_CAPABILITY)


@dataclass(frozen=True, slots=True)
class SnapshotVerification:
    """Trusted verifier attestation; this SDK never computes Snapshot digests."""

    snapshot_id: str
    evidence_digest: str
    status: Literal["verified", "corrupted"]


@dataclass(frozen=True, slots=True)
class AnalysisInputIdentity:
    analysis_input_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class AnalysisAuditIdentity:
    analysis_audit_id: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class GeneratorIdentity:
    """Non-secret generator identifiers, never provider configuration."""

    provider_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class EligibleAnalysis:
    """An invocation-safe input derived from one externally verified Snapshot."""

    snapshot: Mapping[str, Any]
    analysis_input: Mapping[str, Any]
    freshness: Literal["current", "delayed"]


@dataclass(frozen=True, slots=True)
class RefusedAnalysis:
    """Fail-closed result; deliberately contains no analysis input or output."""

    snapshot_id: str
    evidence_digest: str
    purpose: str
    reason: RefusalReason
