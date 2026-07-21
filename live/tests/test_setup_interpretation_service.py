"""
Setup Interpretation Sprint 2. Tests for
atlas.setup_interpretation.service.interpret_setups() - the pure service
applying SETUP_INTERPRETATION_V1's canonical rules to a real
RuleEngineOutput/SetupEngineOutput pair. Every fixture here is built from
real project model constructors, not loose mocks.
"""
import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest
from atlas.rule_engine.models import FactResult, RuleEngineOutput
from atlas.rule_engine.models import InsufficientData as FactInsufficientData
from atlas.setup_engine.models import InsufficientData as SetupInsufficientData
from atlas.setup_engine.models import SetupEngineOutput, SetupEvidence, SetupResult, Severity
from atlas.setup_interpretation.definitions import SETUP_INTERPRETATION_V1
from atlas.setup_interpretation.fingerprint import compute_fingerprint
from atlas.setup_interpretation.models import DirectionSource, SetupDirection
from atlas.setup_interpretation.service import (
    SetupInterpretationAlignmentError,
    SetupInterpretationInvalidFactValueError,
    SetupInterpretationMissingFactError,
    SetupInterpretationUnknownSetupError,
    interpret_setups,
)

_OCCURRED_AT_STR = "2026-07-21T12:00:00+00:00"
_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
_VERSION = SETUP_INTERPRETATION_V1.version
_FINGERPRINT = compute_fingerprint(SETUP_INTERPRETATION_V1)

DISPLACEMENT = "displacement_with_volume_confirmation"
LIQUIDITY_SWEEP = "liquidity_sweep_with_volume_confirmation"
STREAK = "sustained_displacement_streak"
VWAP_EXTENSION = "vwap_extension_with_volume_confirmation"


def _rule_engine_output(facts=None, occurred_at=_OCCURRED_AT_STR) -> RuleEngineOutput:
    return RuleEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at, facts=facts or {},
    )


def _setup_engine_output(setups=(), occurred_at=_OCCURRED_AT_STR) -> SetupEngineOutput:
    return SetupEngineOutput(
        schema_version="1.0", symbol="MNQU6", timeframe="5m", occurred_at=occurred_at, setups=tuple(setups),
    )


def _setup_result(setup_name: str, detected: bool = True) -> SetupResult:
    return SetupResult(
        setup_name=setup_name, definition_version="1.0", detected=detected,
        severity=Severity.NORMAL if detected else None, evidence=SetupEvidence(supporting_facts=()),
    )


def _setup_insufficient(setup_name: str) -> SetupInsufficientData:
    return SetupInsufficientData(setup_name=setup_name, definition_version="1.0", reason="no history")


def _trend_fact(value: str) -> FactResult:
    return FactResult(fact_name="trend_5m", definition_version="1.0", value=value, evidence={})


def _trend_insufficient() -> FactInsufficientData:
    return FactInsufficientData(fact_name="trend_5m", definition_version="1.0", reason="fewer than 20 bars")


def _liquidity_sweep_fact(sides: list) -> FactResult:
    qualifying_levels = [
        {
            "reference_level": f"level_{i}", "side": side, "level": 100.0, "excursion": 101.0,
            "excursion_occurred_at": _OCCURRED_AT_STR, "close": 99.0,
        }
        for i, side in enumerate(sides)
    ]
    return FactResult(
        fact_name="liquidity_sweep", definition_version="1.0", value=len(qualifying_levels) > 0,
        evidence={"window_size": 3, "qualifying_levels": qualifying_levels},
    )


def _liquidity_sweep_insufficient() -> FactInsufficientData:
    return FactInsufficientData(fact_name="liquidity_sweep", definition_version="1.0", reason="fewer than 3 bars")


# ---- 1/2/3. one interpretation per setup, ordering preserved, dense output ----

def test_one_interpretation_per_setup_outcome_in_order():
    setups = (
        _setup_result(DISPLACEMENT),
        _setup_result(LIQUIDITY_SWEEP, detected=False),
        _setup_result(STREAK),
        _setup_result(VWAP_EXTENSION),
    )
    rule_engine_output = _rule_engine_output(facts={
        "trend_5m": _trend_fact("up"),
        "liquidity_sweep": _liquidity_sweep_fact(["high"]),
    })
    setup_engine_output = _setup_engine_output(setups=setups)

    result = interpret_setups(rule_engine_output=rule_engine_output, setup_engine_output=setup_engine_output)

    assert len(result) == 4
    assert [interp.setup_id for interp in result] == [s.setup_name for s in setups]


