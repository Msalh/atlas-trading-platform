"""
Setup Interpretation Sprint 3 - Integration Review (not certification).
Validates atlas.setup_interpretation.service.interpret_setups() against
real project builders and replay-shaped data, and performs a read-only
equivalence study for atlas.strategy_engine.strategies
.displacement_volume_context's eventual migration.

No production code is modified by this sprint. Wherever a real market
condition can be produced by feeding hand-built (but otherwise ordinary)
MarketState bars through the REAL Rule Engine / Setup Engine / Replay
Engine pipeline (build_rule_engine_output_window,
build_setup_engine_output_window, build_replay_output_window), this file
does exactly that - never a hand-built FactResult/SetupResult standing in
for what the real evaluators would have computed. The three exceptions
are the genuine CONTRACT-VIOLATION scenarios Correction 1/Sprint 2 added
error paths for (a fact entirely absent, an invalid trend_5m value, an
unregistered setup_id) - these cannot occur from any real pipeline run by
construction (REGISTRY always evaluates every registered fact/setup, and
trend_5m's own contract is a closed three-way classification), which is
exactly why they are contract violations worth testing, not real market
states - those are clearly marked and built by hand.
"""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_context.definitions import CME_RTH_V1, RegimeClassifierDefinition, RegimeClassifierParams
from atlas.market_context.models import ContextQuality
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.service import build_replay_output_window
from atlas.rule_engine.models import RuleEngineOutput
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.rule_engine.service import build_rule_engine_output_window
from atlas.setup_engine.models import SetupEngineOutput
from atlas.setup_engine.models import InsufficientData as SetupInsufficientData
from atlas.setup_engine.registry import REGISTRY as SETUP_ENGINE_REGISTRY
from atlas.setup_engine.service import build_setup_engine_output_window
from atlas.setup_interpretation.definitions import SETUP_INTERPRETATION_V1
from atlas.setup_interpretation.fingerprint import compute_fingerprint
from atlas.setup_interpretation.models import DirectionSource, SetupDirection
from atlas.setup_interpretation.service import (
    SetupInterpretationInvalidFactValueError,
    SetupInterpretationMissingFactError,
    SetupInterpretationUnknownSetupError,
    interpret_setups,
)
from atlas.strategy_engine.models import StrategyDirection, StrategyDisposition
from atlas.strategy_engine.strategies.displacement_volume_context import DisplacementVolumeContext

_BASE = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # 22:00 CDT, 2026-07-20 - deep overnight
_INTERPRETATION_VERSION = SETUP_INTERPRETATION_V1.version
_INTERPRETATION_FINGERPRINT = compute_fingerprint(SETUP_INTERPRETATION_V1)

DISPLACEMENT = "displacement_with_volume_confirmation"
LIQUIDITY_SWEEP = "liquidity_sweep_with_volume_confirmation"
STREAK = "sustained_displacement_streak"
VWAP_EXTENSION = "vwap_extension_with_volume_confirmation"

_SMALL_REGIME = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=5, min_bars_required=5, compressed_percentile=25, expanded_percentile=75,
    ),
)


# ---- real MarketState series builders ----

def _bar(
    index: int, occurred_at: datetime, close: float, *,
    high: float | None = None, low: float | None = None, atr: float = 2.0, volume_ratio: float = 2.0,
    overnight_high: float | None = None, overnight_low: float | None = None,
    previous_day_high: float | None = None, previous_day_low: float | None = None,
    distance_from_vwap_points: float = 0.0, is_rth: bool | None = None,
) -> MarketState:
    high = close + 3.0 if high is None else high
    low = close - 3.0 if low is None else low
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=f"e{index}"),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        open=Price(close, 0.25), high=Price(high, 0.25), low=Price(low, 0.25), close=Price(close, 0.25),
        volume=1000.0, atr=atr, volume_ratio=volume_ratio,
        distance_from_vwap_points=distance_from_vwap_points, is_rth=is_rth,
        overnight_high=Price(overnight_high, 0.25) if overnight_high is not None else None,
        overnight_low=Price(overnight_low, 0.25) if overnight_low is not None else None,
        previous_day_high=Price(previous_day_high, 0.25) if previous_day_high is not None else None,
        previous_day_low=Price(previous_day_low, 0.25) if previous_day_low is not None else None,
    )


