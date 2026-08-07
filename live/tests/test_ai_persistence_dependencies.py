"""Static isolation checks for the offline Phase 18F production package."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "atlas_ai_persistence"


def test_production_package_has_no_operational_dependencies_or_fake() -> None:
    prohibited = {
        "asyncpg",
        "django",
        "fastapi",
        "flask",
        "httpx",
        "openai",
        "psycopg",
        "railway",
        "requests",
        "sqlalchemy",
    }
    for path in PACKAGE.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert imports.isdisjoint(prohibited)
        assert "TransactionalFake" not in source
        assert "retry" not in source.lower()


def test_no_runtime_module_imports_phase18f_package() -> None:
    runtime_files = [ROOT / "main.py", *ROOT.glob("**/routes*.py")]
    for path in runtime_files:
        if path.is_file():
            assert "atlas_ai_persistence" not in path.read_text(encoding="utf-8")
