"""Dependency direction checks for the read-only risk projection package."""

import ast
from pathlib import Path

_ATLAS = Path(__file__).resolve().parent.parent / "atlas"
_PROJECTION = _ATLAS / "risk_projection"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_projection_depends_only_on_risk_assessment_and_itself():
    for path in _PROJECTION.glob("*.py"):
        assert all(
            imported.startswith(("atlas.risk_assessment", "atlas.risk_projection"))
            for imported in _imports(path)
            if imported.startswith("atlas.")
        ), f"{path.name} has a forbidden dependency"


def test_risk_assessment_does_not_depend_on_projection_or_trader_now():
    for path in (_ATLAS / "risk_assessment").glob("*.py"):
        imports = _imports(path)
        assert "atlas.risk_projection" not in imports
        assert "atlas.trader_now" not in imports


def test_projection_has_no_api_persistence_or_framework_dependencies():
    forbidden = (
        "atlas.api",
        "atlas.repositories",
        "atlas.trader_now",
        "fastapi",
        "sqlalchemy",
    )
    for path in _PROJECTION.glob("*.py"):
        for imported in _imports(path):
            assert not imported.startswith(forbidden)
