"""Phase 18D dependency, authority, and purity boundary."""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "atlas_ai_orchestration"
ADAPTER = PACKAGE / "openai_adapter.py"
CORE_FILES = tuple(path for path in PACKAGE.glob("*.py") if path != ADAPTER)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_orchestration_has_only_frozen_and_standard_library_dependencies():
    forbidden = (
        "fastapi",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "subprocess",
        "psycopg",
        "sqlalchemy",
        "openai",
        "anthropic",
        "atlas.api",
        "atlas.application",
        "atlas.repositories",
        "atlas.services",
        "atlas.execution",
        "atlas.broker",
        "atlas_snapshot",
        "atlas_snapshot_api",
        "atlas_snapshot_capture",
        "atlas_snapshot_store",
    )
    for path in CORE_FILES:
        assert not any(
            name == prefix or name.startswith(f"{prefix}.")
            for name in _imports(path)
            for prefix in forbidden
        ), path.name


def test_orchestration_contains_no_concrete_io_persistence_or_execution_capability():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in CORE_FILES
    ).lower()
    for forbidden in (
        "http://",
        "https://",
        "database_url",
        "api_key",
        "authorization",
        "bearer ",
        "requests.",
        "socket.",
        "subprocess.",
        "openai.",
        "anthropic.",
        "place_order",
        "execute_order",
        "send_order",
        "railway",
        "postgres",
        "insert into",
        "update ",
        "delete from",
    ):
        assert forbidden not in source, forbidden


def test_orchestration_does_not_duplicate_frozen_authority():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in CORE_FILES
    )
    for forbidden in (
        "atlas_snapshot.digest",
        "atlas_snapshot.verify",
        "project_input(",
        "resolve_citation(",
        "resolve_evidence(",
        "sha256(",
        "datetime.now(",
        "uuid.uuid",
    ):
        assert forbidden not in source, forbidden


def test_no_runtime_package_imports_phase18d_before_a_later_integration_phase():
    runtime_roots = (
        ROOT / "atlas" / "api",
        ROOT / "atlas" / "application",
        ROOT / "atlas" / "services",
        ROOT / "atlas" / "repositories",
    )
    for root in runtime_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            assert not any(
                name == "atlas_ai_orchestration"
                or name.startswith("atlas_ai_orchestration.")
                for name in _imports(path)
            ), path.name


def test_phase18e_adapter_has_only_approved_transport_and_internal_dependencies():
    imports = _imports(ADAPTER)
    allowed = {
        "__future__",
        "atlas_ai_analysis",
        "collections.abc",
        "dataclasses",
        "datetime",
        "errors",
        "httpx",
        "json",
        "math",
        "models",
        "time",
        "typing",
    }
    assert set(imports) <= allowed
    assert "httpx" in imports


def test_no_production_runtime_imports_or_binds_phase18e_adapter():
    runtime_roots = (
        ROOT / "atlas" / "main.py",
        ROOT / "atlas" / "api",
        ROOT / "atlas" / "application",
        ROOT / "atlas" / "services",
        ROOT / "atlas" / "repositories",
    )
    paths = []
    for root in runtime_roots:
        paths.extend([root] if root.is_file() else root.rglob("*.py"))
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "openai_adapter" not in source, path
        assert "OpenAIProviderAdapter" not in source, path
        assert "ATLAS_AI_PROVIDER_" not in source, path
