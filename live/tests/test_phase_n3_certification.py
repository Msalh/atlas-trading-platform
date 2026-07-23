"""
Sprint 7 - Phase N3 Final Certification. Consolidates whole-project
architecture and dependency checks that no single earlier sprint's test
file owns end to end - each individual boundary (Setup Interpretation's
own dependents, Strategy Engine's own rule_engine-free imports, Replay
Engine's own dependency list) is already covered by its own package's
dedicated test file; this file instead certifies the PIPELINE as a whole:

    Rule Engine -> Setup Engine -> Setup Interpretation -> Replay Engine -> Strategy Engine

is the only production path, with no duplicated or parallel direction
interpretation anywhere else in the tree, and no production module other
than atlas.replay_engine.service ever calls interpret_setups() directly.

No production code is exercised for correctness here (that is Rule
Engine's, Setup Engine's, Setup Interpretation's, Replay Engine's, and
Strategy Engine's own already-certified concern) - this file audits
STRUCTURE (imports, call sites) and, in one end-to-end real-pipeline run,
confirms the whole chain produces StrategyDecision objects with zero
exceptions.
"""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_context.definitions import CME_RTH_V1, RegimeClassifierDefinition, RegimeClassifierParams
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.service import build_replay_output_window
from atlas.strategy_engine.service import evaluate_strategies
from atlas.strategy_engine.strategies.displacement_volume_context import DisplacementVolumeContext

_ATLAS_ROOT = Path(__file__).resolve().parent.parent / "atlas"


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


def _calls_named(file_path: Path, name: str) -> int:
    """AST-based count of call expressions targeting a function of the
    given name - matches both `name(...)` (after `from x import name`) and
    `module.name(...)` (after `import x as module`) call shapes."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name:
            count += 1
        elif isinstance(func, ast.Attribute) and func.attr == name:
            count += 1
    return count


# ---- interpret_setups() has exactly one production caller ----

def test_interpret_setups_is_called_from_exactly_one_production_module():
    expected_caller = str(Path("replay_engine") / "service.py")
    callers = {}
    for py_file in _ATLAS_ROOT.rglob("*.py"):
        if (_ATLAS_ROOT / "setup_interpretation") in py_file.parents:
            continue  # interpret_setups's own definition/helpers, not a caller
        count = _calls_named(py_file, "interpret_setups")
        if count:
            callers[str(py_file.relative_to(_ATLAS_ROOT))] = count
    assert callers == {expected_caller: 1}, f"unexpected interpret_setups() callers: {callers}"


def test_strategy_engine_never_calls_interpret_setups():
    strategy_engine_dir = _ATLAS_ROOT / "strategy_engine"
    for py_file in strategy_engine_dir.rglob("*.py"):
        assert _calls_named(py_file, "interpret_setups") == 0, f"{py_file} calls interpret_setups() directly"


# ---- pipeline dependency direction: strictly downstream, no shortcuts ----

def test_rule_engine_depends_on_nothing_downstream():
    for py_file in (_ATLAS_ROOT / "rule_engine").rglob("*.py"):
        imports = _atlas_imports(py_file)
        forbidden = {
            name for name in imports
            if name.startswith((
                "atlas.setup_engine", "atlas.setup_interpretation",
                "atlas.replay_engine", "atlas.strategy_engine", "atlas.market_context",
            ))
        }
        assert not forbidden, f"{py_file} imports downstream package: {forbidden}"


def test_setup_engine_depends_on_nothing_downstream_of_itself():
    for py_file in (_ATLAS_ROOT / "setup_engine").rglob("*.py"):
        imports = _atlas_imports(py_file)
        forbidden = {
            name for name in imports
            if name.startswith((
                "atlas.setup_interpretation", "atlas.replay_engine",
                "atlas.strategy_engine", "atlas.market_context",
            ))
        }
        assert not forbidden, f"{py_file} imports downstream package: {forbidden}"


def test_setup_interpretation_depends_on_nothing_downstream_of_itself():
    for py_file in (_ATLAS_ROOT / "setup_interpretation").rglob("*.py"):
        imports = _atlas_imports(py_file)
        forbidden = {
            name for name in imports
            if name.startswith(("atlas.replay_engine", "atlas.strategy_engine", "atlas.market_context"))
        }
        assert not forbidden, f"{py_file} imports downstream package: {forbidden}"


def test_replay_engine_depends_on_nothing_downstream_of_itself():
    for py_file in (_ATLAS_ROOT / "replay_engine").rglob("*.py"):
        imports = _atlas_imports(py_file)
        forbidden = {name for name in imports if name.startswith("atlas.strategy_engine")}
        assert not forbidden, f"{py_file} imports downstream package: {forbidden}"


# ---- no duplicated or parallel direction interpretation anywhere ----

def test_no_n3_pipeline_package_reads_rule_engine_facts_outside_setup_interpretation():
    """Zero .facts attribute accesses anywhere under the Phase N3 pipeline
    packages (Replay Engine, Strategy Engine) - proving no second,
    parallel interpretation path re-reads trend_5m or any other fact
    outside atlas.setup_interpretation.service, the one approved reader.

    Deliberately scoped to the N3 pipeline packages, not the whole atlas
    tree: atlas.profiling (RE-1/RE-2's own statistical research code, an
    entirely separate, frozen, pre-N3 consumer of RuleEngineOutput.facts)
    legitimately reads it directly for unrelated statistical-profiling
    purposes and is out of this certification's scope."""
    n3_pipeline_dirs = (_ATLAS_ROOT / "replay_engine", _ATLAS_ROOT / "strategy_engine")
    for pipeline_dir in n3_pipeline_dirs:
        for py_file in pipeline_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            accesses = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "facts")
            assert accesses == 0, f"{py_file} reads .facts directly outside the approved layers"


