"""
Phase N3, Sprint 1. Tests for atlas.strategy_engine.models -
StrategyDirection, StrategyDisposition, StrategyDecision. No concrete
strategy exists yet - every decision here is hand-built, not produced by
evaluating a real trading idea.
"""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest
from atlas.core.primitives import Price
from atlas.strategy_engine.models import StrategyDecision, StrategyDirection, StrategyDisposition

_OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
_FINGERPRINT = "0123456789abcdef"


def _decision(**overrides) -> StrategyDecision:
    fields = dict(
        occurred_at=_OCCURRED_AT, strategy_id="momentum_stub", strategy_version="MOMENTUM_STUB_V1",
        disposition=StrategyDisposition.CANDIDATE, direction=StrategyDirection.LONG,
        setup_ids=("displacement_with_volume_confirmation",), reason_codes=(),
        context_fingerprint=_FINGERPRINT,
    )
    fields.update(overrides)
    return StrategyDecision(**fields)


# ---- enum completeness ----

def test_strategy_direction_has_exactly_long_short_flat():
    assert {member.value for member in StrategyDirection} == {"long", "short", "flat"}


def test_strategy_disposition_has_exactly_candidate_rejected_no_signal():
    assert {member.value for member in StrategyDisposition} == {"candidate", "rejected", "no_signal"}


# ---- immutability ----

def test_strategy_decision_is_frozen():
    decision = _decision()
    with pytest.raises(FrozenInstanceError):
        decision.direction = StrategyDirection.SHORT


# ---- valid CANDIDATE ----

def test_valid_candidate_decision_long():
    decision = _decision(disposition=StrategyDisposition.CANDIDATE, direction=StrategyDirection.LONG, setup_ids=("a",))
    assert decision.disposition == StrategyDisposition.CANDIDATE
    assert decision.direction == StrategyDirection.LONG


def test_valid_candidate_decision_short():
    decision = _decision(disposition=StrategyDisposition.CANDIDATE, direction=StrategyDirection.SHORT, setup_ids=("a",))
    assert decision.direction == StrategyDirection.SHORT


# ---- valid REJECTED ----

def test_valid_rejected_decision():
    decision = _decision(
        disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
        setup_ids=("a",), reason_codes=("insufficient_volume_confirmation",),
    )
    assert decision.disposition == StrategyDisposition.REJECTED
    assert decision.direction == StrategyDirection.FLAT


# ---- valid NO_SIGNAL ----

def test_valid_no_signal_decision():
    decision = _decision(
        disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
        setup_ids=(), reason_codes=(),
    )
    assert decision.disposition == StrategyDisposition.NO_SIGNAL
    assert decision.setup_ids == ()


# ---- invalid disposition/direction combinations ----

def test_long_with_rejected_raises():
    with pytest.raises(ValueError, match="disposition=CANDIDATE"):
        _decision(
            disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.LONG,
            setup_ids=("a",), reason_codes=("x",),
        )


def test_short_with_no_signal_raises():
    with pytest.raises(ValueError, match="disposition=CANDIDATE"):
        _decision(disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.SHORT, setup_ids=())


def test_candidate_with_flat_raises():
    with pytest.raises(ValueError, match="direction to be LONG or SHORT"):
        _decision(disposition=StrategyDisposition.CANDIDATE, direction=StrategyDirection.FLAT, setup_ids=("a",))


def test_candidate_with_empty_setup_ids_raises():
    with pytest.raises(ValueError, match="at least one setup_id"):
        _decision(disposition=StrategyDisposition.CANDIDATE, direction=StrategyDirection.LONG, setup_ids=())


def test_rejected_with_empty_setup_ids_raises():
    with pytest.raises(ValueError, match="at least one setup_id"):
        _decision(
            disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
            setup_ids=(), reason_codes=("x",),
        )


def test_rejected_with_empty_reason_codes_raises():
    with pytest.raises(ValueError, match="at least one reason_code"):
        _decision(
            disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
            setup_ids=("a",), reason_codes=(),
        )


def test_no_signal_with_nonempty_setup_ids_raises():
    with pytest.raises(ValueError, match="setup_ids to be empty"):
        _decision(disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT, setup_ids=("a",))


# ---- blank identity ----

def test_blank_strategy_id_raises():
    with pytest.raises(ValueError, match="strategy_id"):
        _decision(strategy_id="   ")


def test_blank_strategy_version_raises():
    with pytest.raises(ValueError, match="strategy_version"):
        _decision(strategy_version="")


def test_blank_context_fingerprint_raises():
    with pytest.raises(ValueError, match="context_fingerprint"):
        _decision(context_fingerprint="")


# ---- confidence bounds ----

def test_confidence_none_is_valid():
    assert _decision(confidence=None).confidence is None


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_confidence_within_bounds_is_valid(value):
    assert _decision(confidence=value).confidence == value


@pytest.mark.parametrize("value", [-0.01, 1.01, -5.0, 5.0])
def test_confidence_out_of_bounds_raises(value):
    with pytest.raises(ValueError, match="confidence"):
        _decision(confidence=value)


# ---- deterministic reason-code / setup-id representation ----

def test_reason_codes_preserve_supplied_order():
    decision = _decision(
        disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT, setup_ids=("a",),
        reason_codes=("third", "first", "second"),
    )
    assert decision.reason_codes == ("third", "first", "second")  # never sorted, never de-duplicated as a set


def test_setup_ids_preserve_supplied_order():
    decision = _decision(setup_ids=("c", "a", "b"))
    assert decision.setup_ids == ("c", "a", "b")


def test_repeated_construction_with_identical_inputs_is_equal_and_deterministic():
    a = _decision()
    b = _decision()
    assert a is not b
    assert a == b


# ---- optional reference fields ----

def test_optional_reference_fields_accept_price():
    decision = _decision(stop=Price(100.0, 0.25), target=Price(110.0, 0.25), invalidation=Price(95.0, 0.25))
    assert decision.stop == Price(100.0, 0.25)
    assert decision.target == Price(110.0, 0.25)
    assert decision.invalidation == Price(95.0, 0.25)


def test_optional_reference_fields_default_to_none():
    decision = _decision()
    assert decision.stop is None
    assert decision.target is None
    assert decision.invalidation is None


# ---- no ReplaySession dependency ----

def test_no_replay_session_reference_in_models_module():
    import atlas.strategy_engine.models as strategy_engine_models
    assert not hasattr(strategy_engine_models, "ReplaySession")
