"""
Phase N4 Sprint 7. Dependency boundary audit for atlas.research.ranking -
proves its claimed minimal footprint: atlas.research.models/.fingerprint/
.ports (write-side LeaderboardSnapshotStore only) and its own local
models.py - no import of atlas.research.validation/.statistics/
.experiment_builder/.features/.replay_bridge, no import of
atlas.research.stores directly (only the ports.py Protocol), and no N1-N3
production package.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_RANKING_DIR = _ATLAS_ROOT / "research" / "ranking"

_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset(),
    "service.py": frozenset({
        "atlas.research.fingerprint",
        "atlas.research.models",
        "atlas.research.ports",
        "atlas.research.ranking.models",
    }),
}

_FORBIDDEN_PREFIXES = (
    "atlas.rule_engine", "atlas.setup_engine", "atlas.market_context", "atlas.setup_interpretation",
    "atlas.replay_engine", "atlas.strategy_engine", "atlas.market_engine", "atlas.repositories",
    "atlas.api", "atlas.events", "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services",
    "atlas.research.experiment_builder", "atlas.research.statistics", "atlas.research.features",
    "atlas.research.validation", "atlas.research.replay_bridge", "atlas.research.stores",
    "atlas.research.serialization",
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
def test_ranking_imports_match_current_actual_allowlist(filename):
    file_path = _RANKING_DIR / filename
    disallowed = _atlas_imports(file_path) - _ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its allowlist: {disallowed}"


@pytest.mark.parametrize("filename", sorted(_ALLOWED))
def test_ranking_imports_nothing_explicitly_forbidden(filename):
    file_path = _RANKING_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


def test_nothing_outside_ranking_imports_it_back():
    """Sprint 1-6 (frozen) must remain completely unaware of Sprint 7."""
    research_dir = _ATLAS_ROOT / "research"
    for py_file in research_dir.rglob("*.py"):
        if _RANKING_DIR == py_file.parent or _RANKING_DIR in py_file.parents:
            continue
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.ranking")}
        assert not offending, f"{py_file} imports atlas.research.ranking: {offending}"
