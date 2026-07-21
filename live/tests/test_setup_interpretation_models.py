"""
Setup Interpretation Sprint 1. Tests for atlas.setup_interpretation.models -
SetupDirection, DirectionSource, SetupInterpretation. No interpretation
logic exists yet (Sprint 2) - every instance here is hand-built to prove
the model's own shape and invariants, never produced by evaluating real
RuleEngineOutput/SetupEngineOutput data.
"""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest
from atlas.setup_interpretation.models import DirectionSource, SetupDirection, SetupInterpretation

_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
_VERSION = "SETUP_INTERPRETATION_V1"
_FINGERPRINT = "0123456789abcdef"


def _interpretation(**overrides) -> SetupInterpretation:
    fields = dict(
        occurred_at=_OCCURRED_AT,
        setup_id="displacement_with_volume_confirmation",
        detected=True,
        direction=SetupDirection.BULLISH,
        source=DirectionSource.RULE_FACT,
        source_fact_ids=("trend_5m",),
        reason_codes=(),
        interpretation_version=_VERSION,
        interpretation_fingerprint=_FINGERPRINT,
    )
    fields.update(overrides)
    return SetupInterpretation(**fields)


# ---- 1. enum completeness and exact serialized values ----

def test_setup_direction_has_exactly_the_five_approved_values():
    assert {member.value for member in SetupDirection} == {
        "bullish", "bearish", "neutral", "ambiguous", "unavailable",
    }


def test_direction_source_has_exactly_the_four_approved_values():
    assert {member.value for member in DirectionSource} == {
        "setup_evidence", "rule_fact", "intentionally_neutral", "insufficient_data",
    }


# ---- 2. SetupInterpretation immutability ----

def test_setup_interpretation_is_frozen():
    interpretation = _interpretation()
    with pytest.raises(FrozenInstanceError):
        interpretation.direction = SetupDirection.BEARISH


# ---- 3. valid detected bullish/bearish interpretations ----

def test_valid_bullish_from_rule_fact():
    interpretation = _interpretation(
        direction=SetupDirection.BULLISH, source=DirectionSource.RULE_FACT, detected=True,
    )
    assert interpretation.direction == SetupDirection.BULLISH


def test_valid_bearish_from_setup_evidence():
    interpretation = _interpretation(
        setup_id="liquidity_sweep_with_volume_confirmation",
        direction=SetupDirection.BEARISH, source=DirectionSource.SETUP_EVIDENCE,
        source_fact_ids=("liquidity_sweep",), detected=True,
    )
    assert interpretation.direction == SetupDirection.BEARISH
    assert interpretation.source == DirectionSource.SETUP_EVIDENCE


# ---- 4. valid detected neutral interpretation ----

def test_valid_neutral_from_intentionally_neutral():
    interpretation = _interpretation(
        setup_id="vwap_extension_with_volume_confirmation",
        direction=SetupDirection.NEUTRAL, source=DirectionSource.INTENTIONALLY_NEUTRAL,
        source_fact_ids=(), detected=True,
    )
    assert interpretation.direction == SetupDirection.NEUTRAL
    assert interpretation.source == DirectionSource.INTENTIONALLY_NEUTRAL


# ---- 5. valid detected ambiguous interpretation ----

def test_valid_ambiguous_from_setup_evidence():
    """Conflicting sides in liquidity_sweep's own qualifying evidence."""
    interpretation = _interpretation(
        setup_id="liquidity_sweep_with_volume_confirmation",
        direction=SetupDirection.AMBIGUOUS, source=DirectionSource.SETUP_EVIDENCE,
        source_fact_ids=("liquidity_sweep",), detected=True,
    )
    assert interpretation.direction == SetupDirection.AMBIGUOUS


def test_valid_ambiguous_from_rule_fact():
    """A flat trend_5m reading for a MOMENTUM-family setup - AMBIGUOUS
    must not be over-constrained to only one source."""
    interpretation = _interpretation(
        direction=SetupDirection.AMBIGUOUS, source=DirectionSource.RULE_FACT,
        source_fact_ids=("trend_5m",), detected=True,
    )
    assert interpretation.direction == SetupDirection.AMBIGUOUS


# ---- 6. valid undetected/unavailable interpretation ----

def test_valid_unavailable_when_not_detected():
    interpretation = _interpretation(
        detected=False, direction=SetupDirection.UNAVAILABLE, source=DirectionSource.INSUFFICIENT_DATA,
        source_fact_ids=(),
    )
    assert interpretation.detected is False
    assert interpretation.direction == SetupDirection.UNAVAILABLE
    assert interpretation.source == DirectionSource.INSUFFICIENT_DATA


# ---- 7. invalid UNAVAILABLE/source combinations ----

