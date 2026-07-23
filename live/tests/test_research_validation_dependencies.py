"""
Phase N4 Sprint 6. Dependency boundary audit for atlas.research.validation -
proves the package's own claimed minimal footprint: atlas.research.models
and atlas.research.fingerprint only - no import of
atlas.research.experiment_builder, .statistics, .features, .stores
(the Ledger), .replay_bridge, or any N1-N3 production package, despite
"depending on" Statistics/Experiment Builder/Features logically (their
OUTPUT types, all of which live in atlas.research.models already).
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_VALIDATION_DIR = _ATLAS_ROOT / "research" / "validation"

_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset(),
    "service.py": frozenset({
        "atlas.research.fingerprint",
        "atlas.research.models",
        "atlas.research.validation.models",
    }),
}

_FORBIDDEN_PREFIXES = (
    "atlas.rule_engine", "atlas.setup_engine", "atlas.market_context", "atlas.setup_interpretation",
    "atlas.replay_engine", "atlas.strategy_engine", "atlas.market_engine", "atlas.repositories",
    "atlas.api", "atlas.events", "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services",
    "atlas.research.experiment_builder", "atlas.research.statistics", "atlas.research.features",
    "atlas.research.stores", "atlas.research.replay_bridge", "atlas.research.serialization", "atlas.research.ports",
)


def _imported_module_roots(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def _atlas_imports(file_path: Path) -> set[str]:
    return {name for name in _imported_module_roots(file_path) if name.startswith("atlas.")}


@pytest.mark.parametrize("filename", sorted(_ALLOWED))
def test_validation_imports_match_current_actual_allowlist(filename):
    file_path = _VALIDATION_DIR / filename
    disallowed = _atlas_imports(file_path) - _ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its allowlist: {disallowed}"


@pytest.mark.parametrize("filename", sorted(_ALLOWED))
def test_validation_imports_nothing_explicitly_forbidden(filename):
    file_path = _VALIDATION_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


def test_nothing_under_sprint_1_to_5_imports_validation_back():
    """Sprint 1-5 (frozen) must remain completely unaware of Sprint 6."""
    research_dir = _ATLAS_ROOT / "research"
    for py_file in research_dir.rglob("*.py"):
        if _VALIDATION_DIR == py_file.parent or _VALIDATION_DIR in py_file.parents:
            continue
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.validation")}
        assert not offending, f"{py_file} imports atlas.research.validation: {offending}"
