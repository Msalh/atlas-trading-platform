"""
Phase N4 Sprint 9 (Milestone: Phase N4 Core certification). The
whole-pipeline dependency audit the roadmap's own Sprint 9 deliverable
text requires: "zero production dependents of atlas.research, confirmed
the same way Replay Engine's/Setup Interpretation's zero/approved-
dependent lists were verified."

Every individual Research Engine package (backtesting, statistics,
validation, ranking, experiment_builder, research_deploy, promotion, ...)
already has its own narrow dependency audit proving IT doesn't import
outside its own allowlist. This test is the complementary, whole-tree
check from the other side: confirms that no production/trading package
anywhere under atlas/ imports atlas.research at all, except the small,
explicitly sanctioned set of API router files whose entire job is calling
into it.

The roadmap's own risk note for this sprint: "the whole-pipeline audit
here is the first point something could have quietly leaked a production
dependency across eight prior sprints; treat any finding here as a
stop-the-line event, not a fix-and-continue one." This test is what makes
that finding possible to detect at all.
"""
import ast
from pathlib import Path

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"

# The complete, closed list of files anywhere under atlas/ that are
# sanctioned to import atlas.research - every one of them is a thin API
# router whose entire job is calling into the Research Engine, never
# production/trading code. Adding a new entry here should be as rare and
# deliberate as adding a new sprint's own router.
_SANCTIONED_RESEARCH_CONSUMERS = frozenset({
    "api/v1/research_pipeline.py",  # Sprint 8.2 - smoke-test/leaderboard endpoints
    "api/v1/promotion.py",  # Sprint 9 - promotion candidates/decide/history endpoints
    "api/v1/research_lineage.py",  # Sprint 10 Slice A - composed read-only lineage walk
    # Pre-existing (UI v2 era, predates this session's Sprint 8/8.1/8.2/9
    # work) - imports only atlas.research.service.current_code_version, a
    # pure, side-effect-free git-commit-string utility with zero coupling
    # to Hypothesis/Realization/Evidence/Ledger data. A real, disclosed
    # architectural finding surfaced by this exact audit and explicitly
    # accepted rather than silently exempted: fixing it (moving the
    # utility to a neutral location) is real, unplanned scope on a live
    # production endpoint this session hasn't otherwise touched, out of
    # Sprint 9's own boundary. Named here so it stays visible, not because
    # it's endorsed as the ideal shape.
    "api/v1/setup_engine.py",
})

# Packages that are themselves research-adjacent infrastructure, not
# production/trading code - excluded from this audit entirely since their
# whole purpose is reading from atlas.research (their own dependency
# audits, where they exist, cover their footprint precisely).
_EXCLUDED_DIRS = frozenset({"research", "research_export", "live_view", "research_deploy", "__pycache__"})


def _imported_module_roots(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def _atlas_research_imports(file_path: Path) -> set[str]:
    """atlas.research.* only - NOT atlas.research_export.*/atlas.research_deploy.*,
    which merely share a string prefix with atlas.research but are
    separate, sibling top-level packages, not its submodules. A naive
    startswith("atlas.research") check would incorrectly flag those as
    research-engine imports."""
    return {
        n for n in _imported_module_roots(file_path)
        if n == "atlas.research" or n.startswith("atlas.research.")
    }


def test_zero_production_dependents_of_atlas_research():
    """Scans every .py file under atlas/ except the excluded research-
    adjacent directories, and confirms atlas.research is imported nowhere
    except the closed, sanctioned router list above."""
    offending: dict[str, set[str]] = {}
    for py_file in _ATLAS_ROOT.rglob("*.py"):
        relative = py_file.relative_to(_ATLAS_ROOT)
        if relative.parts[0] in _EXCLUDED_DIRS:
            continue
        relative_str = str(relative).replace("\\", "/")
        if relative_str in _SANCTIONED_RESEARCH_CONSUMERS:
            continue
        imports = _atlas_research_imports(py_file)
        if imports:
            offending[relative_str] = imports

    assert not offending, (
        f"Found production/trading files importing atlas.research outside the sanctioned router "
        f"list - this is a stop-the-line finding per the roadmap's own Sprint 9 risk note, not a "
        f"fix-and-continue one: {offending}"
    )


def test_strategy_engine_specifically_has_zero_research_dependency():
    """The single most important individual case - stated separately and
    explicitly, not only folded into the whole-tree scan above, since this
    is the one edge the entire N4 architecture has protected since Sprint 1
    (Principle VIII.4: research and production objects are never
    structurally interchangeable, and never import each other)."""
    strategy_engine_dir = _ATLAS_ROOT / "strategy_engine"
    for py_file in strategy_engine_dir.rglob("*.py"):
        offending = _atlas_research_imports(py_file)
        assert not offending, f"{py_file} imports atlas.research: {offending}"


def test_sanctioned_consumer_list_matches_files_that_actually_import_research():
    """The inverse check: every file in the sanctioned list must actually
    exist and actually import atlas.research - an unused allowlist entry
    is exactly the kind of drift that would let a future, real leak hide
    behind a stale exemption."""
    for relative_str in _SANCTIONED_RESEARCH_CONSUMERS:
        py_file = _ATLAS_ROOT / relative_str
        assert py_file.exists(), f"sanctioned consumer {relative_str} does not exist"
        assert _atlas_research_imports(py_file), f"sanctioned consumer {relative_str} does not actually import atlas.research"