def _series(closes: list[float], base: datetime = _BASE, **shared) -> list[MarketState]:
    step = timedelta(minutes=5)
    return [_bar(i, base + step * i, close, **shared) for i, close in enumerate(closes)]



# is_rth=False on every bar: _BASE sits at 22:00 CDT and the whole 125-minute
# span these 25-bar series cover stays deep in OVERNIGHT under CME_RTH_V1
# (well clear of the 07:30 CT pre-open buffer) - so Atlas's own session
# classification (phase=OVERNIGHT -> atlas_is_rth=False) genuinely AGREES
# with this upstream value on every bar, not just leaves it unset. This
# matters beyond realism: with upstream_is_rth left None (UPSTREAM_MISSING),
# ContextQuality can never reach TRUSTED, so DisplacementVolumeContext's own
# ContextQuality.UNKNOWN gate would short-circuit every decision to
# REJECTED before ever reaching its trend_5m check - the migration
# equivalence study below would then never actually exercise the
# CANDIDATE/LONG or CANDIDATE/SHORT path at all, silently passing without
# proving anything about the case that matters most.
_BULLISH_SERIES = _series([100.0 + i * 2 for i in range(25)], is_rth=False)   # clean ascending trend -> "up"
_BEARISH_SERIES = _series([200.0 - i * 2 for i in range(25)], is_rth=False)   # clean descending trend -> "down"
_FLAT_SERIES = _series([100.0] * 25, is_rth=False)                           # constant close -> slope 0 -> "flat"
_SHORT_SERIES = _series([100.0 + i for i in range(5)], is_rth=False)         # < 20 bars -> trend_5m InsufficientData


def _real_outputs(states: list[MarketState]) -> tuple[list[RuleEngineOutput], list[SetupEngineOutput]]:
    """The real pipeline, unchanged: MarketState window -> RuleEngineOutput
    window -> SetupEngineOutput window, via the exact same functions
    Replay Engine itself calls."""
    rule_outputs = build_rule_engine_output_window(states)
    setup_outputs = build_setup_engine_output_window(rule_outputs)
    return rule_outputs, setup_outputs


# =====================================================================
# 1. Real upstream contract compatibility
# =====================================================================

def test_interpret_setups_handles_every_position_of_a_real_bullish_series_without_error():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    for rule_output, setup_output in zip(rule_outputs, setup_outputs):
        result = interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
        assert len(result) == len(setup_output.setups)


def test_real_trend_5m_up_produces_bullish_via_interpret_setups():
    """Confirms interpret_setups correctly consumes the REAL
    FactResult.value trend_5m actually produces (a genuine OLS
    classification, not a hand-built string)."""
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    last_rule, last_setup = rule_outputs[-1], setup_outputs[-1]
    assert last_rule.facts["trend_5m"].value == "up"  # sanity: real Rule Engine agrees
    result = interpret_setups(rule_engine_output=last_rule, setup_engine_output=last_setup)
    displacement = next(i for i in result if i.setup_id == DISPLACEMENT)
    assert displacement.direction == SetupDirection.BULLISH
    assert displacement.source == DirectionSource.RULE_FACT


def test_real_trend_5m_down_produces_bearish_via_interpret_setups():
    rule_outputs, setup_outputs = _real_outputs(_BEARISH_SERIES)
    last_rule, last_setup = rule_outputs[-1], setup_outputs[-1]
    assert last_rule.facts["trend_5m"].value == "down"
    result = interpret_setups(rule_engine_output=last_rule, setup_engine_output=last_setup)
    displacement = next(i for i in result if i.setup_id == DISPLACEMENT)
    assert displacement.direction == SetupDirection.BEARISH


