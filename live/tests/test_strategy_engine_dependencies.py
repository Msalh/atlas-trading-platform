"""
Phase N3, Sprint 1; extended Sprint 3 (concrete strategy added) and Sprint
6 (Setup Interpretation migration). Automated dependency boundary audit
for atlas.strategy_engine - the same AST-based, permanent-test approach
atlas/tests/test_market_context_dependencies.py already established for
Market Context, applied here from Sprint 1 rather than retrofitted later.

_ACTUAL_ALLOWED now covers every real file in the package, including
service.py and strategies/*.py - Sprint 1 through Sprint 5 only checked
__init__.py/models.py/ports.py here (the concrete strategy's own imports
were audited separately, in test_strategy_displacement_volume_context.py's
own embedded checks). Sprint 6 folds strategies/displacement_volume_context.py
and service.py into this file's own allowlist too, so this file's own
"zero atlas.rule_engine imports" and "zero forbidden imports" assertions
are genuinely comprehensive across the whole package - not, as before,
silently skipping the one file that used to need the disclosed
atlas.rule_engine exception.

Two allowlists are checked, deliberately kept separate:

    - _ACTUAL_ALLOWED: exactly what today's real code imports, per file.
      Tight by design - a future sprint needing a new import (permitted by
      the package-level ceiling, not currently used) would need to update
      this dict, the same way Phase N1's own dependency test evolved
      sprint by sprint rather than pre-declaring every future need.
    - _CEILING: the full package-level boundary from the Phase N3
      architecture, widened Sprint 6 to add atlas.setup_interpretation.models
      (the reference strategy's own new, narrow dependency, replacing the
      Sprint 3 atlas.rule_engine.models exception it fully removes) - the
      maximum ANY file in this package may ever import, checked
      independently of what any one file currently uses.

atlas.market_engine remains absent from _CEILING (Strategy Engine reaches
MarketState only through ReplayFrame's own already-typed field, never by
importing atlas.market_engine.models directly). atlas.rule_engine is now
explicitly, permanently forbidden (see _FORBIDDEN_PREFIXES) rather than
merely absent from _CEILING - Sprint 3's disclosed exception for it is
gone, and this sprint's whole point is proving it stays gone.
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
    "service.py": frozenset({
        "atlas.replay_engine.models", "atlas.strategy_engine.models", "atlas.strategy_engine.ports",
    }),
    "strategies/__init__.py": frozenset(),
    "strategies/displacement_volume_context.py": frozenset({
        "atlas.market_context.models",
        "atlas.replay_engine.models",
        "atlas.setup_engine.models",
        "atlas.setup_interpretation.models",
        "atlas.strategy_engine.models",
    }),
}

_CEILING = frozenset({
    "atlas.replay_engine.models",
    "atlas.setup_engine.models",
    "atlas.market_context.models",
    "atlas.setup_interpretation.models",
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


def test_setup_interpretation_does_not_import_strategy_engine_back():
    """Sprint 6: Strategy Engine gained a real dependency on
    atlas.setup_interpretation.models - confirms the arrow points one way
    only, the same acyclic shape every other dependency in this codebase
    already follows."""
    for py_file in (_ATLAS_ROOT / "setup_interpretation").rglob("*.py"):
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.strategy_engine")}
        assert not offending, f"{py_file} imports atlas.strategy_engine (circular): {offending}"


# ---- Sprint 6: package-wide, whole-tree confirmation (not just per-file) ----

def test_zero_rule_engine_imports_anywhere_under_strategy_engine():
    for py_file in _STRATEGY_ENGINE_DIR.rglob("*.py"):
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.rule_engine")}
        assert not offending, f"{py_file} imports atlas.rule_engine: {offending}"


def _facts_attribute_accesses(file_path: Path) -> int:
    """AST-based, not a substring search - see
    test_setup_interpretation_service.py's own _non_docstring_string_constants
    precedent for why a blunt substring check over raw source risks
    false-positiving on prose that legitimately discusses a removed
    access pattern. Counting actual ast.Attribute(attr="facts") nodes only
    matches real code performing the access."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "facts")


def test_zero_dot_facts_reads_anywhere_under_strategy_engine():
    for py_file in _STRATEGY_ENGINE_DIR.rglob("*.py"):
        assert _facts_attribute_accesses(py_file) == 0, f"{py_file} reads .facts directly"
