"""Phase 18C purity boundary. Mirrors test_trade_plan_authority_dependencies.py's
pattern, adapted for a package whose sanctioned job is fetching evidence
through an injected port (so, unlike that file, a literal "fetch(" ban would
be a false positive here - what must stay absent is a concrete network/DB/
broker implementation living inside the package instead of behind the port)."""

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
ATLAS = ROOT / "atlas"
PACKAGE = ROOT / "atlas_ai_service"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_service_package_has_only_pure_and_frozen_dependencies():
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
        "atlas_snapshot_capture",
        "atlas_snapshot_store",
    )
    for path in PACKAGE.glob("*.py"):
        assert not any(
            name == prefix or name.startswith(f"{prefix}.")
            for name in _imports(path)
            for prefix in forbidden
        ), path.name


def test_service_package_has_no_real_transport_or_order_execution_implementation():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    )
    for forbidden in (
        "http://",
        "https://",
        "database_url",
        "requests.",
        "urllib.request",
        "socket.socket(",
        "http.client",
        "place_order",
        "execute_order",
        "send_order",
        "forward_to_pickmytrade",
        "build_trade_plan(",
    ):
        assert forbidden not in source, forbidden


def test_evidence_digest_is_never_read_off_a_parsed_snapshot_mapping():
    # DR-3: SnapshotVerification.evidence_digest must be derived exclusively
    # from atlas_snapshot.digest()/verify(), never trusted from a snapshot's
    # own declared integrity.evidence_digest field - the exact shortcut the
    # frozen Phase 18A policy names as prohibited
    # ("client_side_digest_verification"). This does not forbid the string
    # "evidence_digest" outright (it is a legitimate SnapshotVerification
    # keyword argument name) - only reading it as a key off a mapping.
    forbidden = (
        '["evidence_digest"]',
        "['evidence_digest']",
        '.get("evidence_digest"',
        ".get('evidence_digest'",
    )
    for path in PACKAGE.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(term in source for term in forbidden), path.name


def test_certified_runtime_does_not_import_ai_service_package():
    runtime_roots = (
        ATLAS / "api",
        ATLAS / "application",
        ATLAS / "services",
        ATLAS / "repositories",
        ATLAS / "trader_now",
    )
    runtime_files = [
        path for root in runtime_roots if root.exists() for path in root.rglob("*.py")
    ] + [ATLAS / "main.py", ATLAS / "read_only_service.py"]
    for path in runtime_files:
        if not path.exists():
            continue
        imports = _imports(path)
        assert not any(
            name == "atlas_ai_service" or name.startswith("atlas_ai_service.")
            for name in imports
        ), path.name
