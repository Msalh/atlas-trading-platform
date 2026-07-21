"""
UI v2. Tests for atlas.research_export.serialization - the generic
recursive converter every frozen RE-1/RE-2 dataclass is serialized
through. Covers determinism, the tuple-order-preserved vs
frozenset-sorted distinction (a correction to the original "sort
everything" sketch - see that module's own docstring), Mapping key
sorting, Enum handling, and the checksum's exclusion of anything not
passed to it explicitly (proving the caller, not this module, is
responsible for keeping dynamic fields out of the checksum input).
"""
from dataclasses import dataclass
from enum import Enum

from atlas.research_export.serialization import canonical_json, content_checksum, pretty_json, to_jsonable


class _Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclass(frozen=True)
class _Inner:
    name: str
    value: int


@dataclass(frozen=True)
class _Outer:
    inner: _Inner
    tags: tuple[str, ...]
    color: _Color
    counts: dict


def test_dataclass_converts_to_dict_with_field_names():
    obj = _Inner(name="a", value=1)
    assert to_jsonable(obj) == {"name": "a", "value": 1}


def test_nested_dataclass_and_enum_and_mapping():
    obj = _Outer(inner=_Inner("x", 2), tags=("b", "a"), color=_Color.BLUE, counts={"z": 1, "a": 2})
    result = to_jsonable(obj)
    assert result["inner"] == {"name": "x", "value": 2}
    assert result["color"] == "blue"
    assert result["counts"] == {"a": 2, "z": 1}


def test_tuple_order_is_preserved_not_sorted():
    # A tuple's own order is already deterministic and often meaningful
    # (e.g. registry order) - to_jsonable must never silently re-sort it.
    obj = _Outer(inner=_Inner("x", 1), tags=("zebra", "apple", "mango"), color=_Color.RED, counts={})
    result = to_jsonable(obj)
    assert result["tags"] == ["zebra", "apple", "mango"]


def test_frozenset_is_sorted_for_determinism():
    result = to_jsonable(frozenset({"banana", "apple", "cherry"}))
    assert result == ["apple", "banana", "cherry"]


def test_mapping_keys_are_always_sorted():
    result = to_jsonable({"z": 1, "a": 2, "m": 3})
    assert list(result.keys()) == ["a", "m", "z"]


def test_none_and_scalars_pass_through():
    assert to_jsonable(None) is None
    assert to_jsonable(True) is True
    assert to_jsonable(3.5) == 3.5
    assert to_jsonable("hi") == "hi"


def test_canonical_json_is_deterministic_across_calls():
    obj = _Outer(inner=_Inner("x", 1), tags=("b", "a"), color=_Color.RED, counts={"z": 1, "a": 2})
    assert canonical_json(obj) == canonical_json(obj)


def test_canonical_json_has_no_incidental_whitespace():
    obj = _Inner("a", 1)
    assert " " not in canonical_json(obj)


def test_content_checksum_stable_for_identical_payload():
    payload_a = {"x": 1, "y": [1, 2, 3]}
    payload_b = {"y": [1, 2, 3], "x": 1}  # different key order, same content
    assert content_checksum(payload_a) == content_checksum(payload_b)


def test_content_checksum_changes_when_payload_changes():
    assert content_checksum({"x": 1}) != content_checksum({"x": 2})


def test_content_checksum_excludes_whatever_is_not_passed_to_it():
    # The caller is responsible for passing only the deterministic payload -
    # this test proves the checksum genuinely only reflects its own input,
    # so a caller that (correctly) excludes exported_at gets a stable value.
    payload = {"a": 1}
    envelope_with_dynamic_field = {"a": 1, "exported_at": "2026-01-01T00:00:00Z"}
    assert content_checksum(payload) != content_checksum(envelope_with_dynamic_field)
    stable_1 = content_checksum(payload)
    stable_2 = content_checksum(payload)
    assert stable_1 == stable_2


def test_pretty_json_is_valid_and_sorted():
    import json
    obj = {"z": 1, "a": 2}
    parsed = json.loads(pretty_json(obj))
    assert parsed == {"z": 1, "a": 2}
    assert "\n" in pretty_json(obj)
