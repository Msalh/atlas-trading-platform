"""Synchronous, insert-only PostgreSQL implementation of AtomicPersistencePort."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, ContextManager, Final, NoReturn, cast

import psycopg
from psycopg import errors

from atlas_ai_persistence import (
    PersistenceConflictError,
    PersistenceIntegrityError,
    PersistenceReceipt,
    PersistenceTimeoutError,
    PersistenceUnavailableError,
)
from atlas_ai_persistence.models import (
    AuditOnlyPersistenceRecord,
    CompletedPersistenceRecord,
    PersistenceRecord,
)

PERSISTENCE_SCHEMA_VERSION: Final = "atlas_ai_persistence.v1"
CANONICALIZATION_PROFILE: Final = "atlas-ai-canonical-json.v1"
_EXPECTED_CONTRACT_VERSIONS: Final = {
    "input": "ai_analysis_input.v1",
    "output": "ai_analysis_output.v1",
    "policy": "ai_analysis_policy.v1",
}


class PostgresAtomicPersistenceAdapter:
    """Store one closed Phase 18F record in one explicit transaction."""

    def __init__(
        self,
        connection_factory: Callable[[], ContextManager[psycopg.Connection[Any]]],
    ) -> None:
        self._connection_factory = connection_factory

    def store_atomic(self, record: PersistenceRecord) -> PersistenceReceipt:
        error_type: type[Exception] | None = None
        receipt: PersistenceReceipt | None = None
        try:
            receipt = self._store_atomic(record)
        except PersistenceConflictError:
            error_type = PersistenceConflictError
        except PersistenceIntegrityError:
            error_type = PersistenceIntegrityError
        except (errors.QueryCanceled, TimeoutError):
            error_type = PersistenceTimeoutError
        except (errors.SerializationFailure, errors.DeadlockDetected):
            error_type = PersistenceUnavailableError
        except errors.IntegrityError:
            error_type = PersistenceIntegrityError
        except (psycopg.Error, OSError):
            error_type = PersistenceUnavailableError
        except Exception:  # noqa: BLE001 - untrusted driver failures are sanitized
            error_type = PersistenceUnavailableError
        if error_type is not None:
            self._raise_clean(error_type)
        if receipt is None:
            self._raise_clean(PersistenceIntegrityError)
        return receipt

    def _store_atomic(self, record: PersistenceRecord) -> PersistenceReceipt:
        values = self._values(record)
        with self._connection_factory() as connection:
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                inserted = connection.execute(
                    """
                    INSERT INTO atlas_ai_persistence.persistence_records (
                        analysis_audit_id, analysis_output_id, outcome,
                        analysis_input_id, snapshot_id, evidence_digest, purpose,
                        input_contract_version, output_contract_version,
                        policy_contract_version, provider_id, model_id,
                        audit_recorded_at, persistence_schema_version,
                        canonicalization_profile, audit_payload, audit_digest,
                        output_payload, output_digest
                    ) VALUES (
                        %(analysis_audit_id)s::uuid, %(analysis_output_id)s::uuid,
                        %(outcome)s, %(analysis_input_id)s::uuid,
                        %(snapshot_id)s::uuid, %(evidence_digest)s, %(purpose)s,
                        %(input_contract_version)s, %(output_contract_version)s,
                        %(policy_contract_version)s, %(provider_id)s, %(model_id)s,
                        %(audit_recorded_at)s::timestamptz,
                        %(persistence_schema_version)s,
                        %(canonicalization_profile)s, %(audit_payload)s,
                        %(audit_digest)s, %(output_payload)s, %(output_digest)s
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING analysis_audit_id
                    """,
                    values,
                ).fetchone()
                if inserted is not None:
                    disposition = "committed"
                else:
                    rows = self._conflicting_rows(connection, values)
                    if len(rows) != 1 or not self._matches(rows[0], values):
                        raise PersistenceConflictError()
                    disposition = "replayed"
            return PersistenceReceipt(record.operation_id, disposition)

    @classmethod
    def _values(cls, record: PersistenceRecord) -> dict[str, Any]:
        if type(record) not in {CompletedPersistenceRecord, AuditOnlyPersistenceRecord}:
            cls._raise_clean(PersistenceIntegrityError)
        audit = record.audit
        versions = audit.get("contract_versions")
        if versions != _EXPECTED_CONTRACT_VERSIONS:
            cls._raise_clean(PersistenceIntegrityError)
        if cls._digest(record.audit_bytes) != record.audit_digest:
            cls._raise_clean(PersistenceIntegrityError)

        output_payload: bytes | None = None
        output_digest: str | None = None
        output_id: str | None = None
        provider_id: str | None = None
        model_id: str | None = None
        if type(record) is CompletedPersistenceRecord:
            completed = cast(CompletedPersistenceRecord, record)
            if cls._digest(completed.output_bytes) != completed.output_digest:
                cls._raise_clean(PersistenceIntegrityError)
            output_payload = completed.output_bytes
            output_digest = completed.output_digest
            output_id = completed.output_id
            generator = audit.get("generator")
            if not isinstance(generator, Mapping):
                cls._raise_clean(PersistenceIntegrityError)
            provider_id = cast(str, generator.get("provider_id"))
            model_id = cast(str, generator.get("model_id"))
        elif audit.get("analysis_output_id") is not None:
            cls._raise_clean(PersistenceIntegrityError)

        return {
            "analysis_audit_id": record.operation_id,
            "analysis_output_id": output_id,
            "outcome": audit.get("outcome"),
            "analysis_input_id": audit.get("analysis_input_id"),
            "snapshot_id": audit.get("snapshot_id"),
            "evidence_digest": audit.get("evidence_digest"),
            "purpose": audit.get("purpose"),
            "input_contract_version": versions["input"],
            "output_contract_version": versions["output"],
            "policy_contract_version": versions["policy"],
            "provider_id": provider_id,
            "model_id": model_id,
            "audit_recorded_at": audit.get("recorded_at"),
            "persistence_schema_version": PERSISTENCE_SCHEMA_VERSION,
            "canonicalization_profile": CANONICALIZATION_PROFILE,
            "audit_payload": record.audit_bytes,
            "audit_digest": record.audit_digest,
            "output_payload": output_payload,
            "output_digest": output_digest,
        }

    @staticmethod
    def _conflicting_rows(
        connection: psycopg.Connection[Any], values: Mapping[str, Any]
    ) -> Sequence[Sequence[Any]]:
        columns = """
            analysis_audit_id::text, analysis_output_id::text, outcome,
            analysis_input_id::text, snapshot_id::text, evidence_digest, purpose,
            input_contract_version, output_contract_version,
            policy_contract_version, provider_id, model_id, audit_recorded_at,
            persistence_schema_version, canonicalization_profile, audit_payload,
            audit_digest, output_payload, output_digest
        """
        predicate = "analysis_audit_id = %(analysis_audit_id)s::uuid"
        if values["analysis_output_id"] is not None:
            predicate += " OR analysis_output_id = %(analysis_output_id)s::uuid"
        return connection.execute(
            f"SELECT {columns} FROM atlas_ai_persistence.persistence_records WHERE {predicate}",
            values,
        ).fetchall()

    @staticmethod
    def _matches(row: Sequence[Any], values: Mapping[str, Any]) -> bool:
        expected = tuple(
            values[key]
            for key in (
                "analysis_audit_id",
                "analysis_output_id",
                "outcome",
                "analysis_input_id",
                "snapshot_id",
                "evidence_digest",
                "purpose",
                "input_contract_version",
                "output_contract_version",
                "policy_contract_version",
                "provider_id",
                "model_id",
                "audit_recorded_at",
                "persistence_schema_version",
                "canonicalization_profile",
                "audit_payload",
                "audit_digest",
                "output_payload",
                "output_digest",
            )
        )
        normalized = tuple(
            item.isoformat(timespec="microseconds").replace("+00:00", "Z")
            if isinstance(item, datetime)
            else bytes(item)
            if isinstance(item, memoryview)
            else item
            for item in row
        )
        return normalized == expected

    @staticmethod
    def _digest(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def _raise_clean(error_type: type[Exception]) -> NoReturn:
        error = error_type()
        error.__cause__ = None
        error.__context__ = None
        raise error from None