def test_real_liquidity_sweep_evidence_shape_is_consumed_correctly():
    """A genuinely conflicting-sides window, produced by the REAL
    evaluate_liquidity_sweep function (not hand-built evidence) - proves
    interpret_setups reads the actual evidence["qualifying_levels"][i]
    ["side"] shape Rule Engine really produces."""
    # bar0 sweeps the high side, bar1 sweeps the low side, bar2 (current)
    # closes back on the origin side of BOTH.
    states = [
        _bar(0, _BASE, 100.0, high=112.0, low=95.0, overnight_high=110.0, overnight_low=90.0),
        _bar(1, _BASE + timedelta(minutes=5), 100.0, high=105.0, low=88.0, overnight_high=110.0, overnight_low=90.0),
        _bar(2, _BASE + timedelta(minutes=10), 100.0, high=104.0, low=94.0, overnight_high=110.0, overnight_low=90.0),
    ]
    rule_outputs, setup_outputs = _real_outputs(states)
    last_rule, last_setup = rule_outputs[-1], setup_outputs[-1]

    liquidity_fact = last_rule.facts["liquidity_sweep"]
    sides = {level["side"] for level in liquidity_fact.evidence["qualifying_levels"]}
    assert sides == {"high", "low"}  # sanity: real Rule Engine genuinely produced a conflict

    result = interpret_setups(rule_engine_output=last_rule, setup_engine_output=last_setup)
    sweep = next(i for i in result if i.setup_id == LIQUIDITY_SWEEP)
    assert sweep.direction == SetupDirection.AMBIGUOUS
    assert sweep.reason_codes == ("conflicting_sides_in_qualifying_levels",)


def test_real_setup_result_and_setup_level_insufficient_data_both_consumed_correctly():
    """sustained_displacement_streak's required_history is 2 -
    context.history has only 1 entry at position 0, so Setup Engine
    itself (unmodified) produces a real Setup-level InsufficientData
    there - not a hand-built one."""
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES[:3])
    first_setup_output = setup_outputs[0]
    streak_outcome = next(o for o in first_setup_output.setups if o.setup_name == STREAK)
    assert isinstance(streak_outcome, SetupInsufficientData)  # sanity: real Setup Engine agrees

    result = interpret_setups(rule_engine_output=rule_outputs[0], setup_engine_output=first_setup_output)
    streak_interpretation = next(i for i in result if i.setup_id == STREAK)
    assert streak_interpretation.detected is False
    assert streak_interpretation.direction == SetupDirection.UNAVAILABLE


def test_real_rule_fact_insufficient_data_consumed_correctly():
    """trend_5m needs 20 bars - a real 5-bar window leaves it genuinely
    insufficient_data at every position, produced by the real
    evaluate_trend_5m function."""
    rule_outputs, setup_outputs = _real_outputs(_SHORT_SERIES)
    last_rule, last_setup = rule_outputs[-1], setup_outputs[-1]
    assert isinstance(last_rule.facts["trend_5m"], FactInsufficientData)  # sanity

    result = interpret_setups(rule_engine_output=last_rule, setup_engine_output=last_setup)
    displacement = next(i for i in result if i.setup_id == DISPLACEMENT)
    assert displacement.detected is True  # displacement itself needs only 1 bar
    assert displacement.direction == SetupDirection.UNAVAILABLE
    assert displacement.source == DirectionSource.INSUFFICIENT_DATA


def test_real_occurred_at_matches_across_rule_and_setup_engine_output():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    for rule_output, setup_output in zip(rule_outputs, setup_outputs):
        assert rule_output.occurred_at == setup_output.occurred_at


def test_real_setup_ordering_matches_registry_order():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    last_setup_output = setup_outputs[-1]
    result = interpret_setups(rule_engine_output=rule_outputs[-1], setup_engine_output=last_setup_output)
    assert [i.setup_id for i in result] == [o.setup_name for o in last_setup_output.setups]
    assert [o.setup_name for o in last_setup_output.setups] == [r.definition.name for r in SETUP_ENGINE_REGISTRY]


