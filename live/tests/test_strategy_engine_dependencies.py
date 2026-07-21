"""
Phase N3, Sprint 1. Automated dependency boundary audit for
atlas.strategy_engine - the same AST-based, permanent-test approach
atlas/tests/test_market_context_dependencies.py already established for
Market Context, applied here from Sprint 1 rather than retrofitted later.

Two allowlists are checked, deliberately kept separate:

    - _ACTUAL_ALLOWED: exactly what Sprint 1's real code imports today.
      Tight by design - a future sprint adding a concrete strategy that
      needs, say, atlas.setup_engine.models directly (permitted by the
      package-level boundary, not currently used) would need to update
      this dict, the same way Phase N1's own dependency test evolved
      sprint by sprint rather than pre-declaring every future need.
    - _CEILING: the full package-level boundary from the Phase N3
      architecture ("Strategy Engine may depend only on
      atlas.replay_engine.models, atlas.setup_engine.models,
      atlas.market_context.models, atlas.core primitives") - the maximum
      ANY file in this package may ever import, checked independently of
      what Sprint 1 currently uses.

Both atlas.market_engine and atlas.rule_engine are deliberately absent
from _CEILING: Strategy Engine reaches MarketState/RuleEngineOutput only
through ReplayFrame's own already-typed fields, never by importing those
packages' models directly.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_STRATEGY_ENGINE_DIR = _ATLAS_ROOT / "strategy_engine"

_ACTUAL_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset({"atlas.core.primitives"}),
    "ports.py": frozenset({"atlas.replay_engine.models", "atlas.strategy_engine.models"}),
}

_CEILING = frozenset({
    "atlas.replay_engine.models",
    "atlas.setup_engine.models",
    "atlas.market_context.models",
    "atlas.core.primitives",
})

_FORBIDDEN_PREFIXES = (
    "atlas.market_engine", "atlas.rule_engine", "atlas.repositories", "atlas.api", "atlas.events",
    "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services", "atlas.research",
    "atlas.research_export", "atlas.live_view", "atlas.profiling",
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


# ---- exact current-usage allowlist ----

@pytest.mark.parametrize("filename", sorted(_ACTUAL_ALLOWED))
def test_module_imports_match_current_actual_allowlist(filename):
    file_path = _STRATEGY_ENGINE_DIR / filename
    disallowed = _atlas_imports(file_path) - _ACTUAL_ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its current actual allowlist: {disallowed}"


# ---- package-level ceiling, independent of current usage ----

@pytest.mark.parametrize("filename", sorted(_ACTUAL_ALLOWED))
def test_module_never_exceeds_the_approved_package_level_ceiling(filename):
    file_path = _STRATEGY_ENGINE_DIR / filename
    for name in _atlas_imports(file_path):
        allowed = name in _CEILING or name.startswith("atlas.strategy_engine")
        assert allowed, f"{filename} imports {name}, outside the approved Strategy Engine dependency ceiling"


# ---- explicitly forbidden packages ----

@pytest.mark.parametrize("filename", sorted(_ACTUAL_ALLOWED))
def test_no_module_imports_any_explicitly_forbidden_package(filename):
    file_path = _STRATEGY_ENGINE_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


# ---- zero dependents (Sprint 1 is foundational only) ----

def test_nothing_outside_strategy_engine_imports_it_yet():
    for py_file in _ATLAS_ROOT.rglob("*.py"):
        if _STRATEGY_ENGINE_DIR == py_file.parent or _STRATEGY_ENGINE_DIR in py_file.parents:
            continue
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.strategy_engine")}
        assert not offending, f"{py_file} imports atlas.strategy_engine unexpectedly: {offending}"


# ---- no circular imports ----

def test_replay_engine_models_does_not_import_strategy_engine_back():
    imported = _imported_module_roots(_ATLAS_ROOT / "replay_engine" / "models.py")
    offending = {name for name in imported if name.startswith("atlas.strategy_engine")}
    assert not offending


def test_setup_engine_models_does_not_import_strategy_engine_back():
    imported = _imported_module_roots(_ATLAS_ROOT / "setup_engine" / "models.py")
    offending = {name for name in imported if name.startswith("atlas.strategy_engine")}
    assert not offending


def test_market_context_models_does_not_import_strategy_engine_back():
    imported = _imported_module_roots(_ATLAS_ROOT / "market_context" / "models.py")
    offending = {name for name in imported if name.startswith("atlas.strategy_engine")}
    assert not offending
