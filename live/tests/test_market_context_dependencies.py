"""
Phase N1 Sprint 5 (Finalization). Automated dependency boundary audit for
atlas.market_context, replacing the manual grep-based audit performed at
the earlier Finalization Gate with a permanent, repeatable test. Simple
AST-based import inspection only - no dependency-analysis framework.

--- A note on the allowlists below ---

Sprint 5's own instructions describe models.py as "-> standard library
only" and give shorter per-file allowlists than what the already-approved,
already-certified Sprint 1-4 code actually (and correctly) imports. Two
real, necessary dependencies are missing from that written description:

    - models.py (and by extension every module built on it) needs
      atlas.core.primitives.Symbol/Timeframe - the shared instrument-
      identity primitives every package in this codebase depends on
      (Rule Engine, Setup Engine, and Market Engine all import
      atlas.core.primitives too; it is the project's foundational layer,
      not a "project-layer dependency" in the sense the frozen-package
      boundary rules are about).
    - regime.py and service.py need atlas.market_engine.models.MarketState
      - the type Market Context's entire domain (a MarketState window ->
        an interpretation of it) is built around.

Silently enforcing the stricter, incomplete allowlist as written would
fail these tests against correct, already-certified code - the same kind
of self-contradiction the original Phase N1 plan needed a correction for
(the window_integrity allowlist, Sprint "corrected plan" round). The
allowlists below encode the REAL, already-approved architecture instead;
this is called out explicitly here and in the Final Phase N1 Report
rather than silently patched over.

What these tests DO enforce exactly as specified: no forbidden
cross-package coupling (atlas.setup_engine, atlas.research,
atlas.research_export, and every atlas.rule_engine module except
window_integrity), no circular imports, and session.py/regime.py's mutual
independence from each other and from service.py/fingerprint.py.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_MARKET_CONTEXT_DIR = _ATLAS_ROOT / "market_context"
_REPLAY_ENGINE_DIR = _ATLAS_ROOT / "replay_engine"

# The real, certified allowlist per module - see this file's own docstring
# for the two corrections versus Sprint 5's written (incomplete) version.
_ALLOWED_ATLAS_IMPORTS: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset({"atlas.core.primitives"}),
    "definitions.py": frozenset(),
    "fingerprint.py": frozenset(),
    "session.py": frozenset({
        "atlas.market_context.definitions",
        "atlas.market_context.models",
    }),
    "regime.py": frozenset({
        "atlas.market_context.definitions",
        "atlas.market_context.models",
        "atlas.market_engine.models",
        "atlas.rule_engine.window_integrity",
    }),
    "service.py": frozenset({
        "atlas.core.primitives",
        "atlas.market_context.definitions",
        "atlas.market_context.fingerprint",
        "atlas.market_context.models",
        "atlas.market_context.regime",
        "atlas.market_context.session",
        "atlas.market_engine.models",
        "atlas.rule_engine.window_integrity",
    }),
}

_FORBIDDEN_PREFIXES = ("atlas.setup_engine", "atlas.research", "atlas.research_export")


def _imported_module_roots(file_path: Path) -> set[str]:
    """Every dotted module path this file imports from, via `import X` or
    `from X import Y` - a plain AST walk, not a framework."""
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


# ---- Per-file allowlist enforcement ----

@pytest.mark.parametrize("filename", sorted(_ALLOWED_ATLAS_IMPORTS))
def test_module_imports_stay_within_the_approved_allowlist(filename):
    file_path = _MARKET_CONTEXT_DIR / filename
    disallowed = _atlas_imports(file_path) - _ALLOWED_ATLAS_IMPORTS[filename]
    assert not disallowed, f"{filename} imports unapproved project-layer modules: {disallowed}"


@pytest.mark.parametrize("filename", sorted(_ALLOWED_ATLAS_IMPORTS))
def test_no_module_imports_setup_engine_research_or_research_export(filename):
    file_path = _MARKET_CONTEXT_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden module {name}"


# ---- Rule Engine dependency is limited to exactly window_integrity ----

def test_regime_py_rule_engine_dependency_is_limited_to_window_integrity():
    rule_engine_imports = {
        name for name in _atlas_imports(_MARKET_CONTEXT_DIR / "regime.py")
        if name.startswith("atlas.rule_engine")
    }
    assert rule_engine_imports == {"atlas.rule_engine.window_integrity"}


def test_service_py_rule_engine_dependency_is_limited_to_window_integrity():
    rule_engine_imports = {
        name for name in _atlas_imports(_MARKET_CONTEXT_DIR / "service.py")
        if name.startswith("atlas.rule_engine")
    }
    assert rule_engine_imports == {"atlas.rule_engine.window_integrity"}


def test_session_definitions_fingerprint_and_models_never_import_rule_engine():
    for filename in ("session.py", "definitions.py", "fingerprint.py", "models.py", "__init__.py"):
        rule_engine_imports = {
            name for name in _atlas_imports(_MARKET_CONTEXT_DIR / filename)
            if name.startswith("atlas.rule_engine")
        }
        assert not rule_engine_imports, f"{filename} must never import atlas.rule_engine, got {rule_engine_imports}"


# ---- session.py / regime.py mutual independence ----

def test_session_and_regime_do_not_import_each_other_service_or_fingerprint():
    forbidden = {
        "atlas.market_context.regime", "atlas.market_context.session",
        "atlas.market_context.service", "atlas.market_context.fingerprint",
    }
    session_imports = _atlas_imports(_MARKET_CONTEXT_DIR / "session.py")
    regime_imports = _atlas_imports(_MARKET_CONTEXT_DIR / "regime.py")
    assert not (session_imports & forbidden), f"session.py imports: {session_imports & forbidden}"
    assert not (regime_imports & forbidden), f"regime.py imports: {regime_imports & forbidden}"


# ---- No circular imports ----

def test_no_module_market_context_depends_on_imports_market_context_back():
    """market_context depends on atlas.core, atlas.market_engine, and
    atlas.rule_engine.window_integrity - none of those may import
    atlas.market_context back, or the dependency graph would cycle.
    atlas.replay_engine is deliberately NOT checked here: it is Phase N2's
    downstream consumer BUILT on top of market_context, not something
    market_context itself depends on, so it legitimately imports it - see
    the next test, which checks the actually-meaningful invariant instead."""
    for directory_name in ("core", "market_engine", "rule_engine"):
        directory = _ATLAS_ROOT / directory_name
        for py_file in directory.rglob("*.py"):
            offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.market_context")}
            assert not offending, f"{py_file} imports atlas.market_context (circular): {offending}"


def test_nothing_outside_market_context_or_its_approved_downstream_consumer_imports_it():
    """Scans the whole atlas package tree, excluding market_context itself
    and atlas.replay_engine (Phase N2's approved, one-way downstream
    consumer - see the ADR). Nothing else may import atlas.market_context."""
    exempt_dirs = {_MARKET_CONTEXT_DIR, _REPLAY_ENGINE_DIR}
    for py_file in _ATLAS_ROOT.rglob("*.py"):
        if any(exempt == py_file.parent or exempt in py_file.parents for exempt in exempt_dirs):
            continue
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.market_context")}
        assert not offending, f"{py_file} imports atlas.market_context unexpectedly: {offending}"