# =====================================================================
# 2. Dense cardinality and ordering
# =====================================================================

def test_dense_output_matches_registry_length_on_real_data():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    for rule_output, setup_output in zip(rule_outputs, setup_outputs):
        result = interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
        assert len(result) == len(setup_output.setups) == len(SETUP_ENGINE_REGISTRY)


def test_no_registered_setup_is_ever_omitted_across_a_real_window():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    expected_ids = {r.definition.name for r in SETUP_ENGINE_REGISTRY}
    for rule_output, setup_output in zip(rule_outputs, setup_outputs):
        result = interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
        assert {i.setup_id for i in result} == expected_ids


def test_detected_false_remains_explicit_on_real_early_positions():
    """Position 0 of a real window: sustained_displacement_streak cannot
    yet have detected=True (insufficient history) - the interpretation's
    own detected field must say so explicitly, not omit the entry."""
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    result = interpret_setups(rule_engine_output=rule_outputs[0], setup_engine_output=setup_outputs[0])
    streak_interpretation = next(i for i in result if i.setup_id == STREAK)
    assert streak_interpretation.detected is False


def test_output_order_is_stable_across_repeated_runs_on_real_data():
    rule_output, setup_output = _real_outputs(_BULLISH_SERIES)[0][-1], _real_outputs(_BULLISH_SERIES)[1][-1]
    orders = [
        tuple(i.setup_id for i in interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output))
        for _ in range(20)
    ]
    assert len(set(orders)) == 1


# =====================================================================
# 3. Replay-shaped validation (no ReplayFrame widening)
# =====================================================================

def test_replay_frames_feed_interpret_setups_without_modification():
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    for frame in frames:
        result = interpret_setups(
            rule_engine_output=frame.rule_engine_output, setup_engine_output=frame.setup_engine_output,
        )
        assert len(result) == len(frame.setup_engine_output.setups)


def test_replay_shaped_occurred_at_alignment():
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    for frame in frames:
        result = interpret_setups(
            rule_engine_output=frame.rule_engine_output, setup_engine_output=frame.setup_engine_output,
        )
        for interpretation in result:
            assert interpretation.occurred_at == frame.market_state.envelope.occurred_at


def test_replay_shaped_version_and_fingerprint_stability():
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    for frame in frames:
        result = interpret_setups(
            rule_engine_output=frame.rule_engine_output, setup_engine_output=frame.setup_engine_output,
        )
        for interpretation in result:
            assert interpretation.interpretation_version == _INTERPRETATION_VERSION
            assert interpretation.interpretation_fingerprint == _INTERPRETATION_FINGERPRINT


def test_replay_shaped_determinism():
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    first_pass = [
        interpret_setups(rule_engine_output=f.rule_engine_output, setup_engine_output=f.setup_engine_output)
        for f in frames
    ]
    second_pass = [
        interpret_setups(rule_engine_output=f.rule_engine_output, setup_engine_output=f.setup_engine_output)
        for f in frames
    ]
    assert first_pass == second_pass


def test_replay_frame_and_upstream_outputs_are_not_mutated():
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    frame = frames[-1]
    original_market_state = frame.market_state
    original_rule_engine_output = frame.rule_engine_output
    original_setup_engine_output = frame.setup_engine_output
    original_facts = dict(frame.rule_engine_output.facts)
    original_setups = tuple(frame.setup_engine_output.setups)

    interpret_setups(rule_engine_output=frame.rule_engine_output, setup_engine_output=frame.setup_engine_output)

    assert frame.market_state is original_market_state
    assert frame.rule_engine_output is original_rule_engine_output
    assert frame.setup_engine_output is original_setup_engine_output
    assert frame.rule_engine_output.facts == original_facts
    assert frame.setup_engine_output.setups == original_setups


# =====================================================================
# 4. Strategy migration equivalence study (read-only; strategy unchanged)
# =====================================================================