def test_dense_output_including_not_detected_and_insufficient_data_setups():
    setups = (
        _setup_result(DISPLACEMENT, detected=False),
        _setup_insufficient(LIQUIDITY_SWEEP),
        _setup_result(STREAK),
        _setup_result(VWAP_EXTENSION),
    )
    rule_engine_output = _rule_engine_output(facts={"trend_5m": _trend_fact("up")})
    setup_engine_output = _setup_engine_output(setups=setups)

    result = interpret_setups(rule_engine_output=rule_engine_output, setup_engine_output=setup_engine_output)

    assert len(result) == 4  # never a shorter list, even with two non-detected entries
    assert [interp.detected for interp in result] == [False, False, True, True]


def test_empty_setup_engine_output_produces_empty_tuple():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(), setup_engine_output=_setup_engine_output(setups=()),
    )
    assert result == ()


# ---- 1/2/4. all four mappings, with definition-owned success reasons ----

def test_displacement_maps_from_trend_5m_bullish():
    """"up" -> BULLISH, with the definition-owned "trend_up" reason code -
    Correction 2: never the generic hardcoded "accepted"."""
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("up")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
    )
    assert result[0].direction == SetupDirection.BULLISH
    assert result[0].source == DirectionSource.RULE_FACT
    assert result[0].source_fact_ids == ("trend_5m",)
    assert result[0].reason_codes == ("trend_up",)


def test_displacement_maps_from_trend_5m_bearish():
    """"down" -> BEARISH, with the definition-owned "trend_down" reason code."""
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("down")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
    )
    assert result[0].direction == SetupDirection.BEARISH
    assert result[0].reason_codes == ("trend_down",)


def test_sustained_displacement_streak_maps_from_trend_5m():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("up")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(STREAK)]),
    )
    assert result[0].direction == SetupDirection.BULLISH
    assert result[0].source == DirectionSource.RULE_FACT
    assert result[0].source_fact_ids == ("trend_5m",)


def test_liquidity_sweep_maps_from_evidence_side_bearish_on_high_side():
    """6. High-side sweep uses its definition-owned success reason,
    "high_side_liquidity_sweep" - never the generic "accepted"."""
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"liquidity_sweep": _liquidity_sweep_fact(["high"])}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(LIQUIDITY_SWEEP)]),
    )
    assert result[0].direction == SetupDirection.BEARISH
    assert result[0].source == DirectionSource.SETUP_EVIDENCE
    assert result[0].source_fact_ids == ("liquidity_sweep",)
    assert result[0].reason_codes == ("high_side_liquidity_sweep",)


def test_liquidity_sweep_maps_from_evidence_side_bullish_on_low_side():
    """7. Low-side sweep uses its definition-owned success reason,
    "low_side_liquidity_sweep"."""
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"liquidity_sweep": _liquidity_sweep_fact(["low"])}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(LIQUIDITY_SWEEP)]),
    )
    assert result[0].direction == SetupDirection.BULLISH
    assert result[0].reason_codes == ("low_side_liquidity_sweep",)


def test_vwap_extension_is_always_neutral_intentionally_neutral():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(VWAP_EXTENSION)]),
    )
    assert result[0].direction == SetupDirection.NEUTRAL
    assert result[0].source == DirectionSource.INTENTIONALLY_NEUTRAL
    assert result[0].source_fact_ids == ()


# ---- 5. missing setup (architecture gap) ----

def test_unregistered_setup_id_raises_unknown_setup_error():
    setups = [_setup_result("some_future_setup_with_no_interpretation_rule")]
    with pytest.raises(SetupInterpretationUnknownSetupError, match="some_future_setup_with_no_interpretation_rule"):
        interpret_setups(
            rule_engine_output=_rule_engine_output(), setup_engine_output=_setup_engine_output(setups=setups),
        )


# ---- 6. missing required fact (architecture gap) ----

def test_trend_5m_entirely_absent_raises_missing_fact_error():
    result_setups = [_setup_result(DISPLACEMENT)]
    with pytest.raises(SetupInterpretationMissingFactError, match="trend_5m"):
        interpret_setups(
            rule_engine_output=_rule_engine_output(facts={}),  # trend_5m key entirely absent
            setup_engine_output=_setup_engine_output(setups=result_setups),
        )


