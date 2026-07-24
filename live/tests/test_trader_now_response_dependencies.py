"""Dependency boundaries for the TraderNow transport projection."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "atlas" / "api_models"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_transport_projection_has_no_fastapi_or_infrastructure_dependency():
    imported = imports(PACKAGE / "trader_now.py")

    assert "fastapi" not in imported
    assert "atlas.application" not in imported
    assert "atlas.config" not in imported
    assert "atlas.db" not in imported
    assert "atlas.repositories" not in imported
    assert all("postgres" not in name for name in imported)


def test_domain_does_not_depend_on_api_models():
    atlas = PACKAGE.parent
    for package_name in (
        "trader_now",
        "rule_engine",
        "setup_engine",
        "market_context",
        "setup_interpretation",
        "strategy_engine",
        "risk_assessment",
        "risk_projection",
    ):
        for path in (atlas / package_name).glob("*.py"):
            assert "atlas.api_models" not in imports(path)
