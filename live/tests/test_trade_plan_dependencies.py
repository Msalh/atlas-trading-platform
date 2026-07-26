import ast
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "atlas" / "trade_plan"


def test_trade_plan_is_a_pure_domain_package():
    forbidden = (
        "fastapi",
        "httpx",
        "requests",
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
    )
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: list[str] = []
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


def test_trade_plan_has_no_runtime_ports_or_mutation_verbs():
    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    for forbidden in (
        "Protocol",
        "http://",
        "https://",
        "database_url",
        "place_order",
        "execute_order",
        "send_order",
    ):
        assert forbidden not in source