def _hypothetical_migrated_decision(setup_interpretation, market_context_quality):
    """Test-only, read-only reimplementation of what
    DisplacementVolumeContext.evaluate() WOULD compute if migrated to
    consume a SetupInterpretation for the displacement_with_volume_
    confirmation setup instead of reading trend_5m directly. Never
    imported by, or wired into, any production code - it exists solely to
    empirically compare against the CURRENT strategy's real output.
    Deliberately reuses the strategy's OWN existing reason-code
    vocabulary ("accepted"/"context_conflict"/"context_insufficient"/
    "setup_absent") to test whether a migration COULD preserve those
    exact strings via a small translation step, distinct from adopting
    SetupInterpretation's own reason codes directly (an open design
    choice for the actual migration sprint, not decided here)."""
    if not setup_interpretation.detected:
        return (StrategyDisposition.NO_SIGNAL, StrategyDirection.FLAT, "setup_absent")
    if market_context_quality == ContextQuality.UNKNOWN:
        return (StrategyDisposition.REJECTED, StrategyDirection.FLAT, "context_insufficient")
    if setup_interpretation.direction == SetupDirection.BULLISH:
        return (StrategyDisposition.CANDIDATE, StrategyDirection.LONG, "accepted")
    if setup_interpretation.direction == SetupDirection.BEARISH:
        return (StrategyDisposition.CANDIDATE, StrategyDirection.SHORT, "accepted")
    if setup_interpretation.direction == SetupDirection.AMBIGUOUS:
        return (StrategyDisposition.REJECTED, StrategyDirection.FLAT, "context_conflict")
    return (StrategyDisposition.REJECTED, StrategyDirection.FLAT, "context_insufficient")  # UNAVAILABLE


def _interpretation_for(rule_output, setup_output, setup_id: str):
    return next(
        i for i in interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
        if i.setup_id == setup_id
    )


@pytest.mark.parametrize("series_name", ["bullish", "bearish", "flat", "short"])
def test_migration_equivalence_disposition_and_direction_match_across_series(series_name):
    series = {
        "bullish": _BULLISH_SERIES, "bearish": _BEARISH_SERIES,
        "flat": _FLAT_SERIES, "short": _SHORT_SERIES,
    }[series_name]
    frames = build_replay_output_window(series, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)

    for frame in frames:
        actual = DisplacementVolumeContext().evaluate(frame)
        interpretation = _interpretation_for(frame.rule_engine_output, frame.setup_engine_output, DISPLACEMENT)
        hypothetical_disposition, hypothetical_direction, _ = _hypothetical_migrated_decision(
            interpretation, frame.market_context.quality,
        )
        assert actual.disposition == hypothetical_disposition, (
            f"{series_name} @ {frame.market_state.envelope.occurred_at}: "
            f"actual={actual.disposition} hypothetical={hypothetical_disposition}"
        )
        assert actual.direction == hypothetical_direction


def test_migration_equivalence_reason_code_translation_is_possible_not_identical():
    """Confirms reason-code AVAILABILITY (a migrated strategy can still
    emit its own existing vocabulary via translation) while documenting
    that SetupInterpretation's OWN reason codes ("trend_up"/"trend_flat"/
    "not_detected_or_source_fact_insufficient_data") are NOT byte-identical
    strings to the strategy's current ones - a real, disclosed divergence,
    not a blocking one, since the strategy's own reason_codes field is not
    part of what SetupInterpretation is meant to replace 1:1."""
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    frame = frames[-1]
    actual = DisplacementVolumeContext().evaluate(frame)
    interpretation = _interpretation_for(frame.rule_engine_output, frame.setup_engine_output, DISPLACEMENT)

    assert actual.reason_codes == ("accepted",)
    assert interpretation.reason_codes == ("trend_up",)
    assert actual.reason_codes != interpretation.reason_codes  # documented, not silently assumed equal

    _, _, hypothetical_reason = _hypothetical_migrated_decision(interpretation, frame.market_context.quality)
    assert hypothetical_reason == actual.reason_codes[0]  # translation CAN preserve the exact current string


