"""
Phase N4 Sprint 8. Dependency boundary audit for atlas.research.backtesting -
proves its claimed minimal footprint: atlas.research.models, this package's
own local modules, and atlas.research.replay_bridge (ReplayFrame, sourced
through replay_bridge's own re-export - never atlas.replay_engine.models
directly, since Sprint 3's own frozen boundary test proves replay_bridge is
the ONLY Research Engine module permitted to import atlas.replay_engine at
all) - no import of atlas.research.features/.statistics/.validation/
.ranking/.experiment_builder/.stores/.serialization/.fingerprint, and
critically no import of atlas.strategy_engine in either direction (the
single most important negative-space test this sprint - see this package's
own __init__.py for why).
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_BACKTESTING_DIR = _ATLAS_ROOT / "research" / "backtesting"

_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset(),
    "ports.py": frozenset({
        "atlas.research.backtesting.models",
        "atlas.research.replay_bridge",
    }),
    "templates.py": frozenset({
        "atlas.research.backtesting.models",
        "atlas.research.models",
        "atlas.research.replay_bridge",
    }),
    "factory.py": frozenset({
        "atlas.research.backtesting.ports",
        "atlas.research.backtesting.templates",
        "atlas.research.models",
    }),
    "service.py": frozenset({
        "atlas.research.backtesting.factory",
        "atlas.research.backtesting.models",
        "atlas.research.models",
        "atlas.research.replay_bridge",
    }),
}

_FORBIDDEN_PREFIXES = (
    "atlas.rule_engine", "atlas.setup_engine", "atlas.market_context", "atlas.setup_interpretation",
    "atlas.strategy_engine", "atlas.market_engine", "atlas.repositories", "atlas.replay_engine",
    "atlas.api", "atlas.events", "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services",
    "atlas.research.experiment_builder", "atlas.research.statistics", "atlas.research.features",
    "atlas.research.validation", "atlas.research.ranking",
    "atlas.research.stores", "atlas.research.serialization", "atlas.research.fingerprint",
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
def test_backtesting_imports_match_current_actual_allowlist(filename):
    file_path = _BACKTESTING_DIR / filename
    disallowed = _atlas_imports(file_path) - _ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its allowlist: {disallowed}"


@pytest.mark.parametrize("filename", sorted(_ALLOWED))
def test_backtesting_imports_nothing_explicitly_forbidden(filename):
    file_path = _BACKTESTING_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


def test_nothing_outside_backtesting_and_experiment_builder_imports_it_back():
    """Sprint 1-7 (frozen) must remain completely unaware of Sprint 8.
    atlas.research.experiment_builder is the one sanctioned exception - its
    own Stage B/C extension (this sprint) necessarily calls
    execute_realization()."""
    research_dir = _ATLAS_ROOT / "research"
    for py_file in research_dir.rglob("*.py"):
        if _BACKTESTING_DIR == py_file.parent or _BACKTESTING_DIR in py_file.parents:
            continue
        if py_file.parent.name == "experiment_builder":
            continue
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.backtesting")}
        assert not offending, f"{py_file} imports atlas.research.backtesting: {offending}"


def test_strategy_engine_never_imports_backtesting():
    """The mirror check from the production side - proves the boundary
    both ways, not just from atlas.research.backtesting's own imports."""
    strategy_engine_dir = _ATLAS_ROOT / "strategy_engine"
    for py_file in strategy_engine_dir.rglob("*.py"):
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research")}
        assert not offending, f"{py_file} imports atlas.research: {offending}"
