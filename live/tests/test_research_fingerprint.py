"""
Phase N4 Sprint 1. Tests for atlas.research.fingerprint - a self-contained
canonical hashing helper, independent from
atlas.setup_interpretation.fingerprint and atlas.market_context.fingerprint.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import pytest

from atlas.research.fingerprint import (
    SelfReferentialFingerprintError,
    canonical_json,
    compute_fingerprint,
    to_canonical,
)


class _Color(str, Enum):
    RED = "red"


@dataclass(frozen=True)
class _Thing:
    a: int
    b: str


def test_repeated_fingerprint_of_the_same_value_is_identical():
    value = _Thing(a=1, b="x")
    fingerprints = {compute_fingerprint(value) for _ in range(100)}
    assert len(fingerprints) == 1


def test_same_values_in_separately_created_dataclasses_produce_the_same_fingerprint():
    a = _Thing(a=1, b="x")
    b = _Thing(a=1, b="x")
    assert a is not b
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_fingerprint_output_is_16_lowercase_hex_characters():
    fp = compute_fingerprint(_Thing(a=1, b="x"))
    assert len(fp) == 16
    assert fp == fp.lower()
    assert all(c in "0123456789abcdef" for c in fp)


def test_mapping_insertion_order_does_not_affect_canonical_serialization_or_fingerprint():
    first = {"b": 2, "a": 1, "c": 3}
    second = {"c": 3, "a": 1, "b": 2}
    assert list(first.keys()) != list(second.keys())
    assert canonical_json(first) == canonical_json(second)
    assert compute_fingerprint(first) == compute_fingerprint(second)


def test_dataclass_field_declaration_order_does_not_affect_fingerprint():
    """Two instances built with keyword arguments given in a different
    order still fingerprint identically - sort_keys=True makes call order
    irrelevant, the same guarantee every other fingerprint module in this
    codebase already provides."""
    a = _Thing(a=1, b="x")
    b = _Thing(b="x", a=1)
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_fingerprint_changes_when_any_field_changes():
    base = _Thing(a=1, b="x")
    changed = _Thing(a=2, b="x")
    assert compute_fingerprint(base) != compute_fingerprint(changed)


def test_enum_serializes_by_value_deterministically():
    assert to_canonical(_Color.RED) == "red"
    assert compute_fingerprint(_Color.RED) == compute_fingerprint("red")


def test_datetime_serializes_deterministically_via_iso_8601():
    dt = datetime(2026, 7, 21, 12, 30, 0, tzinfo=timezone.utc)
    assert to_canonical(dt) == dt.isoformat()


def test_lists_and_tuples_preserve_order_rather_than_being_sorted():
    ordered = ["b", "a"]
    assert to_canonical(ordered) == ["b", "a"]
    assert to_canonical(tuple(ordered)) == ["b", "a"]
    assert compute_fingerprint(("a", "b")) != compute_fingerprint(("b", "a"))


def test_output_does_not_depend_on_python_object_identity():
    a = _Thing(a=1, b="x")
    b = _Thing(a=1, b="x")
    assert a is not b
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_hashing_a_self_referencing_object_raises_instead_of_producing_an_unstable_hash():
    """Every new Research Engine entity (Feature, Finding, Realization,
    Evidence, ValidationResult, LeaderboardSnapshot, PromotionRecord,
    Experiment) carries its own fingerprint field(s) on itself, unlike
    SETUP_INTERPRETATION_V1 or Market Context's own fingerprinted inputs
    (neither of which has a fingerprint field of its own). Without a guard,
    compute_fingerprint() called on one of these directly would hash
    differently for two objects with identical semantic content purely
    because their pre-existing fingerprint values differ. to_canonical()
    now refuses this outright rather than silently producing an unstable
    hash."""

    @dataclass(frozen=True)
    class _SelfReferencing:
        name: str
        fingerprint: str

    a = _SelfReferencing(name="x", fingerprint="aaaaaaaaaaaaaaaa")
    b = _SelfReferencing(name="x", fingerprint="bbbbbbbbbbbbbbbb")
    with pytest.raises(SelfReferentialFingerprintError):
        compute_fingerprint(a)
    with pytest.raises(SelfReferentialFingerprintError):
        compute_fingerprint(b)


def test_the_guard_does_not_apply_to_plain_mappings_composing_another_fingerprint():
    """The guard is scoped to dataclass instances - the actual entities
    that carry a field which will later be retroactively populated with
    their own fingerprint. A hand-built dict has no such "self" to
    reference, and Experiment's execution_fingerprint design deliberately
    requires nesting an already-computed semantic_fingerprint value as one
    of execution_fingerprint's own inputs - compositional, not self-
    referential. This must keep working."""
    semantic = compute_fingerprint({"hypothesis_id": "h1"})
    execution = compute_fingerprint({"semantic_fingerprint": semantic, "code_version": "abc123"})
    assert execution != semantic


def test_the_correct_pattern_excludes_the_fingerprint_field_before_hashing():
    """The discipline every future Research Engine construction service
    must follow instead: build an explicit projection of only the
    semantically-defining fields, excluding the entity's own `fingerprint`
    field (and every id/timestamp/lifecycle/provenance field), then hash
    that projection - never the entity itself."""

    @dataclass(frozen=True)
    class _SelfReferencing:
        name: str
        fingerprint: str

    def _semantic_projection(entity: "_SelfReferencing") -> dict:
        return {"name": entity.name}

    a = _SelfReferencing(name="x", fingerprint="aaaaaaaaaaaaaaaa")
    b = _SelfReferencing(name="x", fingerprint="bbbbbbbbbbbbbbbb")
    assert compute_fingerprint(_semantic_projection(a)) == compute_fingerprint(_semantic_projection(b))


def test_no_import_from_another_packages_fingerprint_module():
    """This module's own docstring commits to independence from
    atlas.setup_interpretation.fingerprint and
    atlas.market_context.fingerprint - confirmed here directly."""
    import inspect

    import atlas.research.fingerprint as own_module

    source = inspect.getsource(own_module)
    import_lines = [line for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    assert not any("setup_interpretation" in line or "market_context" in line for line in import_lines)
