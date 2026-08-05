"""Deterministic Phase 18F coordinator for trusted Phase 18D outcomes."""

from __future__ import annotations

import hashlib
from asyncio import CancelledError
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, NoReturn, cast

from atlas_ai_analysis import serialize_audit, validate_audit
from atlas_ai_analysis._json import canonical_bytes
from atlas_ai_analysis.models import ValidatedAnalysisOutput
from atlas_ai_orchestration import (
    CompletedOutcome,
    FailedOutcome,
    RefusedOutcome,
    ServiceUnavailableOutcome,
)
from atlas_ai_orchestration.models import OrchestrationOutcome

from .errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceTimeoutError,
    PersistenceUnavailableError,
)
from .models import (
    AuditOnlyPersistenceRecord,
    CompletedPersistenceRecord,
    NotPersistableResult,
    PersistedResult,
    PersistenceReceipt,
    PersistenceRecord,
    PersistenceResult,
    _audit_only_record,
    _completed_record,
)
from .ports import AtomicPersistencePort


_EXPECTED_VERSIONS = {
    "input": "ai_analysis_input.v1",
    "output": "ai_analysis_output.v1",
    "policy": "ai_analysis_policy.v1",
}


class PersistenceCoordinator:
    def __init__(self, port: AtomicPersistencePort) -> None:
        self._port = port

    def persist(self, outcome: OrchestrationOutcome) -> PersistenceResult:
        if type(outcome) is ServiceUnavailableOutcome:
            return NotPersistableResult()
        record: PersistenceRecord | None = None
        try:
            record = self._record(outcome)
        except Exception:
            pass
        if record is None:
            self._raise_sanitized(PersistenceIntegrityError)

        adapter_error: type[PersistenceError] | None = None
        receipt: PersistenceReceipt | None = None
        try:
            receipt = self._port.store_atomic(record)
        except PersistenceConflictError:
            adapter_error = PersistenceConflictError
        except PersistenceTimeoutError:
            adapter_error = PersistenceTimeoutError
        except PersistenceIntegrityError:
            adapter_error = PersistenceIntegrityError
        except PersistenceUnavailableError:
            adapter_error = PersistenceUnavailableError
        except CancelledError:
            adapter_error = PersistenceUnavailableError
        except Exception:
            adapter_error = PersistenceUnavailableError
        if adapter_error is not None:
            self._raise_sanitized(adapter_error)

        if (
            type(receipt) is not PersistenceReceipt
            or receipt.operation_id != record.operation_id
            or receipt.disposition not in {"committed", "replayed"}
        ):
            self._raise_sanitized(PersistenceIntegrityError)
        return PersistedResult(receipt)

    def _record(self, outcome: OrchestrationOutcome) -> PersistenceRecord:
        if type(outcome) is CompletedOutcome:
            return self._completed(cast(CompletedOutcome, outcome))
        if type(outcome) is FailedOutcome:
            failed = cast(FailedOutcome, outcome)
            return self._audit_only(failed.audit, "failed", failed.reason)
        if type(outcome) is RefusedOutcome:
            refused = cast(RefusedOutcome, outcome)
            return self._audit_only(refused.audit, "refused", None)
        raise PersistenceIntegrityError

    def _completed(self, outcome: CompletedOutcome) -> CompletedPersistenceRecord:
        trusted = outcome._validated_output
        if type(trusted) is not ValidatedAnalysisOutput:
            raise PersistenceIntegrityError
        output = trusted.value
        audit = outcome.audit
        self._validated_audit(audit)
        if output.get("status") != "available" or audit.get("outcome") != "completed":
            raise PersistenceIntegrityError
        bindings = (
            "analysis_input_id",
            "analysis_output_id",
            "snapshot_id",
            "evidence_digest",
            "purpose",
        )
        if any(output.get(name) != audit.get(name) for name in bindings):
            raise PersistenceIntegrityError
        if audit.get("contract_versions") != _EXPECTED_VERSIONS:
            raise PersistenceIntegrityError
        generator = audit.get("generator")
        if not isinstance(generator, Mapping) or set(generator) != {
            "provider_id",
            "model_id",
        }:
            raise PersistenceIntegrityError
        if generator != {
            "provider_id": outcome._generator.provider_id,
            "model_id": outcome._generator.model_id,
        }:
            raise PersistenceIntegrityError
        output_bytes = canonical_bytes(output)
        audit_bytes = serialize_audit(audit)
        return _completed_record(
            validated_output=trusted,
            audit=audit,
            output_bytes=output_bytes,
            audit_bytes=audit_bytes,
            output_digest=self._digest(output_bytes),
            audit_digest=self._digest(audit_bytes),
            operation_id=cast(str, audit["analysis_audit_id"]),
            output_id=cast(str, output["analysis_output_id"]),
        )

    def _audit_only(
        self,
        audit: Mapping[str, Any],
        expected: str,
        expected_reason: str | None,
    ) -> AuditOnlyPersistenceRecord:
        self._validated_audit(audit)
        if audit.get("outcome") != expected or audit.get("analysis_output_id") is not None:
            raise PersistenceIntegrityError
        if expected == "failed" and audit.get("reason_code") != expected_reason:
            raise PersistenceIntegrityError
        if expected == "refused" and audit.get("reason_code") is None:
            raise PersistenceIntegrityError
        audit_bytes = serialize_audit(audit)
        return _audit_only_record(
            audit=audit,
            audit_bytes=audit_bytes,
            audit_digest=self._digest(audit_bytes),
            operation_id=cast(str, audit["analysis_audit_id"]),
            outcome=cast(Any, expected),
        )

    @staticmethod
    def _validated_audit(audit: Mapping[str, Any]) -> None:
        if type(audit) is not MappingProxyType:
            raise PersistenceIntegrityError
        validate_audit(audit)

    @staticmethod
    def _digest(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def _raise_sanitized(error_type: type[PersistenceError]) -> NoReturn:
        error = error_type()
        error.__cause__ = None
        error.__context__ = None
        raise error from None