def test_migration_equivalence_occurred_at_matches():
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    frame = frames[-1]
    actual = DisplacementVolumeContext().evaluate(frame)
    interpretation = _interpretation_for(frame.rule_engine_output, frame.setup_engine_output, DISPLACEMENT)
    assert actual.occurred_at == interpretation.occurred_at == frame.market_state.envelope.occurred_at


def test_migration_equivalence_context_fingerprint_is_a_different_fingerprint_by_design():
    """StrategyDecision.context_fingerprint comes from
    frame.market_context.context_fingerprint (Market Context's own
    config), NOT interpretation_fingerprint (Setup Interpretation's own,
    separate config) - two distinct audit fingerprints for two distinct
    layers, never meant to be interchangeable. A migrated strategy's
    context_fingerprint field should continue to be Market-Context-sourced,
    unchanged by this migration."""
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    frame = frames[-1]
    actual = DisplacementVolumeContext().evaluate(frame)
    interpretation = _interpretation_for(frame.rule_engine_output, frame.setup_engine_output, DISPLACEMENT)

    assert actual.context_fingerprint == frame.market_context.context_fingerprint
    assert interpretation.interpretation_fingerprint == _INTERPRETATION_FINGERPRINT
    assert actual.context_fingerprint != interpretation.interpretation_fingerprint


# =====================================================================
# 5. Direct Rule Engine dependency audit (Strategy Engine)
# =====================================================================

_STRATEGY_ENGINE_DIR = Path(__file__).resolve().parent.parent / "atlas" / "strategy_engine"


def _rule_engine_imports(file_path: Path) -> set:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("atlas.rule_engine"):
            roots.add(node.module)
        elif isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names if alias.name.startswith("atlas.rule_engine"))
    return roots


def test_no_file_under_strategy_engine_imports_rule_engine():
    """Sprint 3 through Sprint 5, displacement_volume_context.py was the
    one disclosed exception (importing exactly atlas.rule_engine.models.
    FactResult to read trend_5m directly). Setup Interpretation Sprint 6
    migrated it to consume frame.setup_interpretations instead, removing
    that dependency entirely - Strategy Engine now has zero direct Rule
    Engine imports anywhere, confirmed here rather than assumed from the
    migration report alone."""
    offenders = {}
    for py_file in _STRATEGY_ENGINE_DIR.rglob("*.py"):
        imports = _rule_engine_imports(py_file)
        if imports:
            offenders[py_file.name] = imports
    assert offenders == {}


