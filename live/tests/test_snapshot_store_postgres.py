"""Mandatory real-PostgreSQL Phase 17C certification.

Set SNAPSHOT_STORE_TEST_ADMIN_URL to a disposable database owned by an
administrative login. The test creates temporary login roles, runs the real
migration, certifies runtime privileges and repository behavior, then removes
all snapshot resources.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from pathlib import Path

import psycopg
import pytest
from atlas_snapshot import SnapshotRecordIdentity, project, serialize
from atlas_snapshot_api.conninfo import build_reader_conninfo
from atlas_snapshot_store import (
    PostgresSnapshotRepository,
    SnapshotCorruptionError,
    SnapshotIdempotencyConflictError,
    SnapshotListCursor,
    SnapshotNotFoundError,
    SnapshotStoreError,
    UnsupportedStoredSnapshotError,
)
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg_pool import AsyncConnectionPool
from snapshot_migrations import run_snapshot_migrations

ADMIN_URL = os.environ.get("SNAPSHOT_STORE_TEST_ADMIN_URL", "")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="mandatory certification requires SNAPSHOT_STORE_TEST_ADMIN_URL",
)
ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "specs" / "trader_now_snapshot" / "v1" / "golden"
TEMPLATE_ROLES = (
    "atlas_snapshot_admin",
    "atlas_snapshot_retention",
    "atlas_snapshot_writer",
    "atlas_snapshot_reader",
)


@pytest.fixture(scope="module")
def event_loop_policy():
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def _golden(name="complete-current-candidate.canonical.json"):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _transport(golden):
    return {
        "schema_version": golden["source"]["trader_now_response_schema_version"],
        "domain_schema_version": golden["source"][
            "trader_now_domain_schema_version"
        ],
        "snapshot_id": None,
        **golden["evidence"],
    }


def _payload(
    *,
    snapshot_id: str,
    created_at: str,
    golden_name="complete-current-candidate.canonical.json",
    supersedes_snapshot_id=None,
    mutate=None,
):
    golden = _golden(golden_name)
    source = _transport(golden)
    if mutate is not None:
        mutate(source)
    snapshot = project(
        source,
        SnapshotRecordIdentity(
            snapshot_id=snapshot_id,
            created_at=created_at,
            supersedes_snapshot_id=supersedes_snapshot_id,
        ),
    )
    return serialize(snapshot)


def _role_url(admin_url: str, username: str, password: str, template: str) -> str:
    values = conninfo_to_dict(admin_url)
    values.update(
        user=username,
        password=password,
        options=f"-c role={template}",
    )
    return make_conninfo(**values)


def _admin_execute(statement, parameters=None):
    with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
        connection.execute(statement, parameters)


@pytest.mark.asyncio
async def test_real_postgres_snapshot_store_certification():
    suffix = secrets.token_hex(6)
    writer_login = f"snapshot_cert_writer_{suffix}"
    reader_login = f"snapshot_cert_reader_{suffix}"
    writer_password = secrets.token_urlsafe(32)
    reader_password = secrets.token_urlsafe(32)
    preexisting_roles: set[str] = set()
    writer_pool = None
    reader_pool = None

    with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
        preexisting_roles = {
            row[0]
            for row in connection.execute(
                "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
                (list(TEMPLATE_ROLES),),
            ).fetchall()
        }

    try:
        run_snapshot_migrations(ADMIN_URL)
        # Re-running proves the migration ledger is idempotent.
        run_snapshot_migrations(ADMIN_URL)

        with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
            current_user = connection.execute("SELECT current_user").fetchone()[0]
            connection.execute(
                sql.SQL("GRANT atlas_snapshot_admin TO {}").format(
                    sql.Identifier(current_user)
                )
            )
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(
                    sql.Identifier(writer_login), sql.Literal(writer_password)
                )
            )
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOINHERIT PASSWORD {}").format(
                    sql.Identifier(reader_login), sql.Literal(reader_password)
                )
            )
            connection.execute(
                sql.SQL("GRANT atlas_snapshot_writer TO {}").format(
                    sql.Identifier(writer_login)
                )
            )
            connection.execute(
                sql.SQL("GRANT atlas_snapshot_reader TO {}").format(
                    sql.Identifier(reader_login)
                )
            )
            role_rows = connection.execute(
                """
                SELECT
                    rolname,
                    rolcanlogin,
                    rolinherit,
                    rolsuper,
                    rolcreatedb,
                    rolcreaterole,
                    rolreplication,
                    rolbypassrls
                FROM pg_roles
                WHERE rolname = ANY(%s)
                ORDER BY rolname
                """,
                (list(TEMPLATE_ROLES),),
            ).fetchall()
            assert role_rows == [
                (role, False, False, False, False, False, False, False)
                for role in sorted(TEMPLATE_ROLES)
            ]
            privilege_rows = connection.execute(
                """
                SELECT
                    role_name,
                    has_table_privilege(
                        role_name, 'atlas_snapshot.snapshots', 'SELECT'
                    ),
                    has_table_privilege(
                        role_name, 'atlas_snapshot.snapshots', 'INSERT'
                    ),
                    has_table_privilege(
                        role_name, 'atlas_snapshot.snapshots', 'UPDATE'
                    ),
                    has_table_privilege(
                        role_name, 'atlas_snapshot.snapshots', 'DELETE'
                    ),
                    has_table_privilege(
                        role_name, 'atlas_snapshot.snapshots', 'TRUNCATE'
                    )
                FROM unnest(%s::text[]) AS role_name
                ORDER BY role_name
                """,
                (
                    [
                        "atlas_snapshot_reader",
                        "atlas_snapshot_retention",
                        "atlas_snapshot_writer",
                    ],
                ),
            ).fetchall()
            assert privilege_rows == [
                ("atlas_snapshot_reader", True, False, False, False, False),
                ("atlas_snapshot_retention", True, False, False, True, False),
                ("atlas_snapshot_writer", True, True, False, False, False),
            ]

        writer_pool = AsyncConnectionPool(
            _role_url(
                ADMIN_URL,
                writer_login,
                writer_password,
                "atlas_snapshot_writer",
            ),
            min_size=1,
            max_size=4,
            open=False,
        )
        reader_pool = AsyncConnectionPool(
            build_reader_conninfo(
                _role_url(
                    ADMIN_URL,
                    reader_login,
                    reader_password,
                    "atlas_snapshot_reader",
                )
            ),
            min_size=1,
            max_size=2,
            open=False,
        )
        await writer_pool.open(wait=True, timeout=30)
        await reader_pool.open(wait=True, timeout=30)
        writer = PostgresSnapshotRepository(writer_pool)
        reader = PostgresSnapshotRepository(reader_pool)

        first_payload = _payload(
            snapshot_id="019849d1-8c00-7000-8000-000000000101",
            created_at="2026-07-25T13:00:01.000000Z",
        )
        inserted = await writer.append(first_payload)
        assert inserted.created is True
        assert inserted.metadata.economic_instrument == "MNQ"

        duplicate = await writer.append(first_payload)
        assert duplicate.created is False
        assert duplicate.metadata == inserted.metadata

        by_id = await reader.get_by_snapshot_id(inserted.metadata.snapshot_id)
        by_digest = await reader.get_by_evidence_digest(
            inserted.metadata.evidence_digest
        )
        assert serialize(by_id) == first_payload
        assert serialize(by_digest) == first_payload

        with psycopg.connect(ADMIN_URL) as connection:
            row = connection.execute(
                """
                SELECT canonical_payload, economic_instrument, timeframe
                FROM atlas_snapshot.snapshots
                WHERE snapshot_id = %s
                """,
                (inserted.metadata.snapshot_id,),
            ).fetchone()
        assert bytes(row[0]) == first_payload
        assert row[1:] == ("MNQ", "5m")

        def change_fact(source):
            source["rules"]["facts"][0]["value"] = False

        conflicting_payload = _payload(
            snapshot_id="019849d1-8c00-7000-8000-000000000102",
            created_at="2026-07-25T13:00:01.000000Z",
            mutate=change_fact,
        )
        with pytest.raises(SnapshotIdempotencyConflictError):
            await writer.append(conflicting_payload)

        concurrent_payload = _payload(
            snapshot_id="019849d1-8c00-7000-8000-000000000103",
            created_at="2026-07-25T13:01:01.000000Z",
            golden_name="delayed-insufficient-rejected.canonical.json",
        )
        concurrent = await asyncio.gather(
            writer.append(concurrent_payload),
            writer.append(concurrent_payload),
        )
        assert sorted(item.created for item in concurrent) == [False, True]

        correction_payload = _payload(
            snapshot_id="019849d1-8c00-7000-8000-000000000104",
            created_at="2026-07-25T13:02:01.000000Z",
            golden_name="stale-unavailable-no-signal-with-risk.canonical.json",
            supersedes_snapshot_id=inserted.metadata.snapshot_id,
        )
        correction = await writer.append(correction_payload)
        assert correction.metadata.supersedes_snapshot_id == (
            inserted.metadata.snapshot_id
        )

        page1 = await reader.list_metadata(limit=2)
        assert len(page1.items) == 2
        assert page1.next_cursor is not None
        assert isinstance(page1.next_cursor, SnapshotListCursor)
        page2 = await reader.list_metadata(limit=2, cursor=page1.next_cursor)
        assert page2.items
        assert {item.snapshot_id for item in page1.items}.isdisjoint(
            item.snapshot_id for item in page2.items
        )
        with pytest.raises(ValueError):
            await reader.list_metadata(limit=201)

        invalid_supersession = _payload(
            snapshot_id="019849d1-8c00-7000-8000-000000000105",
            created_at="2026-07-25T13:03:01.000000Z",
            golden_name="no-data.canonical.json",
            supersedes_snapshot_id="019849d1-8c00-7000-8000-999999999999",
        )
        with pytest.raises(SnapshotStoreError, match="transaction failed"):
            await writer.append(invalid_supersession)
        with pytest.raises(SnapshotNotFoundError):
            await reader.get_by_snapshot_id(
                "019849d1-8c00-7000-8000-000000000105"
            )

        async with writer_pool.connection() as connection:
            audit = await connection.execute(
                """
                SELECT
                    current_user,
                    has_schema_privilege(current_user, 'atlas_snapshot', 'USAGE'),
                    has_schema_privilege(current_user, 'atlas_snapshot', 'CREATE'),
                    has_table_privilege(
                        current_user, 'atlas_snapshot.snapshots', 'SELECT'
                    ),
                    has_table_privilege(
                        current_user, 'atlas_snapshot.snapshots', 'INSERT'
                    ),
                    has_table_privilege(
                        current_user, 'atlas_snapshot.snapshots', 'UPDATE'
                    ),
                    has_table_privilege(
                        current_user, 'atlas_snapshot.snapshots', 'DELETE'
                    ),
                    has_table_privilege(
                        current_user, 'atlas_snapshot.snapshots', 'TRUNCATE'
                    )
                """
            )
            assert await audit.fetchone() == (
                "atlas_snapshot_writer",
                True,
                False,
                True,
                True,
                False,
                False,
                False,
            )
            for statement in (
                "UPDATE atlas_snapshot.snapshots SET trust_status = trust_status",
                "DELETE FROM atlas_snapshot.snapshots",
                "TRUNCATE atlas_snapshot.snapshots",
                "ALTER TABLE atlas_snapshot.snapshots ADD COLUMN forbidden int",
                "CREATE TABLE atlas_snapshot.forbidden (id int)",
            ):
                with pytest.raises(psycopg.Error):
                    await connection.execute(statement)
                await connection.rollback()

        async with reader_pool.connection() as connection:
            role = await connection.execute("SELECT current_user")
            assert await role.fetchone() == ("atlas_snapshot_reader",)
            read_only = await connection.execute("SHOW transaction_read_only")
            assert await read_only.fetchone() == ("on",)
            for statement in (
                "INSERT INTO atlas_snapshot.snapshots DEFAULT VALUES",
                "UPDATE atlas_snapshot.snapshots SET trust_status = trust_status",
                "DELETE FROM atlas_snapshot.snapshots",
                "ALTER TABLE atlas_snapshot.snapshots ADD COLUMN forbidden int",
                "CREATE TABLE atlas_snapshot.forbidden (id int)",
            ):
                with pytest.raises(psycopg.Error):
                    await connection.execute(statement)
                await connection.rollback()

        # Administrative corruption simulation proves fail-closed quarantine.
        with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
            connection.execute("SET ROLE atlas_snapshot_admin")
            with pytest.raises(psycopg.Error, match="immutable"):
                connection.execute(
                    """
                    UPDATE atlas_snapshot.snapshots
                    SET trust_status = trust_status
                    WHERE snapshot_id = %s
                    """,
                    (correction.metadata.snapshot_id,),
                )
            connection.execute(
                "ALTER TABLE atlas_snapshot.snapshots DISABLE TRIGGER snapshots_reject_update"
            )
            connection.execute(
                """
                UPDATE atlas_snapshot.snapshots
                SET economic_instrument = 'CORRUPTED'
                WHERE snapshot_id = %s
                """,
                (correction.metadata.snapshot_id,),
            )
            connection.execute(
                "ALTER TABLE atlas_snapshot.snapshots ENABLE TRIGGER snapshots_reject_update"
            )
            connection.execute("RESET ROLE")
        with pytest.raises(SnapshotCorruptionError, match="metadata disagrees"):
            await reader.get_by_snapshot_id(correction.metadata.snapshot_id)

        with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
            connection.execute("SET ROLE atlas_snapshot_admin")
            connection.execute(
                "ALTER TABLE atlas_snapshot.snapshots DISABLE TRIGGER snapshots_reject_update"
            )
            connection.execute(
                """
                UPDATE atlas_snapshot.snapshots
                SET canonical_payload = canonical_payload || %s
                WHERE snapshot_id = %s
                """,
                (b"x", concurrent[0].metadata.snapshot_id),
            )
            connection.execute(
                "ALTER TABLE atlas_snapshot.snapshots ENABLE TRIGGER snapshots_reject_update"
            )
            connection.execute("RESET ROLE")
        with pytest.raises(SnapshotCorruptionError, match="canonical payload"):
            await reader.get_by_snapshot_id(concurrent[0].metadata.snapshot_id)

        with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
            connection.execute("SET ROLE atlas_snapshot_admin")
            connection.execute(
                "ALTER TABLE atlas_snapshot.snapshots DISABLE TRIGGER snapshots_reject_update"
            )
            connection.execute(
                """
                ALTER TABLE atlas_snapshot.snapshots
                DROP CONSTRAINT snapshots_snapshot_schema_version_check
                """
            )
            connection.execute(
                """
                UPDATE atlas_snapshot.snapshots
                SET snapshot_schema_version = 'trader_now_snapshot.v99'
                WHERE snapshot_id = %s
                """,
                (inserted.metadata.snapshot_id,),
            )
            connection.execute(
                "ALTER TABLE atlas_snapshot.snapshots ENABLE TRIGGER snapshots_reject_update"
            )
            connection.execute("RESET ROLE")
        with pytest.raises(UnsupportedStoredSnapshotError):
            await reader.get_by_snapshot_id(inserted.metadata.snapshot_id)

    finally:
        if writer_pool is not None:
            await writer_pool.close()
            assert writer_pool.closed
        if reader_pool is not None:
            await reader_pool.close()
            assert reader_pool.closed
        with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
            current_user = connection.execute("SELECT current_user").fetchone()[0]
            connection.execute("DROP SCHEMA IF EXISTS atlas_snapshot CASCADE")
            connection.execute(
                "DROP TABLE IF EXISTS public.atlas_snapshot_schema_migrations"
            )
            for login in (writer_login, reader_login):
                connection.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(login))
                )
            connection.execute(
                sql.SQL("REVOKE atlas_snapshot_admin FROM {}").format(
                    sql.Identifier(current_user)
                )
            )
            for role in reversed(TEMPLATE_ROLES):
                if role not in preexisting_roles:
                    connection.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(
                            sql.Identifier(role)
                        )
                    )
