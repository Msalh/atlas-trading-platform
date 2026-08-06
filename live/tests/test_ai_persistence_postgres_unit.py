"""Offline unit qualification for the Phase 18G PostgreSQL adapter."""

from __future__ import annotations

from contextlib import nullcontext

import pytest
from psycopg import OperationalError

from atlas_ai_persistence import (
    PersistenceCoordinator,
    PersistenceIntegrityError,
    PersistenceReceipt,
    PersistenceUnavailableError,
)
from atlas_ai_persistence_postgres import PostgresAtomicPersistenceAdapter
from tests.test_ai_persistence import _completed, _failed, _refused


class _Capture:
    def __init__(self) -> None:
        self.record = None

    def store_atomic(self, record):
        self.record = record
        return PersistenceReceipt(record.operation_id, "committed")


def _record(factory):
    port = _Capture()
    PersistenceCoordinator(port).persist(factory())
    assert port.record is not None
    return port.record


@pytest.mark.parametrize(
    "factory,outcome",
    [(_completed, "completed"), (_failed, "failed"), (_refused, "refused")],
)
def test_record_mapping_preserves_only_approved_canonical_fields(
    factory, outcome
) -> None:
    record = _record(factory)
    values = PostgresAtomicPersistenceAdapter._values(record)
    assert values["outcome"] == outcome
    assert values["audit_payload"] == record.audit_bytes
    assert values["audit_digest"] == record.audit_digest
    assert "prompt" not in values
    assert "evidence" not in values
    assert "credential" not in values
    if outcome == "completed":
        assert values["output_payload"] == record.output_bytes
        assert values["output_digest"] == record.output_digest
    else:
        assert values["output_payload"] is None
        assert values["output_digest"] is None


def test_comparison_only_digest_check_fails_before_connection() -> None:
    record = _record(_completed)
    object.__setattr__(record, "audit_digest", "0" * 64)
    calls = 0

    def connection_factory():
        nonlocal calls
        calls += 1
        raise AssertionError

    with pytest.raises(PersistenceIntegrityError) as caught:
        PostgresAtomicPersistenceAdapter(connection_factory).store_atomic(record)
    assert calls == 0
    assert caught.value.__cause__ is caught.value.__context__ is None


def test_unsupported_contract_version_fails_before_connection() -> None:
    record = _record(_completed)
    values = dict(record.audit)
    values["contract_versions"] = {
        "input": "unsupported",
        "output": "ai_analysis_output.v1",
        "policy": "ai_analysis_policy.v1",
    }
    object.__setattr__(record, "audit", values)
    with pytest.raises(PersistenceIntegrityError):
        PostgresAtomicPersistenceAdapter(
            lambda: pytest.fail("connection opened")
        ).store_atomic(record)


class _FailingConnection:
    closed = False

    def transaction(self):
        return nullcontext()

    def execute(self, statement, parameters=None):
        raise OperationalError("postgresql://secret-user:secret@secret-host/db")

    def close(self):
        self.closed = True


def test_database_failure_is_sanitized_and_not_retried() -> None:
    connection = _FailingConnection()
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return connection

    with pytest.raises(PersistenceUnavailableError) as caught:
        PostgresAtomicPersistenceAdapter(factory).store_atomic(_record(_completed))
    assert calls == 1
    assert connection.closed
    assert caught.value.__cause__ is caught.value.__context__ is None
    assert "secret" not in repr(caught.value)
