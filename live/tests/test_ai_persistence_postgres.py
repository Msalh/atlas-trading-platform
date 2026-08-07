"""Ordinary disposable PostgreSQL 17 qualification for Phase 18G."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import atlas.main as main_module
from ai_persistence_migrations import (
    expected_ai_persistence_migrations,
    run_ai_persistence_migrations,
)
from atlas.ai_persistence_runtime import (
    AIPersistenceStartupError,
    build_ai_persistence_runtime,
)
from atlas_ai_persistence import PersistenceConflictError, PersistenceCoordinator
from atlas_ai_persistence_postgres import PostgresAtomicPersistenceAdapter
from tests.test_ai_persistence import _completed, _failed, _refused

ADMIN_URL = os.environ.get("PHASE18G_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="isolated Phase 18G PostgreSQL URL required"
)
WRITER = "phase18g_test_writer"
PASSWORD = "phase18g-test-only-password"
LIMITED_WRITER = "phase18h_limited_writer"
LIMITED_PASSWORD = "phase18h-limited-only"
MIGRATIONS = Path(__file__).parents[1] / "ai_persistence_migrations"


def _writer_url() -> str:
    values = conninfo_to_dict(ADMIN_URL)
    values.update(user=WRITER, password=PASSWORD)
    return make_conninfo(**values)


def _runtime_settings(url: str | None = None):
    return SimpleNamespace(
        atlas_ai_persistence_mode="required",
        atlas_ai_persistence_database_url=url or _writer_url(),
        atlas_ai_persistence_connect_timeout_seconds="2",
        atlas_ai_persistence_pool_min_size="1",
        atlas_ai_persistence_pool_max_size="2",
        atlas_ai_persistence_pool_acquisition_timeout_seconds="2",
        atlas_ai_persistence_local_disposable_test="true",
        environment="development",
    )


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
            sql.SQL(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {}) "
                "THEN CREATE ROLE {} LOGIN PASSWORD {}; END IF; END $$"
            ).format(
                sql.Literal(LIMITED_WRITER),
                sql.Identifier(LIMITED_WRITER),
                sql.Literal(LIMITED_PASSWORD),
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
    assert dict(rows) == expected_ai_persistence_migrations()


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


def test_phase18g_baseline_upgrade_grants_only_narrow_ledger_columns() -> None:
    migration = MIGRATIONS / "0002_runtime_schema_verification.sql"
    with psycopg.connect(ADMIN_URL) as connection:
        connection.execute(
            "REVOKE SELECT (filename, sha256) ON public.atlas_ai_persistence_schema_migrations FROM atlas_ai_persistence_writer"
        )
        assert connection.execute(
            "SELECT has_column_privilege('atlas_ai_persistence_writer', 'public.atlas_ai_persistence_schema_migrations', 'filename', 'SELECT')"
        ).fetchone()[0] is False
        connection.execute(migration.read_text(encoding="utf-8"))
        assert connection.execute(
            "SELECT has_column_privilege('atlas_ai_persistence_writer', 'public.atlas_ai_persistence_schema_migrations', 'filename', 'SELECT')"
        ).fetchone()[0] is True
        assert connection.execute(
            "SELECT has_table_privilege('atlas_ai_persistence_writer', 'public.atlas_ai_persistence_schema_migrations', 'INSERT')"
        ).fetchone()[0] is False
        connection.rollback()


def test_required_runtime_startup_readiness_and_shutdown_commit_no_probe() -> None:
    assert _count() == 0
    runtime = build_ai_persistence_runtime(_runtime_settings())
    assert runtime.public_state() == {"status": "ready", "required": True}
    assert runtime.coordinator is not None
    assert runtime.refresh_readiness() == "ready"
    assert _count() == 0
    runtime.close()
    runtime.close()
    assert runtime.state == "shutdown"
    assert _count() == 0


def test_required_runtime_fails_closed_on_checksum_mismatch() -> None:
    with psycopg.connect(ADMIN_URL) as connection:
        filename, checksum = connection.execute(
            "SELECT filename, sha256 FROM public.atlas_ai_persistence_schema_migrations ORDER BY filename LIMIT 1"
        ).fetchone()
        connection.execute(
            "UPDATE public.atlas_ai_persistence_schema_migrations SET sha256 = %s WHERE filename = %s",
            ("0" * 64, filename),
        )
    try:
        with pytest.raises(AIPersistenceStartupError) as caught:
            build_ai_persistence_runtime(_runtime_settings())
        assert caught.value.classification == "schema_mismatch"
        assert caught.value.__cause__ is caught.value.__context__ is None
    finally:
        with psycopg.connect(ADMIN_URL) as connection:
            connection.execute(
                "UPDATE public.atlas_ai_persistence_schema_migrations SET sha256 = %s WHERE filename = %s",
                (checksum, filename),
            )


def test_required_runtime_fails_closed_on_missing_or_excess_privilege() -> None:
    values = conninfo_to_dict(ADMIN_URL)
    limited_url = make_conninfo(
        **{**values, "user": LIMITED_WRITER, "password": LIMITED_PASSWORD}
    )
    with pytest.raises(AIPersistenceStartupError) as missing:
        build_ai_persistence_runtime(_runtime_settings(limited_url))
    assert missing.value.classification == "privilege_invalid"

    with pytest.raises(AIPersistenceStartupError) as excess:
        build_ai_persistence_runtime(_runtime_settings(ADMIN_URL))
    assert excess.value.classification == "privilege_invalid"


def test_required_runtime_unavailable_and_post_start_loss_are_sanitized(caplog) -> None:
    values = conninfo_to_dict(_writer_url())
    unavailable_url = make_conninfo(**{**values, "port": "1", "connect_timeout": "1"})
    with pytest.raises(AIPersistenceStartupError) as unavailable:
        build_ai_persistence_runtime(_runtime_settings(unavailable_url))
    assert unavailable.value.classification == "unavailable"
    assert unavailable.value.__cause__ is unavailable.value.__context__ is None
    assert "phase18g-test-only-password" not in caplog.text
    assert "127.0.0.1" not in caplog.text
    assert "localhost" not in caplog.text
    assert "port 1" not in caplog.text
    assert "connection refused" not in caplog.text
    assert "postgres_pool_event" in caplog.text

    runtime = build_ai_persistence_runtime(_runtime_settings())
    runtime._pool.close()
    assert runtime.refresh_readiness() == "unavailable"
    assert _count() == 0
    runtime.close()
    restored = build_ai_persistence_runtime(_runtime_settings())
    assert restored.state == "ready"
    assert _count() == 0
    restored.close()


async def test_application_lifespan_required_mode_uses_verified_runtime_without_probe_record(
    monkeypatch, tmp_path
) -> None:
    class ApplicationPool:
        close_calls = 0

        async def close(self):
            self.close_calls += 1

    application_pool = ApplicationPool()

    async def create_pool():
        return application_pool

    monkeypatch.setattr(main_module, "create_pool", create_pool)
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(
        main_module.settings, "research_ledger_dir", str(tmp_path / "research")
    )
    for name in (
        "trader_now_product",
        "trader_now_market_data_provider",
        "trader_now_market_data_series_symbol",
        "trader_now_market_data_series_type",
        "trader_now_series_resolution_version",
        "trader_now_series_effective_date",
        "trader_now_calendar_version",
        "trader_now_holidays_json",
        "trader_now_early_closes_json",
    ):
        monkeypatch.setattr(main_module.settings, name, "")
    for name, value in vars(_runtime_settings()).items():
        monkeypatch.setattr(main_module.settings, name, value)
    try:
        async with main_module.lifespan(main_module.app):
            runtime = main_module.app.state.ai_persistence_runtime
            assert runtime.state == "ready"
            assert runtime.coordinator is not None
            assert _count() == 0
        assert runtime.state == "shutdown"
        assert application_pool.close_calls == 1
        assert _count() == 0
    finally:
        for name in ("ai_persistence_runtime", "started_at"):
            if hasattr(main_module.app.state, name):
                delattr(main_module.app.state, name)


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
