"""
Setup Interpretation Sprint 1. Tests for atlas.setup_interpretation.fingerprint
and its use over SETUP_INTERPRETATION_V1 - a self-contained canonical
hashing helper, independent from atlas.market_context.fingerprint.
"""
from datetime import datetime, timezone
from enum import Enum

from atlas.setup_interpretation.definitions import (
    SETUP_INTERPRETATION_V1,
    SetupInterpretationDefinition,
    SetupInterpretationRule,
    SetupInterpretationRuleParams,
)
from atlas.setup_interpretation.fingerprint import canonical_json, compute_fingerprint, to_canonical
from atlas.setup_interpretation.models import DirectionSource


class _Color(str, Enum):
    RED = "red"


def _rule_params(**overrides):
    fields = dict(
        interpretation_mode="inferred_from_external_rule_fact",
        expected_source=DirectionSource.RULE_FACT,
        source_fact_ids=("trend_5m",),
        bullish_reason="trend_up",
        bearish_reason="trend_down",
        neutral_policy="not_applicable",
        ambiguous_policy="trend_flat",
        unavailable_policy="not_detected_or_source_fact_insufficient_data",
    )
    fields.update(overrides)
    return SetupInterpretationRuleParams(**fields)


def _definition(version="SETUP_INTERPRETATION_V1", rule_params=None):
    rule_params = rule_params or _rule_params()
    return SetupInterpretationDefinition(
        version=version,
        rules=(SetupInterpretationRule(setup_id="displacement_with_volume_confirmation", params=rule_params),),
    )


# ---- 14. fingerprint determinism ----

def test_repeated_fingerprint_of_setup_interpretation_v1_is_identical():
    fingerprints = {compute_fingerprint(SETUP_INTERPRETATION_V1) for _ in range(100)}
    assert len(fingerprints) == 1


def test_same_values_in_separately_created_definitions_produce_the_same_fingerprint():
    a = _definition()
    b = _definition()
    assert a is not b
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_fingerprint_output_is_16_lowercase_hex_characters():
    fp = compute_fingerprint(SETUP_INTERPRETATION_V1)
    assert len(fp) == 16
    assert fp == fp.lower()
    assert all(c in "0123456789abcdef" for c in fp)


# ---- 15. fingerprint stable under mapping insertion-order differences ----

def test_mapping_insertion_order_does_not_affect_canonical_serialization_or_fingerprint():
    first = {"b": 2, "a": 1, "c": 3}
    second = {"c": 3, "a": 1, "b": 2}
    assert list(first.keys()) != list(second.keys())
    assert canonical_json(first) == canonical_json(second)
    assert compute_fingerprint(first) == compute_fingerprint(second)


def test_rule_field_declaration_order_does_not_affect_fingerprint():
    """Two SetupInterpretationRuleParams built with keyword arguments given
    in a different order must still fingerprint identically - sort_keys=True
    makes declaration/call order irrelevant."""
    a = SetupInterpretationRuleParams(
        interpretation_mode="m", expected_source=DirectionSource.RULE_FACT, source_fact_ids=("x",),
        bullish_reason="bu", bearish_reason="be",
        neutral_policy="n", ambiguous_policy="a", unavailable_policy="u",
    )
    b = SetupInterpretationRuleParams(
        unavailable_policy="u", ambiguous_policy="a", neutral_policy="n",
        bearish_reason="be", bullish_reason="bu",
        source_fact_ids=("x",), expected_source=DirectionSource.RULE_FACT, interpretation_mode="m",
    )
    assert compute_fingerprint(a) == compute_fingerprint(b)


# ---- 16. fingerprint changes when any semantic field changes ----

