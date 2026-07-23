"""
Sprint 8.2. Mechanical proof of the architectural review's own §11 claim:
deployment introduces no coupling into atlas.research.** - the new
atlas.research_deploy package and atlas.api.v1.research_pipeline router
sit entirely outside the audited tree, importing FROM atlas.research.**
(a one-way edge, exactly mirroring atlas.research_export/atlas.live_view's
own existing precedent), never the other way around.
"""
import ast
from pathlib import Path

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"
_RESEARCH_DIR = _ATLAS_ROOT / "research"

_FORBIDDEN_PREFIXES = ("atlas.api", "atlas.main", "atlas.research_deploy")


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


def test_nothing_under_atlas_research_imports_the_deployment_layer():
    """The one-way direction claim, proven mechanically rather than
    merely asserted: every file under atlas/research/** (every sprint,
    frozen or not) must remain completely unaware that atlas.api,
    atlas.main, or atlas.research_deploy exist."""
    offending_files: dict[str, set[str]] = {}
    for py_file in _RESEARCH_DIR.rglob("*.py"):
        offending = {n for n in _atlas_imports(py_file) if n.startswith(_FORBIDDEN_PREFIXES)}
        if offending:
            offending_files[str(py_file)] = offending
    assert not offending_files, f"atlas/research/** files importing the deployment layer: {offending_files}"


def test_research_deploy_only_imports_research_stores_and_models():
    """atlas.research_deploy's own footprint stays minimal - only the
    Ledger stores it exists to wire up, never .backtesting/.statistics/
    .validation/.ranking/.experiment_builder directly (those are the
    research_pipeline router's own concern, not the startup-check
    package's)."""
    research_deploy_dir = _ATLAS_ROOT / "research_deploy"
    allowed = frozenset({"atlas.research.stores"})
    for py_file in research_deploy_dir.rglob("*.py"):
        disallowed = _atlas_imports(py_file) - allowed
        assert not disallowed, f"{py_file} imports beyond its allowlist: {disallowed}"


def test_research_pipeline_router_never_imports_backtesting_directly():
    """The router calls atlas.research.experiment_builder.service.
    build_realization_experiment(), which itself calls
    atlas.research.backtesting.execute_realization() internally - the
    router has no reason to import atlas.research.backtesting itself, the
    same layering discipline already established between
    experiment_builder and backtesting since Sprint 8."""
    router_file = _ATLAS_ROOT / "api" / "v1" / "research_pipeline.py"
    imports = _atlas_imports(router_file)
    assert not any(n.startswith("atlas.research.backtesting") for n in imports)
