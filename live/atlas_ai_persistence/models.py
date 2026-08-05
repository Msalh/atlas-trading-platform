"""Closed immutable values for the offline Phase 18F persistence contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from atlas_ai_analysis.models import ValidatedAnalysisOutput


_RECORD_CAPABILITY = object()


@dataclass(frozen=True, slots=True, init=False)
class CompletedPersistenceRecord:
    """Atomic output/audit unit created only from a trusted Phase 18D outcome."""

    _validated_output: ValidatedAnalysisOutput = field(repr=False)
    audit: Mapping[str, Any] = field(repr=False)
    output_bytes: bytes = field(repr=False)
    audit_bytes: bytes = field(repr=False)
    output_digest: str
    audit_digest: str
    operation_id: str
    output_id: str

    def __init__(
        self,
        *,
        validated_output: ValidatedAnalysisOutput,
        audit: Mapping[str, Any],
        output_bytes: bytes,
        audit_bytes: bytes,
        output_digest: str,
        audit_digest: str,
        operation_id: str,
        output_id: str,
        capability: object,
    ) -> None:
        if capability is not _RECORD_CAPABILITY:
            raise TypeError("persistence record construction is private")
        object.__setattr__(self, "_validated_output", validated_output)
        object.__setattr__(self, "audit", audit)
        object.__setattr__(self, "output_bytes", output_bytes)
        object.__setattr__(self, "audit_bytes", audit_bytes)
        object.__setattr__(self, "output_digest", output_digest)
        object.__setattr__(self, "audit_digest", audit_digest)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "output_id", output_id)

    @property
    def output(self) -> Mapping[str, Any]:
        return self._validated_output.value


@dataclass(frozen=True, slots=True, init=False)
class AuditOnlyPersistenceRecord:
    """Atomic audit-only unit for failed and refused Phase 18D outcomes."""

    audit: Mapping[str, Any] = field(repr=False)
    audit_bytes: bytes = field(repr=False)
    audit_digest: str
    operation_id: str
    outcome: Literal["failed", "refused"]

    def __init__(
        self,
        *,
        audit: Mapping[str, Any],
        audit_bytes: bytes,
        audit_digest: str,
        operation_id: str,
        outcome: Literal["failed", "refused"],
        capability: object,
    ) -> None:
        if capability is not _RECORD_CAPABILITY:
            raise TypeError("persistence record construction is private")
        object.__setattr__(self, "audit", audit)
        object.__setattr__(self, "audit_bytes", audit_bytes)
        object.__setattr__(self, "audit_digest", audit_digest)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "outcome", outcome)


type PersistenceRecord = CompletedPersistenceRecord | AuditOnlyPersistenceRecord


@dataclass(frozen=True, slots=True)
class PersistenceReceipt:
    operation_id: str
    disposition: Literal["committed", "replayed"]


@dataclass(frozen=True, slots=True)
class PersistedResult:
    receipt: PersistenceReceipt


@dataclass(frozen=True, slots=True)
class NotPersistableResult:
    reason: Literal["pre_eligibility_service_unavailable"] = (
        "pre_eligibility_service_unavailable"
    )


type PersistenceResult = PersistedResult | NotPersistableResult


def _completed_record(**values: Any) -> CompletedPersistenceRecord:
    return CompletedPersistenceRecord(capability=_RECORD_CAPABILITY, **values)


def _audit_only_record(**values: Any) -> AuditOnlyPersistenceRecord:
    return AuditOnlyPersistenceRecord(capability=_RECORD_CAPABILITY, **values)