def test_fingerprint_changes_when_expected_source_changes():
    base = _definition(rule_params=_rule_params(expected_source=DirectionSource.RULE_FACT))
    changed = _definition(rule_params=_rule_params(expected_source=DirectionSource.SETUP_EVIDENCE))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_source_fact_ids_change():
    base = _definition(rule_params=_rule_params(source_fact_ids=("trend_5m",)))
    changed = _definition(rule_params=_rule_params(source_fact_ids=("trend_5m", "displacement")))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_bullish_reason_changes():
    """Correction 2: the successful-directional reason codes are
    definition-owned and therefore fingerprinted, exactly like the other
    three outcome policies - a change here must be just as detectable."""
    base = _definition(rule_params=_rule_params(bullish_reason="trend_up"))
    changed = _definition(rule_params=_rule_params(bullish_reason="something_else"))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_bearish_reason_changes():
    base = _definition(rule_params=_rule_params(bearish_reason="trend_down"))
    changed = _definition(rule_params=_rule_params(bearish_reason="something_else"))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_ambiguous_policy_changes():
    base = _definition(rule_params=_rule_params(ambiguous_policy="trend_flat"))
    changed = _definition(rule_params=_rule_params(ambiguous_policy="something_else"))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_neutral_policy_changes():
    base = _definition(rule_params=_rule_params(neutral_policy="not_applicable"))
    changed = _definition(rule_params=_rule_params(neutral_policy="always_neutral_when_detected"))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_unavailable_policy_changes():
    base = _definition(rule_params=_rule_params(unavailable_policy="a"))
    changed = _definition(rule_params=_rule_params(unavailable_policy="b"))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_interpretation_mode_changes_even_though_expected_source_is_the_same():
    """interpretation_mode is a descriptive string, not just a restatement
    of expected_source - a change to it alone must still be detectable."""
    base = _definition(rule_params=_rule_params(interpretation_mode="inferred_from_external_rule_fact"))
    changed = _definition(rule_params=_rule_params(interpretation_mode="a_different_description"))
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_fingerprint_changes_when_a_setup_is_added_or_removed():
    one_rule = _definition()
    two_rules = SetupInterpretationDefinition(
        version="SETUP_INTERPRETATION_V1",
        rules=one_rule.rules + (
            SetupInterpretationRule(setup_id="liquidity_sweep_with_volume_confirmation", params=_rule_params()),
        ),
    )
    assert compute_fingerprint(one_rule) != compute_fingerprint(two_rules)


# ---- 17. fingerprint changes when version changes ----

def test_fingerprint_changes_when_version_changes_even_with_identical_rules():
    a = _definition(version="SETUP_INTERPRETATION_V1")
    b = _definition(version="SETUP_INTERPRETATION_V2")
    assert compute_fingerprint(a) != compute_fingerprint(b)


# ---- Supplementary coverage, mirroring market_context.fingerprint's own suite ----

def test_enum_serializes_by_value_deterministically():
    assert to_canonical(_Color.RED) == "red"
    assert to_canonical(DirectionSource.RULE_FACT) == "rule_fact"
    assert compute_fingerprint(DirectionSource.RULE_FACT) == compute_fingerprint("rule_fact")


def test_datetime_serializes_deterministically_via_iso_8601():
    dt = datetime(2026, 7, 21, 12, 30, 0, tzinfo=timezone.utc)
    assert to_canonical(dt) == dt.isoformat()


def test_lists_and_tuples_preserve_order_rather_than_being_sorted():
    ordered = ["trend_5m", "displacement"]
    assert to_canonical(ordered) == ["trend_5m", "displacement"]
    assert to_canonical(tuple(ordered)) == ["trend_5m", "displacement"]
    assert compute_fingerprint(("a", "b")) != compute_fingerprint(("b", "a"))


def test_output_does_not_depend_on_python_object_identity():
    a = _rule_params()
    b = _rule_params()
    assert a is not b
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_no_import_from_market_context_fingerprint():
    """This module's own docstring commits to independence from
    atlas.market_context.fingerprint - confirmed here directly, not only
    via the separate dependency-audit test file."""
    import inspect

    import atlas.setup_interpretation.fingerprint as own_module

    source = inspect.getsource(own_module)
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    assert not any("market_context" in line for line in import_lines)
