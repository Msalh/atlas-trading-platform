import ast
from pathlib import Path

ATLAS = Path(__file__).parents[1] / "atlas"
PACKAGE = ATLAS / "trade_plan_authority"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_authority_package_has_only_pure_domain_dependencies():
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
        assert not any(
            name == prefix or name.startswith(f"{prefix}.")
            for name in _imports(path)
            for prefix in forbidden
        )


def test_authority_package_has_no_provider_adapter_or_mutation_implementation():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    )
    for forbidden in (
        "http://",
        "https://",
        "database_url",
        "connect(",
        "fetch(",
        "place_order",
        "execute_order",
        "send_order",
        "build_trade_plan(",
    ):
        assert forbidden not in source


def test_certified_runtime_does_not_import_or_invoke_trade_plan_packages():
    runtime_roots = (
        ATLAS / "api",
        ATLAS / "application",
        ATLAS / "services",
        ATLAS / "trader_now",
    )
    runtime_files = [path for root in runtime_roots for path in root.rglob("*.py")] + [
        ATLAS / "main.py",
        ATLAS / "read_only_service.py",
    ]
    for path in runtime_files:
        imports = _imports(path)
        assert not any(
            name == prefix or name.startswith(f"{prefix}.")
            for name in imports
            for prefix in ("atlas.trade_plan", "atlas.trade_plan_authority")
        )
        source = path.read_text(encoding="utf-8")
        assert "build_trade_plan(" not in source


def test_trader_now_public_response_has_no_trade_plan_field():
    path = ATLAS / "api_models" / "trader_now.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    response = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TraderNowResponse"
    )
    names = {
        target.id
        for node in response.body
        if isinstance(node, ast.AnnAssign)
        and isinstance((target := node.target), ast.Name)
    }
    assert "trade_plan" not in names
