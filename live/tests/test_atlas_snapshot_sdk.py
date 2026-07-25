"""Phase 17B contract, golden-vector, and purity tests."""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

import atlas_snapshot
from atlas_snapshot import (
    SnapshotIntegrityError,
    SnapshotProjectionError,
    SnapshotRecordIdentity,
    SnapshotValidationError,
    derive_idempotency_key,
    digest,
    extract_metadata,
    parse,
    project,
    serialize,
    validate,
    verify,
)

ROOT = Path(__file__).parents[1]
SDK = ROOT / "atlas_snapshot"
GOLDEN = ROOT / "specs" / "trader_now_snapshot" / "v1" / "golden"


def _manifest():
    return json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))


def _golden(entry):
    return json.loads((GOLDEN / entry["file"]).read_text(encoding="utf-8"))


def _transport(golden):
    return {
        "schema_version": golden["source"]["trader_now_response_schema_version"],
        "domain_schema_version": golden["source"][
            "trader_now_domain_schema_version"
        ],
        "snapshot_id": None,
        **golden["evidence"],
        "ignored_future_transport_field": {"must_not_leak": True},
    }


def _identity(golden):
    return SnapshotRecordIdentity(
        snapshot_id=golden["snapshot_id"],
        created_at=golden["created_at"],
        supersedes_snapshot_id=golden["supersedes_snapshot_id"],
    )


def _plain(snapshot):
    return json.loads(serialize(snapshot))


def test_public_api_is_small_explicit_and_standalone():
    expected = {
        "CANONICALIZATION_PROFILE",
        "DIGEST_ALGORITHM",
        "EVIDENCE_PROFILE",
        "SNAPSHOT_SCHEMA_VERSION",
        "SOURCE_DOMAIN_SCHEMA_VERSION",
        "SOURCE_RESPONSE_SCHEMA_VERSION",
        "SnapshotError",
        "SnapshotIntegrityError",
        "SnapshotMetadata",
        "SnapshotProjectionError",
        "SnapshotRecordIdentity",
        "SnapshotValidationError",
        "derive_idempotency_key",
        "digest",
        "extract_metadata",
        "parse",
        "project",
        "serialize",
        "validate",
        "verify",
    }
    assert set(atlas_snapshot.__all__) == expected


@pytest.mark.parametrize("entry", _manifest()["vectors"], ids=lambda item: item["file"])
def test_project_matches_every_frozen_golden_evidence_digest(entry):
    golden = _golden(entry)

    snapshot = project(_transport(golden), _identity(golden))

    assert digest(snapshot) == entry["sha256"]
    assert snapshot["integrity"]["evidence_digest"] == entry["sha256"]
    assert _plain(snapshot)["evidence"] == golden["evidence"]
    assert "ignored_future_transport_field" not in snapshot["evidence"]
    assert verify(snapshot) is True


def test_project_normalizes_fractional_values_and_datetimes():
    golden = _golden(_manifest()["vectors"][0])
    source = _transport(golden)
    source["market"]["latest_bar"]["close"]["value"] = 20750.2500
    source["source_trust"]["freshness"]["lateness_seconds"] = -0.0

    snapshot = project(
        source,
        SnapshotRecordIdentity(
            snapshot_id=golden["snapshot_id"],
            created_at=datetime(2026, 7, 25, 12, 0, 1, tzinfo=timezone.utc),
        ),
    )

    assert snapshot["created_at"] == "2026-07-25T12:00:01.000000Z"
    assert snapshot["evidence"]["market"]["latest_bar"]["close"]["value"] == (
        "20750.25"
    )
    assert snapshot["evidence"]["source_trust"]["freshness"][
        "lateness_seconds"
    ] == "0"


def test_projected_snapshot_is_recursively_immutable():
    golden = _golden(_manifest()["vectors"][0])
    snapshot = project(_transport(golden), _identity(golden))

    assert isinstance(snapshot, MappingProxyType)
    with pytest.raises(TypeError):
        snapshot["snapshot_id"] = "different"
    with pytest.raises(TypeError):
        snapshot["evidence"]["identity"]["product"] = "NQ"
    with pytest.raises(AttributeError):
        snapshot["evidence"]["strategy"]["decisions"].append({})


def test_metadata_is_frozen_and_derived_from_verified_payload():
    golden = _golden(_manifest()["vectors"][0])
    metadata = extract_metadata(project(_transport(golden), _identity(golden)))

    assert metadata.economic_instrument == "MNQ"
    assert metadata.market_data_provider == "tradingview"
    assert metadata.market_data_series_symbol == "MNQ1!"
    assert metadata.market_data_series_type == "continuous"
    assert metadata.latest_closed_at == "2026-07-25T11:55:00.000000Z"
    with pytest.raises(FrozenInstanceError):
        metadata.trust_status = "changed"


def test_no_data_metadata_remains_explicitly_absent():
    entry = _manifest()["vectors"][1]
    golden = _golden(entry)
    metadata = extract_metadata(project(_transport(golden), _identity(golden)))

    assert metadata.economic_instrument is None
    assert metadata.market_data_provider is None
    assert metadata.market_data_series_symbol is None
    assert metadata.latest_closed_at is None
    assert metadata.trust_status == "untrusted"


def test_serialize_parse_verify_round_trip_is_byte_stable():
    golden = _golden(_manifest()["vectors"][0])
    snapshot = project(_transport(golden), _identity(golden))

    payload = serialize(snapshot)
    parsed = parse(payload)

    assert isinstance(parsed, MappingProxyType)
    assert serialize(parsed) == payload
    assert verify(parsed) is True


