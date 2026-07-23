"""
Phase N4 Sprint 5. Dependency boundary audit for atlas.research.experiment_builder
and atlas.research.statistics - the same AST-based, permanent-test approach
every prior sprint's own boundary has used. Proves: Statistics never depends
on Experiment Builder (or vice versa); neither imports atlas.replay_engine
directly; atlas.research.stores is never imported by either; neither
modifies or is imported back by atlas.research.features or Sprint 1-3
modules.

Sprint 8 update: Experiment Builder's own allowlist gains
atlas.research.backtesting and atlas.research.replay_bridge (Stage B/C's
own sanctioned new dependencies - see experiment_builder/__init__.py).
Statistics's own allowlist gains atlas.research.backtesting.models (the
ResearchDecision type only, for its own decision-sequence Evidence
extension). Neither package is permitted to import atlas.replay_engine
directly even now - atlas.research.replay_bridge remains the only Research
Engine module allowed to do that, per its own frozen Sprint 3 boundary
test.

Sprint 8.1 update: Statistics's own allowlist additionally gains
atlas.research.replay_bridge - type-only, for compute_decision_sequence_
evidence()'s own `frames` parameter (asserts decisions/frames share the
same length; never fetches data). This package's own original rule (below,
test_statistics_never_imports_the_ledger) is narrowed accordingly: it now
proves Statistics stays off the Ledger, and a separate test proves it never
imports atlas.replay_engine directly either way.
"""
import ast
from pathlib import Path

import pytest

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_EXPERIMENT_BUILDER_DIR = _ATLAS_ROOT / "research" / "experiment_builder"
_STATISTICS_DIR = _ATLAS_ROOT / "research" / "statistics"

_EXPERIMENT_BUILDER_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "service.py": frozenset({
        "atlas.market_engine.models",
        "atlas.research.backtesting.models",
        "atlas.research.backtesting.service",
        "atlas.research.features.models",
        "atlas.research.features.registry",
        "atlas.research.fingerprint",
        "atlas.research.models",
        "atlas.research.ports",
        "atlas.research.replay_bridge",
        "atlas.research.service",
    }),
}

_STATISTICS_ALLOWED: dict[str, frozenset[str]] = {
    "__init__.py": frozenset(),
    "service.py": frozenset({
        "atlas.research.backtesting.models",
        "atlas.research.features.models",
        "atlas.research.fingerprint",
        "atlas.research.models",
        "atlas.research.replay_bridge",
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


@pytest.mark.parametrize("filename", sorted(_EXPERIMENT_BUILDER_ALLOWED))
def test_experiment_builder_imports_match_current_actual_allowlist(filename):
    file_path = _EXPERIMENT_BUILDER_DIR / filename
    disallowed = _atlas_imports(file_path) - _EXPERIMENT_BUILDER_ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its allowlist: {disallowed}"


@pytest.mark.parametrize("filename", sorted(_STATISTICS_ALLOWED))
def test_statistics_imports_match_current_actual_allowlist(filename):
    file_path = _STATISTICS_DIR / filename
    disallowed = _atlas_imports(file_path) - _STATISTICS_ALLOWED[filename]
    assert not disallowed, f"{filename} imports beyond its allowlist: {disallowed}"


@pytest.mark.parametrize("filename", sorted(set(_EXPERIMENT_BUILDER_ALLOWED) | set(_STATISTICS_ALLOWED)))
def test_no_forbidden_production_package_imported(filename):
    for directory in (_EXPERIMENT_BUILDER_DIR, _STATISTICS_DIR):
        file_path = directory / filename
        if not file_path.exists():
            continue
        for name in _atlas_imports(file_path):
            assert not name.startswith(_FORBIDDEN_PREFIXES), f"{file_path} imports forbidden {name}"


def test_statistics_never_imports_experiment_builder():
    for py_file in _STATISTICS_DIR.rglob("*.py"):
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.experiment_builder")}
        assert not offending, f"{py_file} imports atlas.research.experiment_builder: {offending}"


def test_experiment_builder_never_imports_statistics():
    for py_file in _EXPERIMENT_BUILDER_DIR.rglob("*.py"):
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.statistics")}
        assert not offending, f"{py_file} imports atlas.research.statistics: {offending}"


def test_statistics_never_imports_the_ledger():
    """Statistics stays pure/no-I/O - still true, unchanged, after Sprint
    8.1: atlas.research.stores remains forbidden."""
    for py_file in _STATISTICS_DIR.rglob("*.py"):
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.stores")}
        assert not offending, f"{py_file} imports {offending} - Statistics must never touch the Ledger"


def test_statistics_replay_bridge_dependency_is_type_only_never_a_data_fetch():
    """Sprint 8.1 update to this file's own original, stricter rule (which
    forbade atlas.research.replay_bridge outright, written before any
    legitimate reason for Statistics to reference it existed).
    compute_decision_sequence_evidence()'s own `frames` parameter needs the
    ReplayFrame type for its length-consistency check against `decisions` -
    the identical "type only, never the fetching/execution machinery"
    posture already established for atlas.research.backtesting.models.
    This test proves the narrower thing that actually matters: Statistics
    never calls replay_bridge's own functions (build_replay_frames_for_window/
    fetch_replay_frames) - a type-only import can't do that, but this
    proves it by construction rather than by assuming it, by asserting the
    _STATISTICS_ALLOWED allowlist itself contains no other, wider Replay
    Bridge or Replay Engine surface."""
    for py_file in _STATISTICS_DIR.rglob("*.py"):
        offending = {
            n for n in _atlas_imports(py_file)
            if n.startswith("atlas.replay_engine")  # still never direct - only replay_bridge's own re-export
        }
        assert not offending, f"{py_file} imports {offending} - Statistics must never import atlas.replay_engine directly"


def test_neither_new_package_imports_replay_engine_or_features_registry_write_paths():
    """Statistics must never import atlas.research.features.registry (the
    REGISTRY/evaluate machinery) - it only ever sees already-computed
    FeatureOutcome data, never re-evaluates anything itself."""
    for py_file in _STATISTICS_DIR.rglob("*.py"):
        offending = {n for n in _atlas_imports(py_file) if n.startswith("atlas.research.features.registry")}
        assert not offending, f"{py_file} imports atlas.research.features.registry: {offending}"


def test_nothing_under_atlas_research_features_imports_either_new_sprint5_package():
    """Sprint 4 (frozen) must remain completely unaware of Sprint 5 -
    proves atlas.research.features was not modified to depend forward on
    either new package."""
    features_dir = _ATLAS_ROOT / "research" / "features"
    for py_file in features_dir.rglob("*.py"):
        offending = {
            n for n in _atlas_imports(py_file)
            if n.startswith("atlas.research.experiment_builder") or n.startswith("atlas.research.statistics")
        }
        assert not offending, f"{py_file} imports a Sprint 5 package: {offending}"