def test_liquidity_sweep_entirely_absent_raises_missing_fact_error():
    with pytest.raises(SetupInterpretationMissingFactError, match="liquidity_sweep"):
        interpret_setups(
            rule_engine_output=_rule_engine_output(facts={}),
            setup_engine_output=_setup_engine_output(setups=[_setup_result(LIQUIDITY_SWEEP)]),
        )


def test_source_fact_insufficient_data_yields_unavailable_not_an_error():
    """Distinct from the entirely-absent case above: the fact WAS
    evaluated, it just couldn't be computed - an expected, ordinary
    outcome, not an architecture gap."""
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_insufficient()}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
    )
    assert result[0].direction == SetupDirection.UNAVAILABLE
    assert result[0].source == DirectionSource.INSUFFICIENT_DATA
    assert result[0].detected is True
    assert result[0].reason_codes == ("not_detected_or_source_fact_insufficient_data",)


def test_liquidity_sweep_source_fact_insufficient_data_yields_unavailable():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"liquidity_sweep": _liquidity_sweep_insufficient()}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(LIQUIDITY_SWEEP)]),
    )
    assert result[0].direction == SetupDirection.UNAVAILABLE
    assert result[0].source == DirectionSource.INSUFFICIENT_DATA


# ---- 7. flat trend ----

def test_flat_trend_yields_ambiguous_for_displacement():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("flat")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
    )
    assert result[0].direction == SetupDirection.AMBIGUOUS
    assert result[0].source == DirectionSource.RULE_FACT
    assert result[0].reason_codes == ("trend_flat",)


def test_flat_trend_yields_ambiguous_for_sustained_displacement_streak():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("flat")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(STREAK)]),
    )
    assert result[0].direction == SetupDirection.AMBIGUOUS
    assert result[0].reason_codes == ("trend_flat",)


# ---- Correction 1: invalid trend_5m values fail loudly, never AMBIGUOUS ----

@pytest.mark.parametrize(
    "invalid_value",
    [None, "", "sideways", "UP", "Down", "Flat", " up", "up ", 1, True, 0.5, ("up",)],
    ids=["none", "empty_string", "sideways", "upper_UP", "mixed_Down", "mixed_Flat",
         "leading_space", "trailing_space", "int", "bool", "float", "tuple"],
)
def test_every_unrecognized_trend_value_raises_invalid_fact_value_error(invalid_value):
    """4/5. Anything outside the exact "up"/"down"/"flat" contract is an
    upstream contract violation - never silently coerced, normalized
    (case, whitespace), or reinterpreted as AMBIGUOUS."""
    with pytest.raises(SetupInterpretationInvalidFactValueError, match="trend_5m"):
        interpret_setups(
            rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact(invalid_value)}),
            setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
        )


def test_invalid_trend_value_error_applies_to_sustained_displacement_streak_too():
    with pytest.raises(SetupInterpretationInvalidFactValueError, match="trend_5m"):
        interpret_setups(
            rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("sideways")}),
            setup_engine_output=_setup_engine_output(setups=[_setup_result(STREAK)]),
        )


def test_invalid_trend_value_error_message_includes_the_offending_value():
    with pytest.raises(SetupInterpretationInvalidFactValueError, match=r"got 'sideways'"):
        interpret_setups(
            rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("sideways")}),
            setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
        )


# ---- 8. conflicting liquidity sides ----

def test_conflicting_sides_yields_ambiguous_for_liquidity_sweep():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"liquidity_sweep": _liquidity_sweep_fact(["high", "low"])}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(LIQUIDITY_SWEEP)]),
    )
    assert result[0].direction == SetupDirection.AMBIGUOUS
    assert result[0].source == DirectionSource.SETUP_EVIDENCE
    assert result[0].reason_codes == ("conflicting_sides_in_qualifying_levels",)


# ---- 9. neutral VWAP (already covered above, additional detected=False case) ----

def test_vwap_extension_not_detected_is_unavailable_not_neutral():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(VWAP_EXTENSION, detected=False)]),
    )
    assert result[0].direction == SetupDirection.UNAVAILABLE
    assert result[0].source == DirectionSource.INSUFFICIENT_DATA
    assert result[0].detected is False


# ---- 10/11. version and fingerprint propagation ----