def test_parse_rejects_noncanonical_and_non_utf8_encodings():
    golden = _golden(_manifest()["vectors"][0])
    payload = serialize(project(_transport(golden), _identity(golden)))

    with pytest.raises(SnapshotValidationError, match="not canonical"):
        parse(json.dumps(json.loads(payload), indent=2))
    with pytest.raises(SnapshotValidationError, match="BOM"):
        parse(b"\xef\xbb\xbf" + payload)
    with pytest.raises(SnapshotValidationError, match="UTF-8"):
        parse(b"\xff")


def test_verify_rejects_tampering_and_unsealed_snapshots():
    golden = _golden(_manifest()["vectors"][0])
    sealed = _plain(project(_transport(golden), _identity(golden)))
    sealed["evidence"]["identity"]["product"] = "NQ"
    with pytest.raises(SnapshotIntegrityError, match="mismatch"):
        verify(sealed)

    sealed["integrity"]["evidence_digest"] = None
    with pytest.raises(SnapshotIntegrityError, match="not sealed"):
        verify(sealed)


def test_record_metadata_does_not_change_evidence_digest():
    golden = _golden(_manifest()["vectors"][0])
    first = project(_transport(golden), _identity(golden))
    second = project(
        _transport(golden),
        SnapshotRecordIdentity(
            snapshot_id="019849d1-8c00-7000-8000-000000000099",
            created_at="2026-07-25T12:30:01.000000Z",
            supersedes_snapshot_id="019849d1-8c00-7000-8000-000000000098",
        ),
    )

    assert digest(first) == digest(second)
    assert serialize(first) != serialize(second)


def test_idempotency_is_order_independent_and_evaluation_sensitive():
    golden = _golden(_manifest()["vectors"][0])
    first = _transport(golden)
    reordered = dict(reversed(list(first.items())))

    assert derive_idempotency_key(first) == derive_idempotency_key(reordered)

    changed = json.loads(json.dumps(first))
    changed["evaluated_at"] = "2026-07-25T12:00:01.000000Z"
    assert derive_idempotency_key(first) != derive_idempotency_key(changed)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "trader_now_response.v99", "response schema"),
        ("domain_schema_version", "trader_now.v99", "domain schema"),
    ],
)
def test_project_rejects_unsupported_source_versions(field, value, message):
    golden = _golden(_manifest()["vectors"][0])
    source = _transport(golden)
    source[field] = value

    with pytest.raises(SnapshotProjectionError, match=message):
        project(source, _identity(golden))


def test_project_rejects_missing_evidence_section():
    golden = _golden(_manifest()["vectors"][0])
    source = _transport(golden)
    del source["strategy"]

    with pytest.raises(SnapshotProjectionError, match="missing evidence"):
        project(source, _identity(golden))


def test_validate_rejects_unknown_envelope_and_evidence_fields():
    golden = _golden(_manifest()["vectors"][0])
    value = _plain(project(_transport(golden), _identity(golden)))
    value["runtime"] = {}
    with pytest.raises(SnapshotValidationError, match="envelope fields"):
        validate(value)

    del value["runtime"]
    value["evidence"]["secret"] = "forbidden"
    with pytest.raises(SnapshotValidationError, match="evidence fields"):
        validate(value)


def test_validate_rejects_binary_floats_and_noncanonical_timestamp():
    golden = _golden(_manifest()["vectors"][0])
    value = _plain(project(_transport(golden), _identity(golden)))
    value["evidence"]["strategy"]["decisions"][0]["confidence"] = 0.81
    with pytest.raises(SnapshotValidationError, match="decimal strings"):
        validate(value)

    value = _plain(project(_transport(golden), _identity(golden)))
    value["evidence"]["evaluated_at"] = "2026-07-25T12:00:00+00:00"
    with pytest.raises(SnapshotValidationError, match="canonical UTC"):
        validate(value)


@pytest.mark.parametrize("bad", ["01.5", "1.50", "1e2", "+1", "-0"])
def test_validate_rejects_noncanonical_decimal_strings(bad):
    golden = _golden(_manifest()["vectors"][0])
    value = _plain(project(_transport(golden), _identity(golden)))
    value["evidence"]["strategy"]["decisions"][0]["confidence"] = bad

    with pytest.raises(SnapshotValidationError, match="canonical decimal"):
        validate(value)


def test_parse_rejects_duplicate_object_keys():
    with pytest.raises(SnapshotValidationError, match="duplicate JSON object key"):
        parse('{"snapshot_schema_version":"x","snapshot_schema_version":"y"}')


def test_sdk_dependency_boundary_contains_only_python_standard_library():
    forbidden_roots = {
        "atlas",
        "asyncpg",
        "fastapi",
        "httpx",
        "psycopg",
        "railway",
        "anthropic",
        "openai",
    }
    forbidden_terms = {
        "postgres",
        "railway",
        "capture_service",
        "dependency_inject",
        "fastapi",
        "anthropic",
        "openai",
    }

    for path in SDK.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        assert imports.isdisjoint(forbidden_roots), path.name
        lowered = source.lower()
        assert not any(term in lowered for term in forbidden_terms), path.name


def test_sdk_has_no_io_network_database_or_runtime_entrypoints():
    names = {path.name for path in SDK.glob("*.py")}
    assert names == {"__init__.py", "_canonical.py", "errors.py", "models.py", "sdk.py"}
    for path in SDK.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert calls.isdisjoint({"open", "print", "input", "exec", "eval"})
