"""
Setup Interpretation Sprint 5 (Replay Engine integration). Automated
dependency boundary audit for atlas.replay_engine - the same AST-based,
permanent-test approach already established for Market Context, Setup
Interpretation, and Strategy Engine's own dependency audits. Added now,
when Replay Engine first gained a real outbound dependency worth pinning
down exactly (atlas.setup_interpretation), rather than retrofitted later.

_ACTUAL_ALLOWED is exactly what Replay Engine's real code imports today,
per file - tight by design, the same "today's real usage, not a
speculative ceiling" posture test_strategy_engine_dependencies.py already
established for its own allowlist.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_REPLAY_ENGINE_DIR = _ATLAS_ROOT / "replay_engine"

_ACTUAL_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "models.py": frozenset({
        "atlas.market_context.models",
        "atlas.market_engine.models",
        "atlas.rule_engine.models",
        "atlas.setup_engine.models",
        "atlas.setup_interpretation.models",
    }),
    "segmentation.py": frozenset({
        "atlas.market_engine.models",
        "atlas.profiling.service",
    }),
    "service.py": frozenset({
        "atlas.core.primitives",
        "atlas.market_context.definitions",
        "atlas.market_context.models",
        "atlas.market_context.service",
        "atlas.market_engine.models",
        "atlas.market_engine.ports",
        "atlas.market_engine.service",
        "atlas.replay_engine.models",
        "atlas.replay_engine.segmentation",
        "atlas.rule_engine.models",
        "atlas.rule_engine.service",
        "atlas.setup_engine.models",
        "atlas.setup_engine.service",
        "atlas.setup_interpretation.models",
        "atlas.setup_interpretation.service",
    }),
}

_FORBIDDEN_PREFIXES = (
    "atlas.strategy_engine", "atlas.repositories", "atlas.api", "atlas.events",
    "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services",
    "atlas.research", "atlas.research_export", "atlas.live_view",
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
    file_path = _REPLAY_ENGINE_DIR / filename
    disallowed = _atlas_imports(file_path) - _ACTUAL_ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its current actual allowlist: {disallowed}"


# ---- explicitly forbidden packages ----

@pytest.mark.parametrize("filename", sorted(_ACTUAL_ALLOWED))
def test_no_module_imports_any_explicitly_forbidden_package(filename):
    file_path = _REPLAY_ENGINE_DIR / filename
    for name in _atlas_imports(file_path):
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"{filename} imports forbidden {name}"


# ---- only the approved downstream consumer may depend on Replay Engine ----

def test_nothing_outside_replay_engine_or_its_approved_downstream_consumer_imports_it():
    """atlas.strategy_engine (Phase N3, Sprint 1 - StrategyPlugin.evaluate()
    takes a ReplayFrame) is the one pre-existing, already-approved
    dependent, unrelated to this sprint - not something Sprint 5
    introduced. Nothing else may import atlas.replay_engine."""
    exempt_dirs = {_REPLAY_ENGINE_DIR, _ATLAS_ROOT / "strategy_engine"}
    for py_file in _ATLAS_ROOT.rglob("*.py"):
        if any(exempt == py_file.parent or exempt in py_file.parents for exempt in exempt_dirs):
            continue
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.replay_engine")}
        assert not offending, f"{py_file} imports atlas.replay_engine unexpectedly: {offending}"


# ---- no circular imports: nothing Replay Engine depends on imports it back ----

def test_setup_interpretation_does_not_import_replay_engine_back():
    for py_file in (_ATLAS_ROOT / "setup_interpretation").rglob("*.py"):
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.replay_engine")}
        assert not offending, f"{py_file} imports atlas.replay_engine (circular): {offending}"


def test_rule_engine_does_not_import_replay_engine_back():
    for py_file in (_ATLAS_ROOT / "rule_engine").rglob("*.py"):
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.replay_engine")}
        assert not offending, f"{py_file} imports atlas.replay_engine (circular): {offending}"


def test_setup_engine_does_not_import_replay_engine_back():
    for py_file in (_ATLAS_ROOT / "setup_engine").rglob("*.py"):
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.replay_engine")}
        assert not offending, f"{py_file} imports atlas.replay_engine (circular): {offending}"


def test_market_context_does_not_import_replay_engine_back():
    for py_file in (_ATLAS_ROOT / "market_context").rglob("*.py"):
        offending = {name for name in _atlas_imports(py_file) if name.startswith("atlas.replay_engine")}
        assert not offending, f"{py_file} imports atlas.replay_engine (circular): {offending}"