def _facts_attribute_accesses(file_path: Path) -> int:
    """AST-based, not a substring search: atlas/strategy_engine/models.py's
    own docstring legitimately contains the literal text
    "RuleEngineOutput.facts" while explaining an unrelated design
    precedent (reason_codes/setup_ids' own open-string-tuple shape) - a
    blunt `".facts" in source` check would false-positive on that prose,
    the same docstring-vs-code trap test_setup_interpretation_service.py's
    own _non_docstring_string_constants() helper was written to avoid.
    Counting actual ast.Attribute(attr="facts") nodes only matches real
    code performing the access, never documentation describing it."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "facts")


def test_displacement_volume_context_no_longer_reads_facts_dict_at_all():
    """Sprint 6: the single `.facts.get(...)` call site this test used to
    confirm the exact scope of (Sprint 3 through Sprint 5) is now gone
    entirely - the migrated strategy reads frame.setup_interpretations
    instead."""
    target = _STRATEGY_ENGINE_DIR / "strategies" / "displacement_volume_context.py"
    assert _facts_attribute_accesses(target) == 0


def test_no_strategy_engine_file_reads_rule_engine_output_facts():
    for py_file in _STRATEGY_ENGINE_DIR.rglob("*.py"):
        assert _facts_attribute_accesses(py_file) == 0, f"{py_file} reads .facts directly"


# =====================================================================
# 6. Interpretation sufficiency review
# =====================================================================

def test_setup_interpretation_contract_carries_every_field_the_reference_strategy_needs():
    """Direct proof, not just a written claim: every value
    DisplacementVolumeContext.evaluate() currently reads or emits that a
    migrated version would need is present on SetupInterpretation."""
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    interpretation = _interpretation_for(
        frames[-1].rule_engine_output, frames[-1].setup_engine_output, DISPLACEMENT,
    )
    required_fields = (
        "detected", "direction", "source", "source_fact_ids", "reason_codes",
        "occurred_at", "interpretation_version", "interpretation_fingerprint",
    )
    for field in required_fields:
        assert hasattr(interpretation, field)
        assert getattr(interpretation, field) is not None


# =====================================================================
# 7. Failure-path integration
# =====================================================================

def test_ordinary_flat_trend_market_state_returns_a_domain_output_not_an_error():
    rule_outputs, setup_outputs = _real_outputs(_FLAT_SERIES)
    result = interpret_setups(rule_engine_output=rule_outputs[-1], setup_engine_output=setup_outputs[-1])
    displacement = next(i for i in result if i.setup_id == DISPLACEMENT)
    assert displacement.direction == SetupDirection.AMBIGUOUS
    assert displacement.reason_codes == ("trend_flat",)


def test_ordinary_detected_neutral_vwap_setup_returns_a_domain_output():
    state = _bar(0, _BASE, 100.0, distance_from_vwap_points=5.0, atr=1.0, volume_ratio=2.0)
    rule_outputs, setup_outputs = _real_outputs([state])
    result = interpret_setups(rule_engine_output=rule_outputs[0], setup_engine_output=setup_outputs[0])
    vwap = next(i for i in result if i.setup_id == VWAP_EXTENSION)
    assert vwap.direction == SetupDirection.NEUTRAL
    assert vwap.source == DirectionSource.INTENTIONALLY_NEUTRAL


def test_ordinary_rule_fact_insufficient_data_returns_a_domain_output():
    rule_outputs, setup_outputs = _real_outputs(_SHORT_SERIES)
    result = interpret_setups(rule_engine_output=rule_outputs[-1], setup_engine_output=setup_outputs[-1])
    displacement = next(i for i in result if i.setup_id == DISPLACEMENT)
    assert displacement.direction == SetupDirection.UNAVAILABLE


def test_ordinary_setup_level_insufficient_data_returns_a_domain_output():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES[:3])
    result = interpret_setups(rule_engine_output=rule_outputs[0], setup_engine_output=setup_outputs[0])
    streak = next(i for i in result if i.setup_id == STREAK)
    assert streak.detected is False
    assert streak.direction == SetupDirection.UNAVAILABLE


def test_ordinary_conflicting_liquidity_sides_returns_a_domain_output():
    states = [
        _bar(0, _BASE, 100.0, high=112.0, low=95.0, overnight_high=110.0, overnight_low=90.0),
        _bar(1, _BASE + timedelta(minutes=5), 100.0, high=105.0, low=88.0, overnight_high=110.0, overnight_low=90.0),
        _bar(2, _BASE + timedelta(minutes=10), 100.0, high=104.0, low=94.0, overnight_high=110.0, overnight_low=90.0),
    ]
    rule_outputs, setup_outputs = _real_outputs(states)
    result = interpret_setups(rule_engine_output=rule_outputs[-1], setup_engine_output=setup_outputs[-1])
    sweep = next(i for i in result if i.setup_id == LIQUIDITY_SWEEP)
    assert sweep.direction == SetupDirection.AMBIGUOUS


# --- genuine contract violations: cannot occur from any real pipeline run ---

def test_contract_violation_fact_entirely_absent_fails_explicitly():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    hand_built_rule_output = RuleEngineOutput(
        schema_version=rule_outputs[-1].schema_version, symbol=rule_outputs[-1].symbol,
        timeframe=rule_outputs[-1].timeframe, occurred_at=rule_outputs[-1].occurred_at,
        facts={k: v for k, v in rule_outputs[-1].facts.items() if k != "trend_5m"},  # trend_5m removed entirely
    )
    with pytest.raises(SetupInterpretationMissingFactError):
        interpret_setups(rule_engine_output=hand_built_rule_output, setup_engine_output=setup_outputs[-1])


def test_contract_violation_invalid_trend_value_fails_explicitly():
    from dataclasses import replace

    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    poisoned_trend = replace(rule_outputs[-1].facts["trend_5m"], value="sideways")
    hand_built_rule_output = RuleEngineOutput(
        schema_version=rule_outputs[-1].schema_version, symbol=rule_outputs[-1].symbol,
        timeframe=rule_outputs[-1].timeframe, occurred_at=rule_outputs[-1].occurred_at,
        facts={**rule_outputs[-1].facts, "trend_5m": poisoned_trend},
    )
    with pytest.raises(SetupInterpretationInvalidFactValueError):
        interpret_setups(rule_engine_output=hand_built_rule_output, setup_engine_output=setup_outputs[-1])


def test_contract_violation_unknown_setup_id_fails_explicitly():
    from dataclasses import replace

    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    real_setup_output = setup_outputs[-1]
    renamed = replace(real_setup_output.setups[0], setup_name="a_future_setup_not_yet_interpreted")
    hand_built_setup_output = SetupEngineOutput(
        schema_version=real_setup_output.schema_version, symbol=real_setup_output.symbol,
        timeframe=real_setup_output.timeframe, occurred_at=real_setup_output.occurred_at,
        setups=(renamed,) + real_setup_output.setups[1:],
    )
    with pytest.raises(SetupInterpretationUnknownSetupError):
        interpret_setups(rule_engine_output=rule_outputs[-1], setup_engine_output=hand_built_setup_output)


# =====================================================================
# 8. Determinism review
# =====================================================================

def test_determinism_100_repeated_calls_over_fixed_real_outputs():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    rule_output, setup_output = rule_outputs[-1], setup_outputs[-1]
    results = [
        interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
        for _ in range(100)
    ]
    assert all(result == results[0] for result in results)


def test_determinism_repeated_replay_shaped_sequences():
    frames_first = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    frames_second = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    first = [
        interpret_setups(rule_engine_output=f.rule_engine_output, setup_engine_output=f.setup_engine_output)
        for f in frames_first
    ]
    second = [
        interpret_setups(rule_engine_output=f.rule_engine_output, setup_engine_output=f.setup_engine_output)
        for f in frames_second
    ]
    assert first == second


def test_determinism_reason_code_ordering_is_stable():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    rule_output, setup_output = rule_outputs[-1], setup_outputs[-1]
    for _ in range(50):
        result = interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
        displacement = next(i for i in result if i.setup_id == DISPLACEMENT)
        assert displacement.reason_codes == ("trend_up",)  # never reordered, never a set


def test_determinism_version_and_fingerprint_stable_across_100_calls():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    rule_output, setup_output = rule_outputs[-1], setup_outputs[-1]
    versions = set()
    fingerprints = set()
    for _ in range(100):
        result = interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
        versions.update(i.interpretation_version for i in result)
        fingerprints.update(i.interpretation_fingerprint for i in result)
    assert versions == {_INTERPRETATION_VERSION}
    assert fingerprints == {_INTERPRETATION_FINGERPRINT}


def test_determinism_zero_mutation_across_100_calls():
    rule_outputs, setup_outputs = _real_outputs(_BULLISH_SERIES)
    rule_output, setup_output = rule_outputs[-1], setup_outputs[-1]
    original_facts = dict(rule_output.facts)
    original_setups = tuple(setup_output.setups)
    for _ in range(100):
        interpret_setups(rule_engine_output=rule_output, setup_engine_output=setup_output)
    assert rule_output.facts == original_facts
    assert setup_output.setups == original_setups
