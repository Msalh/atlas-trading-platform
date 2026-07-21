"""
Phase N1, Sprint 1. Tests for atlas.market_context.fingerprint and the
CME_RTH_V1/REGIME_CLASSIFIER_V1 naming/versioning invariants from
definitions.py - both modules are pure, no fixtures beyond plain
construction needed.
"""
from datetime import datetime, timezone
from enum import Enum

from atlas.market_context import definitions
from atlas.market_context.definitions import (
    CME_RTH_V1,
    REGIME_CLASSIFIER_V1,
    RegimeClassifierDefinition,
    RegimeClassifierParams,
    SessionCalendarDefinition,
    SessionCalendarParams,
)
from atlas.market_context.fingerprint import canonical_json, compute_fingerprint, to_canonical


class _Color(str, Enum):
    RED = "red"


def test_same_values_in_separately_created_definitions_produce_the_same_fingerprint():
    a = SessionCalendarDefinition(
        version="CME_RTH_V1",
        params=SessionCalendarParams(
            rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
            pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
        ),
    )
    b = SessionCalendarDefinition(
        version="CME_RTH_V1",
        params=SessionCalendarParams(
            rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
            pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
        ),
    )
    assert a is not b  # genuinely separate objects
    assert a.params is not b.params
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_same_version_but_different_params_produces_a_different_fingerprint():
    """The core guarantee amendment 2 exists for: a params edit without a
    version bump must still be detectable."""
    a = RegimeClassifierDefinition(
        version="REGIME_CLASSIFIER_V1",
        params=RegimeClassifierParams(lookback_bars=288, min_bars_required=288,
                                       compressed_percentile=25, expanded_percentile=75),
    )
    b = RegimeClassifierDefinition(
        version="REGIME_CLASSIFIER_V1",  # identical version string
        params=RegimeClassifierParams(lookback_bars=100, min_bars_required=100,  # different params
                                       compressed_percentile=25, expanded_percentile=75),
    )
    assert a.version == b.version
    assert compute_fingerprint(a) != compute_fingerprint(b)


def test_mapping_insertion_order_does_not_affect_canonical_serialization_or_fingerprint():
    first = {"b": 2, "a": 1, "c": 3}
    second = {"c": 3, "a": 1, "b": 2}
    assert list(first.keys()) != list(second.keys())  # genuinely different insertion order
    assert canonical_json(first) == canonical_json(second)
    assert compute_fingerprint(first) == compute_fingerprint(second)


def test_enum_serializes_by_value_deterministically():
    assert to_canonical(_Color.RED) == "red"
    assert canonical_json({"color": _Color.RED}) == canonical_json({"color": "red"})
    assert compute_fingerprint(_Color.RED) == compute_fingerprint("red")


def test_datetime_serializes_deterministically_via_iso_8601():
    dt = datetime(2026, 7, 21, 12, 30, 0, tzinfo=timezone.utc)
    assert to_canonical(dt) == dt.isoformat()
    # Two separately-constructed but equal datetimes must fingerprint identically.
    dt_again = datetime(2026, 7, 21, 12, 30, 0, tzinfo=timezone.utc)
    assert dt is not dt_again
    assert compute_fingerprint(dt) == compute_fingerprint(dt_again)


def test_lists_and_tuples_preserve_order_rather_than_being_sorted():
    ordered = [3, 1, 2]
    assert to_canonical(ordered) == [3, 1, 2]
    assert to_canonical(tuple(ordered)) == [3, 1, 2]
    # A reordered list is a genuinely different value, not a canonicalization no-op.
    assert compute_fingerprint([3, 1, 2]) != compute_fingerprint([1, 2, 3])


def test_output_does_not_depend_on_python_object_identity():
    a = SessionCalendarParams(
        rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
        pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
    )
    b = SessionCalendarParams(
        rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
        pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
    )
    assert a is not b
    assert id(a) != id(b)
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_fingerprint_output_is_16_lowercase_hex_characters():
    fp = compute_fingerprint({"anything": 1})
    assert len(fp) == 16
    assert fp == fp.lower()
    assert all(c in "0123456789abcdef" for c in fp)


def test_cme_rth_v1_constant_name_matches_its_own_version_string():
    assert CME_RTH_V1.version == "CME_RTH_V1"


def test_regime_classifier_v1_constant_name_matches_its_own_version_string():
    assert REGIME_CLASSIFIER_V1.version == "REGIME_CLASSIFIER_V1"


def test_no_default_star_alias_exists_in_market_context_definitions():
    default_names = [name for name in dir(definitions) if name.startswith("DEFAULT_")]
    assert default_names == []


def test_cme_rth_v1_holds_the_gate_1_calibrated_values():
    p = CME_RTH_V1.params
    assert (p.rth_open_hour_ct, p.rth_open_minute_ct) == (8, 30)
    assert (p.rth_close_hour_ct, p.rth_close_minute_ct) == (15, 5)
    assert p.pre_open_minutes == 60
    assert p.opening_range_minutes == 30
    assert p.closing_range_minutes == 15


def test_regime_classifier_v1_holds_the_gate_1_calibrated_values():
    p = REGIME_CLASSIFIER_V1.params
    assert p.lookback_bars == 288
    assert p.min_bars_required == 288
    assert p.compressed_percentile == 25
    assert p.expanded_percentile == 75
