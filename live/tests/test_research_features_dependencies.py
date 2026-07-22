"""
Phase N4 Sprint 4. Dependency boundary audit for atlas.research.features -
the same AST-based, permanent-test approach every prior sprint's own
boundary has used. Proves the sprint's central dependency claim exactly:
one real production import (atlas.market_engine.models), zero imports from
atlas.rule_engine despite the roadmap's own "mirroring the shape" language
(see this package's __init__.py docstring for why that is a pattern, not
an import), and zero imports from any other production package.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_FEATURES_DIR = _ATLAS_ROOT / "research" / "features"

_ACTUAL_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset(),
    "evaluators.py": frozenset({
        "atlas.market_engine.models",
        "atlas.research.features.models",
        "atlas.research.models",
    }),
    "registry.py": frozenset({
        "atlas.market_engine.models",
        "atlas.research.features.evaluators",
        "atlas.research.features.models",
        "atlas.research.fingerprint",
        "atlas.research.models",
    }),
    "candidate.py": frozenset({
        "atlas.market_engine.models",
        "atlas.research.features.models",
        "atlas.research.fingerprint",
        "atlas.research.models",
    }),
}

_FORBIDDEN_PREFIXES = (
    "atlas.rule_engine", "atlas.setup_engine", "atlas.market_context", "atlas.setup_interpretation",
    "atlas.replay_engine", "atlas.strategy_engine", "atlas.repositories", "atlas.api", "atlas.events",
    "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services",
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


@pytest.mark.parametrize("filename", sorted(_ACTUAL_ALLOWED))
def test_module_imports_match_current_actual_allowlist(filename):
    file_path = _FEATURES_DIR / filename
    disallowed = _atlas_imports(file_path) - _ACTUAL_ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its current actual allowlist: {disallowed}"


@pytest.mark.parametrize("filename", sorted(_ACTUAL_ALLOWED))
def test_no_module_imports_any_explicitly_forbidden_package(filename):
    file_path = _FEATURES_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


def test_no_file_under_features_imports_rule_engine_despite_the_roadmaps_mirroring_language():
    """The roadmap's own 'Rule Engine models (read-only, mirroring the
    shape)' line is deliberately satisfied by pattern-mirroring only - see
    __init__.py's own docstring. This is the mechanical proof, not just a
    documented intent."""
    for py_file in _FEATURES_DIR.rglob("*.py"):
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.rule_engine")}
        assert not offending, f"{py_file} imports atlas.rule_engine: {offending}"


def test_nothing_outside_research_imports_atlas_research_features():
    """No production package may import this research-only package
    (Design Principle VIII.2)."""
    for py_file in _ATLAS_ROOT.rglob("*.py"):
        if _FEATURES_DIR == py_file.parent or _FEATURES_DIR in py_file.parents:
            continue
        if (_ATLAS_ROOT / "research") in py_file.parents or (_ATLAS_ROOT / "research") == py_file.parent:
            continue
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.research.features")}
        assert not offending, f"{py_file} imports atlas.research.features unexpectedly: {offending}"
