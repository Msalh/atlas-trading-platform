"""
Phase N4 Sprint 9. Dependency boundary audit for atlas.research.promotion -
proves its claimed minimal footprint (the roadmap's own "Dependency
changes: none new"): atlas.research.models/.ports/.fingerprint only - no
import of atlas.research.backtesting/.statistics/.validation/.ranking/
.experiment_builder/.stores/.serialization, and no import of
atlas.strategy_engine/atlas.api/atlas.main in either direction.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_PROMOTION_DIR = _ATLAS_ROOT / "research" / "promotion"

_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "service.py": frozenset({
        "atlas.research.fingerprint",
        "atlas.research.models",
        "atlas.research.ports",
    }),
}

_FORBIDDEN_PREFIXES = (
    "atlas.rule_engine", "atlas.setup_engine", "atlas.market_context", "atlas.setup_interpretation",
    "atlas.replay_engine", "atlas.strategy_engine", "atlas.market_engine", "atlas.repositories",
    "atlas.api", "atlas.main", "atlas.research_deploy", "atlas.events", "atlas.execution",
    "atlas.paper_trading", "atlas.brokers", "atlas.services",
    "atlas.research.backtesting", "atlas.research.statistics", "atlas.research.features",
    "atlas.research.validation", "atlas.research.ranking", "atlas.research.experiment_builder",
    "atlas.research.replay_bridge", "atlas.research.stores", "atlas.research.serialization",
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
def test_promotion_imports_match_current_actual_allowlist(filename):
    file_path = _PROMOTION_DIR / filename
    disallowed = _atlas_imports(file_path) - _ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its allowlist: {disallowed}"


@pytest.mark.parametrize("filename", sorted(_ALLOWED))
def test_promotion_imports_nothing_explicitly_forbidden(filename):
    file_path = _PROMOTION_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


def test_nothing_under_atlas_research_imports_promotion_except_the_api_layer():
    """Sprint 1-8.2 (frozen) must remain completely unaware of Sprint 9 -
    atlas.research.promotion is a new leaf package, nothing inside
    atlas/research/** ever depends on it."""
    research_dir = _ATLAS_ROOT / "research"
    for py_file in research_dir.rglob("*.py"):
        if _PROMOTION_DIR == py_file.parent or _PROMOTION_DIR in py_file.parents:
            continue
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.promotion")}
        assert not offending, f"{py_file} imports atlas.research.promotion: {offending}"


def test_strategy_engine_never_imports_promotion():
    strategy_engine_dir = _ATLAS_ROOT / "strategy_engine"
    for py_file in strategy_engine_dir.rglob("*.py"):
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research")}
        assert not offending, f"{py_file} imports atlas.research: {offending}"