def test_unavailable_direction_with_non_insufficient_data_source_raises():
    with pytest.raises(ValueError, match="UNAVAILABLE requires source=INSUFFICIENT_DATA"):
        _interpretation(
            detected=False, direction=SetupDirection.UNAVAILABLE, source=DirectionSource.RULE_FACT,
        )


def test_insufficient_data_source_with_non_unavailable_direction_raises():
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA requires direction=UNAVAILABLE"):
        _interpretation(
            detected=False, direction=SetupDirection.NEUTRAL, source=DirectionSource.INSUFFICIENT_DATA,
        )


# ---- 8. invalid INTENTIONALLY_NEUTRAL combinations ----

def test_intentionally_neutral_source_with_non_neutral_direction_raises():
    with pytest.raises(ValueError, match="INTENTIONALLY_NEUTRAL requires direction=NEUTRAL"):
        _interpretation(
            setup_id="vwap_extension_with_volume_confirmation",
            direction=SetupDirection.BULLISH, source=DirectionSource.INTENTIONALLY_NEUTRAL,
            detected=True,
        )


# ---- 9. invalid detected=False directional interpretations ----

def test_detected_false_with_bullish_direction_and_evidence_backed_source_raises():
    """source=RULE_FACT is evidence-backed, so the "evidence-backed source
    requires detected=True" check fires first - still a correct rejection
    of the same underlying invalid state (see the dedicated
    detected_false_with_evidence_backed_source test below for that check
    in isolation)."""
    with pytest.raises(ValueError, match="requires detected=True"):
        _interpretation(detected=False, direction=SetupDirection.BULLISH, source=DirectionSource.RULE_FACT)


def test_detected_false_with_internally_consistent_but_wrong_direction_source_pair_raises():
    """Isolates the detected=False check itself: direction=NEUTRAL/
    source=INTENTIONALLY_NEUTRAL is an otherwise-valid pairing, so this
    can only be rejected by the detected=False rule, not by an earlier
    source/direction pairing check."""
    with pytest.raises(ValueError, match="detected=False requires"):
        _interpretation(
            setup_id="vwap_extension_with_volume_confirmation",
            detected=False, direction=SetupDirection.NEUTRAL, source=DirectionSource.INTENTIONALLY_NEUTRAL,
            source_fact_ids=(),
        )


def test_detected_false_with_evidence_backed_source_raises():
    with pytest.raises(ValueError, match="requires detected=True"):
        _interpretation(
            detected=False, direction=SetupDirection.BULLISH, source=DirectionSource.SETUP_EVIDENCE,
        )


def test_bullish_or_bearish_with_intentionally_neutral_source_raises():
    """BULLISH/BEARISH can never legitimately pair with
    INTENTIONALLY_NEUTRAL - not via a separate direction-side check, but
    as a direct consequence of source=INTENTIONALLY_NEUTRAL already
    requiring direction=NEUTRAL (see this model's own docstring)."""
    with pytest.raises(ValueError, match="INTENTIONALLY_NEUTRAL requires direction=NEUTRAL"):
        _interpretation(direction=SetupDirection.BEARISH, source=DirectionSource.INTENTIONALLY_NEUTRAL, detected=True)


def test_bullish_or_bearish_with_insufficient_data_source_raises():
    """Same reasoning as above, via source=INSUFFICIENT_DATA already
    requiring direction=UNAVAILABLE."""
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA requires direction=UNAVAILABLE"):
        _interpretation(direction=SetupDirection.BULLISH, source=DirectionSource.INSUFFICIENT_DATA, detected=True)


# ---- 10. blank identity/version/fingerprint rejection ----

def test_blank_setup_id_raises():
    with pytest.raises(ValueError, match="setup_id"):
        _interpretation(setup_id="   ")


def test_blank_interpretation_version_raises():
    with pytest.raises(ValueError, match="interpretation_version"):
        _interpretation(interpretation_version="")


def test_blank_interpretation_fingerprint_raises():
    with pytest.raises(ValueError, match="interpretation_fingerprint"):
        _interpretation(interpretation_fingerprint="")


# ---- 11. tuple immutability and stable ordering ----

def test_source_fact_ids_preserve_supplied_order():
    interpretation = _interpretation(source_fact_ids=("trend_5m", "displacement"))
    assert interpretation.source_fact_ids == ("trend_5m", "displacement")  # never sorted


def test_reason_codes_preserve_supplied_order():
    interpretation = _interpretation(reason_codes=("third", "first", "second"))
    assert interpretation.reason_codes == ("third", "first", "second")


def test_source_fact_ids_field_cannot_be_reassigned():
    interpretation = _interpretation()
    with pytest.raises(FrozenInstanceError):
        interpretation.source_fact_ids = ("something_else",)


def test_repeated_construction_with_identical_inputs_is_equal_and_deterministic():
    a = _interpretation()
    b = _interpretation()
    assert a is not b
    assert a == b
