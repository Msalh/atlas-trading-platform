"""Dependency boundary checks for the pure Part 9C model package."""

import ast
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent / "atlas" / "risk_assessment"


def _atlas_imports(filename: str) -> set[str]:
    tree = ast.parse((_PACKAGE / filename).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name for alias in node.names if alias.name.startswith("atlas.")
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("atlas.")
        ):
            imports.add(node.module)
    return imports


def test_models_depend_only_on_canonical_value_types():
    assert _atlas_imports("models.py") == {
        "atlas.core.primitives",
        "atlas.strategy_engine.models",
    }


def test_package_has_no_application_or_infrastructure_dependencies():
    forbidden_prefixes = (
        "atlas.api",
        "atlas.repositories",
        "atlas.services",
        "atlas.trader_now",
    )
    for file_path in _PACKAGE.glob("*.py"):
        for imported in _atlas_imports(file_path.name):
            assert not imported.startswith(forbidden_prefixes), (
                f"{file_path.name} imports forbidden dependency {imported}"
            )