def test_strategy_engine_has_zero_rule_engine_imports():
    for py_file in (_ATLAS_ROOT / "strategy_engine").rglob("*.py"):
        imports = _atlas_imports(py_file)
        offending = {name for name in imports if name.startswith("atlas.rule_engine")}
        assert not offending, f"{py_file} imports atlas.rule_engine: {offending}"


def test_no_second_trend_direction_lookup_table_exists_under_strategy_engine():
    """Structural, not textual: a second copy of "which trend value maps to
    which direction" would have to be a dict literal mapping string keys to
    StrategyDirection/similar - the only such construct anywhere under
    atlas.strategy_engine today is displacement_volume_context.py's own
    _INTERPRETED_DIRECTION, which maps SetupDirection enum members (not
    raw strings like "up"/"down") to StrategyDirection - confirmed by
    checking no Dict literal under the package has a string-literal key."""
    for py_file in (_ATLAS_ROOT / "strategy_engine").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    raise AssertionError(
                        f"{py_file} contains a dict literal keyed by a raw string {key.value!r} - "
                        "a possible copied trend-direction lookup table"
                    )


# ---- real end-to-end pipeline run: zero exceptions ----

_BASE = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # deep overnight, matches Sprint 6's own equivalence fixture

_SMALL_REGIME = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=5, min_bars_required=5, compressed_percentile=25, expanded_percentile=75,
    ),
)


def _bar(index: int, occurred_at: datetime, close: float) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=f"e{index}"),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        open=Price(close, 0.25), high=Price(close + 3.0, 0.25), low=Price(close - 3.0, 0.25),
        close=Price(close, 0.25), volume=1000.0, atr=2.0, volume_ratio=2.0,
        distance_from_vwap_points=0.0, is_rth=False,
    )


def test_full_pipeline_real_run_produces_strategy_decisions_with_zero_exceptions():
    """Rule Engine -> Setup Engine -> Market Context -> Setup Interpretation
    (via build_replay_output_window) -> Strategy Engine (via
    evaluate_strategies + DisplacementVolumeContext), over a real,
    hand-built-but-otherwise-ordinary 25-bar MarketState series. Confirms
    the entire chain runs to completion with no exception, every
    ReplayFrame carries a dense setup_interpretations tuple, and every
    resulting StrategyDecision is a well-formed instance."""
    step = timedelta(minutes=5)
    states = [_bar(i, _BASE + step * i, 100.0 + i * 2) for i in range(25)]

    frames = build_replay_output_window(states, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    assert len(frames) == 25

    plugin = DisplacementVolumeContext()
    for frame in frames:
        assert len(frame.setup_interpretations) == len(frame.setup_engine_output.setups)
        decisions = evaluate_strategies(frame, [plugin])
        assert len(decisions) == 1
        assert decisions[0].occurred_at == frame.market_state.envelope.occurred_at