def test_interpretation_version_propagated_from_canonical_definition():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("up")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
    )
    assert result[0].interpretation_version == _VERSION == "SETUP_INTERPRETATION_V1"


def test_interpretation_fingerprint_propagated_from_canonical_definition():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("up")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
    )
    assert result[0].interpretation_fingerprint == _FINGERPRINT


def test_version_and_fingerprint_are_identical_across_every_setup_in_one_call():
    setups = (
        _setup_result(DISPLACEMENT, detected=False),
        _setup_result(LIQUIDITY_SWEEP, detected=False),
        _setup_result(STREAK, detected=False),
        _setup_result(VWAP_EXTENSION),
    )
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(), setup_engine_output=_setup_engine_output(setups=setups),
    )
    assert {r.interpretation_version for r in result} == {_VERSION}
    assert {r.interpretation_fingerprint for r in result} == {_FINGERPRINT}


# ---- 12. determinism across repeated runs ----

def test_determinism_across_100_repeated_runs():
    rule_engine_output = _rule_engine_output(facts={
        "trend_5m": _trend_fact("up"), "liquidity_sweep": _liquidity_sweep_fact(["high", "low"]),
    })
    setup_engine_output = _setup_engine_output(setups=[
        _setup_result(DISPLACEMENT), _setup_result(LIQUIDITY_SWEEP), _setup_result(STREAK, detected=False),
        _setup_result(VWAP_EXTENSION),
    ])
    results = [
        interpret_setups(rule_engine_output=rule_engine_output, setup_engine_output=setup_engine_output)
        for _ in range(100)
    ]
    assert all(result == results[0] for result in results)


# ---- 13. no recomputation ----

def test_no_market_state_or_ohlc_is_ever_required():
    """No fixture in this file ever constructs a MarketState - proof that
    interpret_setups needs only already-computed RuleEngineOutput/
    SetupEngineOutput fields, never raw price data."""
    import atlas.setup_interpretation.service as service_module

    source = Path(service_module.__file__).read_text(encoding="utf-8")
    assert "MarketState" not in source
    assert ".open" not in source and ".close" not in source and ".high" not in source and ".low" not in source


# ---- 14. no mutation ----

def test_rule_engine_output_and_setup_engine_output_are_not_mutated():
    rule_engine_output = _rule_engine_output(facts={"trend_5m": _trend_fact("up")})
    setup_engine_output = _setup_engine_output(setups=[_setup_result(DISPLACEMENT)])
    original_facts = dict(rule_engine_output.facts)
    original_setups = tuple(setup_engine_output.setups)

    interpret_setups(rule_engine_output=rule_engine_output, setup_engine_output=setup_engine_output)

    assert rule_engine_output.facts == original_facts
    assert setup_engine_output.setups == original_setups


# ---- Correction 2: no independently hardcoded output reason codes ----

def _non_docstring_string_constants(file_path: Path) -> set:
    """Every string literal used as an actual CODE value in file_path -
    deliberately excluding module/class/function docstrings, so prose
    that merely DISCUSSES a string (e.g. explaining a past hardcoding
    mistake and its fix) doesn't false-positive against a check for that
    string being used as a real value."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    docstring_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (
                node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                docstring_ids.add(id(node.body[0].value))

    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_ids
    }


def test_service_module_contains_no_hardcoded_output_reason_code_literals():
    """9. Every reason code service.py can emit must be READ from
    rule.params (bullish_reason/bearish_reason/neutral_policy/
    ambiguous_policy/unavailable_policy) - never hardcoded as a second,
    independently-drifting string literal used as an actual value in this
    module. Confirms the old "accepted" literal is gone, and that none of
    the four current definition-owned success-reason strings appear as a
    real value here either (only as attribute reads off `rule.params`) -
    checked against non-docstring string constants only, so this module's
    own explanatory prose (which legitimately discusses the old "accepted"
    literal by name) doesn't false-positive the check."""
    import atlas.setup_interpretation.service as service_module

    constants = _non_docstring_string_constants(Path(service_module.__file__))

    assert "accepted" not in constants
    for literal in ("trend_up", "trend_down", "high_side_liquidity_sweep", "low_side_liquidity_sweep"):
        assert literal not in constants, f"{literal!r} must be read from rule.params, not hardcoded in service.py"


