"""Dependency boundaries for the HTTP-independent TraderNow facade."""

import ast
from pathlib import Path

_ATLAS = Path(__file__).resolve().parent.parent / "atlas"
_APPLICATION = _ATLAS / "application"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_application_facade_has_no_api_infrastructure_or_environment_dependency():
    forbidden = (
        "atlas.api",
        "atlas.config",
        "atlas.repositories",
        "fastapi",
        "os",
        "sqlalchemy",
    )
    for path in _APPLICATION.glob("*.py"):
        for imported in imports(path):
            assert not imported.startswith(forbidden)


def test_domain_packages_do_not_depend_on_application_facade():
    for package in (
        "trader_now",
        "risk_assessment",
        "risk_projection",
        "rule_engine",
        "setup_engine",
        "market_context",
        "setup_interpretation",
        "strategy_engine",
    ):
        for path in (_ATLAS / package).glob("*.py"):
            assert not any(
                imported.startswith("atlas.application") for imported in imports(path)
            )


def test_facade_reuses_only_canonical_public_composition_modules():
    application_imports = imports(_APPLICATION / "trader_now.py")
    expected_atlas_imports = {
        "atlas.application.errors",
        "atlas.market_engine.ports",
        "atlas.risk_assessment.models",
        "atlas.trader_now.contexts",
        "atlas.trader_now.freshness",
        "atlas.trader_now.interpretations",
        "atlas.trader_now.models",
        "atlas.trader_now.ports",
        "atlas.trader_now.rules",
        "atlas.trader_now.service",
        "atlas.trader_now.setups",
        "atlas.trader_now.strategies",
        "atlas.trader_now.trust",
    }
    assert {
        imported for imported in application_imports if imported.startswith("atlas.")
    } == expected_atlas_imports
