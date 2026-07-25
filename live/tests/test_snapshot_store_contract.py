"""Phase 17C storage-neutral repository and migration contract tests."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from atlas_snapshot_store import SnapshotRepository
from atlas_snapshot_store.postgres import PostgresSnapshotRepository

ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "snapshot_migrations" / "0001_snapshot_store.sql"


def test_repository_public_interface_is_narrow_and_append_only():
    names = {
        name
        for name, value in inspect.getmembers(SnapshotRepository)
        if inspect.isfunction(value) and not name.startswith("_")
    }
    assert names == {
        "append",
        "get_by_snapshot_id",
        "get_by_evidence_digest",
        "list_metadata",
    }


def test_postgres_adapter_exposes_no_mutation_or_migration_method():
    public = {
        name
        for name, value in inspect.getmembers(PostgresSnapshotRepository)
        if inspect.isfunction(value) and not name.startswith("_")
    }
    assert public == {
        "append",
        "get_by_snapshot_id",
        "get_by_evidence_digest",
        "list_metadata",
    }
    assert public.isdisjoint({"update", "delete", "repair", "migrate", "quarantine"})


def test_schema_has_exactly_one_authoritative_payload_and_no_json_copy():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert sql.count("canonical_payload bytea") == 1
    assert " json " not in sql
    assert " jsonb" not in sql
    assert "payload_copy" not in sql
    assert "canonical_json" not in sql


def test_schema_defines_separate_runtime_retention_and_admin_roles():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for role in (
        "atlas_snapshot_writer",
        "atlas_snapshot_reader",
        "atlas_snapshot_retention",
        "atlas_snapshot_admin",
    ):
        assert f"create role {role} nologin noinherit" in sql
    assert "grant select, insert on atlas_snapshot.snapshots to atlas_snapshot_writer" in sql
    assert "grant select on atlas_snapshot.snapshots to atlas_snapshot_reader" in sql
    assert (
        "grant select, delete on atlas_snapshot.snapshots to atlas_snapshot_retention"
        in sql
    )
    assert "revoke all on schema atlas_snapshot from public" in sql


def test_schema_enforces_immutability_and_supersession():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "before update on atlas_snapshot.snapshots" in sql
    assert "corrections require a new snapshot" in sql
    assert "supersedes_snapshot_id uuid references atlas_snapshot.snapshots" in sql
    assert "on update restrict on delete restrict" in sql


def test_store_packages_do_not_depend_on_trader_now_capture_api_ai_or_railway():
    package = ROOT / "atlas_snapshot_store"
    forbidden_imports = {
        "atlas",
        "fastapi",
        "httpx",
        "anthropic",
        "openai",
    }
    forbidden_terms = {"railway", "capture_service"}

    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        assert imports.isdisjoint(forbidden_imports), path.name
        assert not any(term in source.lower() for term in forbidden_terms), path.name
