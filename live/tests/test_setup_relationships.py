"""
Sprint RE-2, amendment 5. Tests for the centralized, typed setup-relationship
metadata - proves every currently-registered setup pair is covered, that
sharing an input fact alone never yields LOGICALLY_IMPLIED (the specific
regression amendment 5 named: displacement_with_volume_confirmation and
sustained_displacement_streak must be SHARED_INPUTS_ONLY, not
LOGICALLY_IMPLIED), and that the lookup is order-independent.
"""
import pytest

from atlas.research.setup_profiling import relationships as r
from atlas.research.setup_profiling.models import SetupRelationshipCategory
from atlas.setup_engine.registry import REGISTRY


def test_every_registered_setup_pair_has_exactly_one_entry():
    names = sorted(reg.name for reg in REGISTRY)
    expected_pairs = {
        frozenset({a, b}) for i, a in enumerate(names) for b in names[i + 1:]
    }
    actual_pairs = {frozenset({m.setup_a, m.setup_b}) for m in r.SETUP_RELATIONSHIPS}
    assert actual_pairs == expected_pairs
    assert len(r.SETUP_RELATIONSHIPS) == len(expected_pairs)


def test_displacement_and_streak_are_shared_inputs_only_not_logically_implied():
    metadata = r.relationship_for(
        "displacement_with_volume_confirmation", "sustained_displacement_streak",
    )
    assert metadata.category == SetupRelationshipCategory.SHARED_INPUTS_ONLY


def test_lookup_is_order_independent():
    forward = r.relationship_for(r.DISPLACEMENT_WITH_VOLUME_CONFIRMATION, r.SUSTAINED_DISPLACEMENT_STREAK)
    backward = r.relationship_for(r.SUSTAINED_DISPLACEMENT_STREAK, r.DISPLACEMENT_WITH_VOLUME_CONFIRMATION)
    assert forward is backward


def test_unregistered_pair_raises_keyerror():
    with pytest.raises(KeyError):
        r.relationship_for("displacement_with_volume_confirmation", "not_a_real_setup")


def test_no_pair_shares_input_facts_and_is_marked_logically_implied():
    # The regression amendment 5 explicitly warned against: a shared-input
    # pair must never be classified as LOGICALLY_IMPLIED just because the
    # inputs overlap.
    shared_input_pairs = {
        frozenset({r.DISPLACEMENT_WITH_VOLUME_CONFIRMATION, r.LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION}),
        frozenset({r.DISPLACEMENT_WITH_VOLUME_CONFIRMATION, r.SUSTAINED_DISPLACEMENT_STREAK}),
        frozenset({r.DISPLACEMENT_WITH_VOLUME_CONFIRMATION, r.VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION}),
        frozenset({r.LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION, r.VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION}),
    }
    for m in r.SETUP_RELATIONSHIPS:
        if frozenset({m.setup_a, m.setup_b}) in shared_input_pairs:
            assert m.category == SetupRelationshipCategory.SHARED_INPUTS_ONLY

    no_shared_input_pairs = {
        frozenset({r.LIQUIDITY_SWEEP_WITH_VOLUME_CONFIRMATION, r.SUSTAINED_DISPLACEMENT_STREAK}),
        frozenset({r.SUSTAINED_DISPLACEMENT_STREAK, r.VWAP_EXTENSION_WITH_VOLUME_CONFIRMATION}),
    }
    for m in r.SETUP_RELATIONSHIPS:
        if frozenset({m.setup_a, m.setup_b}) in no_shared_input_pairs:
            assert m.category == SetupRelationshipCategory.EMPIRICAL


def test_no_current_pair_is_logically_implied():
    # A real, documented finding (see relationships.py's own module
    # docstring) - not a placeholder. Every real setup so far was
    # deliberately built from facts "independent by construction".
    assert all(m.category != SetupRelationshipCategory.LOGICALLY_IMPLIED for m in r.SETUP_RELATIONSHIPS)


def test_every_entry_has_a_non_blank_rationale():
    for m in r.SETUP_RELATIONSHIPS:
        assert m.rationale.strip()
