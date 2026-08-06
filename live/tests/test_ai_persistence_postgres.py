"""Ordinary disposable PostgreSQL 17 qualification for Phase 18G."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from ai_persistence_migrations import run_ai_persistence_migrations
from atlas_ai_persistence import PersistenceConflictError, PersistenceCoordinator
from atlas_ai_persistence_postgres import PostgresAtomicPersistenceAdapter
from tests.test_ai_persistence import _completed, _failed, _refused

ADMIN_URL = os.environ.get("PHASE18G_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="isolated Phase 18G PostgreSQL URL required"
)
WRITER = "phase18g_test_writer"
PASSWORD = "phase18g-test-only-password"


def _writer_url() -> str:
    values = conninfo_to_dict(ADMIN_URL)
    values.update(user=WRITER, password=PASSWORD)
    return make_conninfo(**values)


@pytest.fixture(scope="module", autouse=True)
def database():
    run_ai_persistence_migrations(ADMIN_URL)
    run_ai_persistence_migrations(ADMIN_URL)
    with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(WRITER))
        )
        connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(WRITER), sql.Literal(PASSWORD)
            )
        )
        connection.execute(
            sql.SQL("GRANT atlas_ai_persistence_writer TO {}").format(
                sql.Identifier(WRITER)
            )
        )
    yield


@pytest.fixture(autouse=True)
def clean_records():
    with psycopg.connect(ADMIN_URL) as connection:
        connection.execute("TRUNCATE atlas_ai_persistence.persistence_records")


def _adapter() -> PostgresAtomicPersistenceAdapter:
    return PostgresAtomicPersistenceAdapter(lambda: psycopg.connect(_writer_url()))


def _count() -> int:
    with psycopg.connect(ADMIN_URL) as connection:
        return connection.execute(
            "SELECT count(*) FROM atlas_ai_persistence.persistence_records"
        ).fetchone()[0]


def test_postgresql_17_and_checksum_bound_migration() -> None:
    with psycopg.connect(ADMIN_URL) as connection:
        version = connection.execute("SHOW server_version").fetchone()[0]
        rows = connection.execute(
            "SELECT filename, sha256 FROM public.atlas_ai_persistence_schema_migrations"
        ).fetchall()
    assert version.startswith("17.10")
    assert len(rows) == 1
    assert len(rows[0][1]) == 64


def test_unexpected_or_changed_migration_state_fails_closed() -> None:
    with psycopg.connect(ADMIN_URL) as connection:
        filename, checksum = connection.execute(
            "SELECT filename, sha256 FROM public.atlas_ai_persistence_schema_migrations"
        ).fetchone()
        connection.execute(
            "UPDATE public.atlas_ai_persistence_schema_migrations SET sha256 = %s WHERE filename = %s",
            ("0" * 64, filename),
        )
    try:
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            run_ai_persistence_migrations(ADMIN_URL)
    finally:
        with psycopg.connect(ADMIN_URL) as connection:
            connection.execute(
                "UPDATE public.atlas_ai_persistence_schema_migrations SET sha256 = %s WHERE filename = %s",
                (checksum, filename),
            )


@pytest.mark.parametrize(
    "factory,outcome",
    [(_completed, "completed"), (_failed, "failed"), (_refused, "refused")],
)
def test_canonical_bytes_digests_and_shapes_round_trip(factory, outcome) -> None:
    capture = []

    class Port:
        def store_atomic(self, record):
            capture.append(record)
            return _adapter().store_atomic(record)

    result = PersistenceCoordinator(Port()).persist(factory())
    assert result.receipt.disposition == "committed"
    record = capture[0]
    with psycopg.connect(ADMIN_URL) as connection:
        row = connection.execute(
            "SELECT outcome, audit_payload, audit_digest, output_payload, output_digest FROM atlas_ai_persistence.persistence_records"
        ).fetchone()
    assert row[0] == outcome
    assert bytes(row[1]) == record.audit_bytes
    assert row[2] == record.audit_digest
    if outcome == "completed":
        assert bytes(row[3]) == record.output_bytes
        assert row[4] == record.output_digest
    else:
        assert row[3:] == (None, None)


def test_exact_replay_and_identity_collisions() -> None:
    coordinator = PersistenceCoordinator(_adapter())
    outcome = _completed()
    assert coordinator.persist(outcome).receipt.disposition == "committed"
    assert coordinator.persist(outcome).receipt.disposition == "replayed"
    assert _count() == 1
    with pytest.raises(PersistenceConflictError):
        coordinator.persist(_completed(audit_id="019c1234-0000-7000-8000-000000000099"))
    assert _count() == 1


def test_bounded_concurrent_identical_and_conflicting_writes() -> None:
    outcome = _completed()
    coordinator = PersistenceCoordinator(_adapter())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(coordinator.persist, [outcome] * 4))
    assert sorted(item.receipt.disposition for item in results) == [
        "committed",
        "replayed",
        "replayed",
        "replayed",
    ]
    assert _count() == 1

    with psycopg.connect(ADMIN_URL) as connection:
        connection.execute("TRUNCATE atlas_ai_persistence.persistence_records")
    conflicting = _completed(audit_id="019c1234-0000-7000-8000-000000000099")
    outcomes = [outcome, conflicting]
    successes = conflicts = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(coordinator.persist, item) for item in outcomes]
        for future in futures:
            try:
                future.result()
                successes += 1
            except PersistenceConflictError:
                conflicts += 1
    assert (successes, conflicts) == (1, 1)
    assert _count() == 1


def test_runtime_privileges_are_insert_only_and_records_are_immutable() -> None:
    PersistenceCoordinator(_adapter()).persist(_completed())
    with psycopg.connect(_writer_url()) as connection:
        with pytest.raises(psycopg.Error):
            connection.execute(
                "UPDATE atlas_ai_persistence.persistence_records SET purpose = purpose"
            )
        connection.rollback()
        with pytest.raises(psycopg.Error):
            connection.execute("DELETE FROM atlas_ai_persistence.persistence_records")
        connection.rollback()
        with pytest.raises(psycopg.Error):
            connection.execute(
                "CREATE TABLE atlas_ai_persistence.forbidden (id integer)"
            )
    assert _count() == 1


def test_constraint_failure_leaves_no_partial_row() -> None:
    with psycopg.connect(ADMIN_URL) as connection, pytest.raises(psycopg.Error):
        connection.execute(
            "INSERT INTO atlas_ai_persistence.persistence_records (analysis_audit_id, outcome) VALUES (%s, 'completed')",
            ("019c1234-0000-7000-8000-000000000099",),
        )
    assert _count() == 0