def test_all_success_reason_codes_present_in_a_full_run_come_from_the_canonical_definition():
    """Cross-checks every BULLISH/BEARISH result's reason_codes against
    SETUP_INTERPRETATION_V1's own rules directly - proof the service
    reads them, rather than merely proof the literals are textually
    absent from the source file."""
    rule_engine_output = _rule_engine_output(facts={
        "trend_5m": _trend_fact("up"), "liquidity_sweep": _liquidity_sweep_fact(["low"]),
    })
    setup_engine_output = _setup_engine_output(
        setups=[_setup_result(DISPLACEMENT), _setup_result(LIQUIDITY_SWEEP)],
    )
    result = interpret_setups(rule_engine_output=rule_engine_output, setup_engine_output=setup_engine_output)

    rules_by_id = {rule.setup_id: rule for rule in SETUP_INTERPRETATION_V1.rules}
    for interpretation in result:
        rule = rules_by_id[interpretation.setup_id]
        expected = rule.params.bullish_reason if interpretation.direction == SetupDirection.BULLISH else None
        assert interpretation.reason_codes == (expected,)


# ---- Bonus: alignment check ----

def test_mismatched_occurred_at_raises_alignment_error():
    rule_engine_output = _rule_engine_output(occurred_at="2026-07-21T12:00:00+00:00")
    setup_engine_output = _setup_engine_output(occurred_at="2026-07-21T12:05:00+00:00")
    with pytest.raises(SetupInterpretationAlignmentError):
        interpret_setups(rule_engine_output=rule_engine_output, setup_engine_output=setup_engine_output)


def test_occurred_at_is_correctly_parsed_onto_every_interpretation():
    result = interpret_setups(
        rule_engine_output=_rule_engine_output(facts={"trend_5m": _trend_fact("up")}),
        setup_engine_output=_setup_engine_output(setups=[_setup_result(DISPLACEMENT)]),
    )
    assert result[0].occurred_at == _OCCURRED_AT


# ---- 15. dependency audit ----

_SERVICE_MODULE = Path(__file__).resolve().parent.parent / "atlas" / "setup_interpretation" / "service.py"

_ALLOWED_ATLAS_IMPORTS = frozenset({
    "atlas.rule_engine.models",
    "atlas.setup_engine.models",
    "atlas.setup_interpretation.definitions",
    "atlas.setup_interpretation.fingerprint",
    "atlas.setup_interpretation.models",
})

_FORBIDDEN_PREFIXES = (
    "atlas.market_engine", "atlas.replay_engine", "atlas.market_context", "atlas.strategy_engine",
    "atlas.repositories", "atlas.api", "atlas.events", "atlas.research", "atlas.research_export",
    "atlas.execution", "atlas.paper_trading", "atlas.brokers", "atlas.services",
    "atlas.rule_engine.service", "atlas.rule_engine.facts", "atlas.rule_engine.registry",
    "atlas.setup_engine.service", "atlas.setup_engine.registry", "atlas.setup_engine.registration",
)


def _imported_module_roots(file_path: Path) -> set:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    return roots


def test_dependency_audit_only_approved_atlas_modules_are_imported():
    atlas_imports = {name for name in _imported_module_roots(_SERVICE_MODULE) if name.startswith("atlas.")}
    assert atlas_imports <= _ALLOWED_ATLAS_IMPORTS, f"unexpected imports: {atlas_imports - _ALLOWED_ATLAS_IMPORTS}"


def test_dependency_audit_no_forbidden_package_is_imported():
    atlas_imports = {name for name in _imported_module_roots(_SERVICE_MODULE) if name.startswith("atlas.")}
    for name in atlas_imports:
        assert not name.startswith(_FORBIDDEN_PREFIXES), f"forbidden import: {name}"


def test_dependency_audit_rule_engine_dependency_is_limited_to_models_only():
    imported = _imported_module_roots(_SERVICE_MODULE)
    rule_engine_imports = {name for name in imported if name.startswith("atlas.rule_engine")}
    assert rule_engine_imports == {"atlas.rule_engine.models"}


def test_dependency_audit_setup_engine_dependency_is_limited_to_models_only():
    imported = _imported_module_roots(_SERVICE_MODULE)
    setup_engine_imports = {name for name in imported if name.startswith("atlas.setup_engine")}
    assert setup_engine_imports == {"atlas.setup_engine.models"}


def test_dependency_audit_no_async_or_repository_constructs():
    source = _SERVICE_MODULE.read_text(encoding="utf-8")
    assert "async def" not in source
    assert "Repository" not in source
