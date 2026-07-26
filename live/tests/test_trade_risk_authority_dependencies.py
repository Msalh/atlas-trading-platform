import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "atlas" / "trade_risk_authority"


def test_package_is_pure_domain_and_has_no_runtime_dependencies():
    forbidden = (
        "fastapi",
        "httpx",
        "psycopg",
        "atlas.api",
        "atlas.application",
        "atlas.repositories",
        "atlas.services",
    )
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(
            name == prefix or name.startswith(f"{prefix}.")
            for name in imports
            for prefix in forbidden
        )


def test_ports_are_read_only_and_do_not_expose_mutation_verbs():
    source = (PACKAGE / "ports.py").read_text(encoding="utf-8")
    for forbidden in ("create_", "update_", "delete_", "place_", "execute_"):
        assert forbidden not in source
