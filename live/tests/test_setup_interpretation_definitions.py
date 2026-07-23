"""
Setup Interpretation Sprint 1. Tests for atlas.setup_interpretation.definitions
- the versioned canonical interpretation ruleset, SETUP_INTERPRETATION_V1.
No interpretation logic is exercised here (Sprint 2's concern) - only the
canonical definition's own structure and immutability.
"""
from dataclasses import FrozenInstanceError

import pytest
from atlas.setup_interpretation import definitions
from atlas.setup_interpretation.definitions import (
    SETUP_INTERPRETATION_V1,
    SetupInterpretationDefinition,
    SetupInterpretationRule,
    SetupInterpretationRuleParams,
)
from atlas.setup_interpretation.models import DirectionSource

_EXPECTED_SETUP_IDS = {
    "displacement_with_volume_confirmation",
    "liquidity_sweep_with_volume_confirmation",
    "sustained_displacement_streak",
    "vwap_extension_with_volume_confirmation",
}


# ---- 12. canonical definition includes all four current setup IDs ----

def test_setup_interpretation_v1_includes_all_four_current_setups():
    rule_setup_ids = {rule.setup_id for rule in SETUP_INTERPRETATION_V1.rules}
    assert rule_setup_ids == _EXPECTED_SETUP_IDS


def test_setup_interpretation_v1_has_no_duplicate_setup_ids():
    rule_setup_ids = [rule.setup_id for rule in SETUP_INTERPRETATION_V1.rules]
    assert len(rule_setup_ids) == len(set(rule_setup_ids))


def test_setup_interpretation_v1_constant_name_matches_its_own_version_string():
    assert SETUP_INTERPRETATION_V1.version == "SETUP_INTERPRETATION_V1"


def test_no_default_star_alias_exists_in_setup_interpretation_definitions():
    default_names = [name for name in dir(definitions) if name.startswith("DEFAULT_")]
    assert default_names == []


# ---- Per-setup rule content, grounded in the approved mapping analysis ----

def _rule_for(setup_id: str) -> SetupInterpretationRule:
    return next(rule for rule in SETUP_INTERPRETATION_V1.rules if rule.setup_id == setup_id)


def test_displacement_with_volume_confirmation_infers_from_trend_5m():
    rule = _rule_for("displacement_with_volume_confirmation")
    assert rule.params.expected_source == DirectionSource.RULE_FACT
    assert rule.params.source_fact_ids == ("trend_5m",)
    assert rule.params.bullish_reason == "trend_up"
    assert rule.params.bearish_reason == "trend_down"
    assert rule.params.ambiguous_policy == "trend_flat"


def test_liquidity_sweep_with_volume_confirmation_reads_direct_setup_evidence():
    rule = _rule_for("liquidity_sweep_with_volume_confirmation")
    assert rule.params.expected_source == DirectionSource.SETUP_EVIDENCE
    assert rule.params.source_fact_ids == ("liquidity_sweep",)
    assert rule.params.bullish_reason == "low_side_liquidity_sweep"
    assert rule.params.bearish_reason == "high_side_liquidity_sweep"
    assert rule.params.ambiguous_policy == "conflicting_sides_in_qualifying_levels"


def test_sustained_displacement_streak_infers_from_trend_5m():
    rule = _rule_for("sustained_displacement_streak")
    assert rule.params.expected_source == DirectionSource.RULE_FACT
    assert rule.params.source_fact_ids == ("trend_5m",)
    assert rule.params.bullish_reason == "trend_up"
    assert rule.params.bearish_reason == "trend_down"


def test_vwap_extension_with_volume_confirmation_is_intentionally_neutral():
    rule = _rule_for("vwap_extension_with_volume_confirmation")
    assert rule.params.expected_source == DirectionSource.INTENTIONALLY_NEUTRAL
    assert rule.params.source_fact_ids == ()
    assert rule.params.bullish_reason == "not_applicable"
    assert rule.params.bearish_reason == "not_applicable"
    assert rule.params.neutral_policy == "always_neutral_when_detected"
    assert rule.params.ambiguous_policy == "not_applicable"


def test_every_rule_shares_the_same_unavailable_policy():
    """The not-detected/insufficient-data policy is uniform across setups -
    a genuinely shared rule, not an oversight."""
    policies = {rule.params.unavailable_policy for rule in SETUP_INTERPRETATION_V1.rules}
    assert policies == {"not_detected_or_source_fact_insufficient_data"}


# ---- 13. definition objects are immutable ----

@pytest.mark.parametrize(
    "make_instance, field_name, new_value",
    [
        pytest.param(
            lambda: SetupInterpretationRuleParams(
                interpretation_mode="x", expected_source=DirectionSource.RULE_FACT,
                source_fact_ids=(), bullish_reason="x", bearish_reason="x",
                neutral_policy="x", ambiguous_policy="x", unavailable_policy="x",
            ),
            "expected_source", DirectionSource.SETUP_EVIDENCE, id="SetupInterpretationRuleParams",
        ),
        pytest.param(
            lambda: SetupInterpretationRule(
                setup_id="x",
                params=SetupInterpretationRuleParams(
                    interpretation_mode="x", expected_source=DirectionSource.RULE_FACT,
                    source_fact_ids=(), bullish_reason="x", bearish_reason="x",
                    neutral_policy="x", ambiguous_policy="x", unavailable_policy="x",
                ),
            ),
            "setup_id", "y", id="SetupInterpretationRule",
        ),
        pytest.param(
            lambda: SetupInterpretationDefinition(version="X", rules=()),
            "version", "Y", id="SetupInterpretationDefinition",
        ),
    ],
)
def test_definition_dataclasses_reject_mutation(make_instance, field_name, new_value):
    instance = make_instance()
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, new_value)


def test_setup_interpretation_v1_rules_tuple_cannot_be_reassigned():
    with pytest.raises(FrozenInstanceError):
        SETUP_INTERPRETATION_V1.rules = ()
