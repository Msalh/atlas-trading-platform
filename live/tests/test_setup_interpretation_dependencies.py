"""
Setup Interpretation Sprint 1. Automated dependency boundary audit for
atlas.setup_interpretation, following the same AST-based, permanent-test
approach atlas/tests/test_market_context_dependencies.py established -
applied from Sprint 1 rather than retrofitted later, the same way
Strategy Engine's own dependency audit was.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_SETUP_INTERPRETATION_DIR = _ATLAS_ROOT / "setup_interpretation"
_REPLAY_ENGINE_DIR = _ATLAS_ROOT / "replay_engine"
_STRATEGY_ENGINE_DIR = _ATLAS_ROOT / "strategy_engine"

# Sprint 1's real, current imports per file - intra-package imports
# (atlas.setup_interpretation.*) are always allowed; only cross-package
# atlas.* imports are restricted here.
_ALLOWED_CROSS_PACKAGE_IMPORTS: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset(),
    "definitions.py": frozenset(),
    "fingerprint.py": frozenset(),
}

_FORBIDDEN_PREFIXES = (
    "atlas.rule_engine", "atlas.setup_engine", "atlas.replay_engine", "atlas.market_context",
    "atlas.strategy_engine", "atlas.repositories", "atlas.api", "atlas.events", "atlas.research",
    "atlas.research_export", "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services",
    "atlas.live_view", "atlas.profiling", "atlas.market_engine",
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


def _cross_package_atlas_imports(file_path: Path) -> set[str]:
    return {
        name for name in _imported_module_roots(file_path)
        if name.startswith("atlas.") and not name.startswith("atlas.setup_interpretation")
    }


# ---- exact current-usage allowlist ----

@pytest.mark.parametrize("filename", sorted(_ALLOWED_CROSS_PACKAGE_IMPORTS))
def test_module_imports_match_current_actual_allowlist(filename):
    file_path = _SETUP_INTERPRETATION_DIR / filename
    disallowed = _cross_package_atlas_imports(file_path) - _ALLOWED_CROSS_PACKAGE_IMPORTS[filename]
    assert not disallowed, f"{filename} imports beyond its current actual allowlist: {disallowed}"


# ---- explicitly forbidden packages ----

@pytest.mark.parametrize("filename", sorted(_ALLOWED_CROSS_PACKAGE_IMPORTS))
def test_no_module_imports_any_explicitly_forbidden_package(filename):
    file_path = _SETUP_INTERPRETATION_DIR / filename
    for name in _cross_package_atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


def test_no_module_imports_atlas_setup_engine_registry_or_any_frozen_registry():
    """Definitions must use stable string identifiers, never import Setup
    Engine's own frozen SETUP_ENGINE_REGISTRY - checked directly, not only
    implied by the forbidden-prefix check above."""
    for filename in _ALLOWED_CROSS_PACKAGE_IMPORTS:
        imported = _imported_module_roots(_SETUP_INTERPRETATION_DIR / filename)
        assert not any(name.startswith("atlas.setup_engine") for name in imported)


# ---- intra-package imports stay within the package (sanity check) ----

def test_definitions_only_imports_models_intra_package():
    imported = {
        name for name in _imported_module_roots(_SETUP_INTERPRETATION_DIR / "definitions.py")
        if name.startswith("atlas.setup_interpretation")
    }
    assert imported <= {"atlas.setup_interpretation.models"}


# ---- only approved downstream consumers may depend on Setup Interpretation ----

def test_nothing_outside_setup_interpretation_or_its_approved_downstream_consumers_imports_it():
    """atlas.replay_engine (Sprint 5 - build_replay_output_window() calls
    interpret_setups() to populate ReplayFrame.setup_interpretations) and
    atlas.strategy_engine (Sprint 6 - the reference strategy reads
    ReplayFrame.setup_interpretations directly) are the two approved
    downstream consumers as of this sprint. Nothing else may import
    atlas.setup_interpretation."""
    exempt_dirs = {_SETUP_INTERPRETATION_DIR, _REPLAY_ENGINE_DIR, _STRATEGY_ENGINE_DIR}
    for py_file in _ATLAS_ROOT.rglob("*.py"):
        if any(exempt == py_file.parent or exempt in py_file.parents for exempt in exempt_dirs):
            continue
        imported = _imported_module_roots(py_file)
        offending = {name for name in imported if name.startswith("atlas.setup_interpretation")}
        assert not offending, f"{py_file} imports atlas.setup_interpretation unexpectedly: {offending}"


# ---- no circular imports ----

@pytest.mark.parametrize(
    "directory_name",
    ["core", "market_engine", "rule_engine", "setup_engine", "market_context"],
)
def test_no_frozen_or_sibling_package_imports_setup_interpretation_back(directory_name):
    """replay_engine and strategy_engine are deliberately absent from this
    list (Sprints 5 and 6 respectively made them the two approved,
    one-way, non-circular downstream consumers - see the exemption above,
    not packages that must never import Setup Interpretation)."""
    directory = _ATLAS_ROOT / directory_name
    for py_file in directory.rglob("*.py"):
        imported = _imported_module_roots(py_file)
        offending = {name for name in imported if name.startswith("atlas.setup_interpretation")}
        assert not offending, f"{py_file} imports atlas.setup_interpretation (circular): {offending}"
