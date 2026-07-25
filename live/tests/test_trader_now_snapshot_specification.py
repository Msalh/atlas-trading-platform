"""Phase 17A executable checks for the frozen snapshot specification.

These tests deliberately contain the small reference checks needed to certify
the static contract and golden vectors. They are not the Phase 17B Snapshot SDK.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from atlas.api_models.trader_now import (
    TRADER_NOW_RESPONSE_SCHEMA_VERSION,
    TraderNowResponse,
)
from atlas.trader_now.models import SCHEMA_VERSION as TRADER_NOW_SCHEMA_VERSION

SPEC = Path(__file__).parents[1] / "specs" / "trader_now_snapshot" / "v1"
GOLDEN = SPEC / "golden"
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_preimage(value: dict[str, Any]) -> bytes:
    return _canonical(
        {
            "canonicalization_profile": value["canonicalization_profile"],
            "evidence": value["evidence"],
            "evidence_profile": value["evidence_profile"],
            "snapshot_schema_version": value["snapshot_schema_version"],
            "source": value["source"],
        }
    )


def _vectors() -> list[tuple[dict[str, Any], bytes, dict[str, Any]]]:
    manifest = _load(GOLDEN / "manifest.json")
    result = []
    for entry in manifest["vectors"]:
        raw = (GOLDEN / entry["file"]).read_bytes().rstrip(b"\r\n")
        result.append((entry, raw, json.loads(raw)))
    return result


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_contract_identities_match_frozen_source_contracts():
    schema = _load(SPEC / "schema.json")
    manifest = _load(GOLDEN / "manifest.json")

    assert TRADER_NOW_RESPONSE_SCHEMA_VERSION == "trader_now_response.v2"
    assert TRADER_NOW_SCHEMA_VERSION == "trader_now.v2"
    assert schema["properties"]["snapshot_schema_version"]["const"] == (
        manifest["snapshot_schema_version"]
    )
    assert schema["properties"]["evidence_profile"]["const"] == (
        manifest["evidence_profile"]
    )
    assert schema["properties"]["canonicalization_profile"]["const"] == (
        manifest["canonicalization_profile"]
    )


def test_schema_closes_the_envelope_and_evidence_namespaces():
    schema = _load(SPEC / "schema.json")

    assert schema["additionalProperties"] is False
    assert schema["properties"]["evidence"]["additionalProperties"] is False
    assert schema["properties"]["source"]["additionalProperties"] is False
    assert schema["properties"]["integrity"]["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    evidence = schema["properties"]["evidence"]
    assert set(evidence["required"]) == set(evidence["properties"])


def test_allowlist_is_exhaustive_for_supported_trader_now_response():
    allowlist = _load(SPEC / "allowlist.json")
    root_fields = {path.split(".", 1)[0] for path in allowlist["paths"]}
    transport_fields = set(TraderNowResponse.__dataclass_fields__)

    # Transport-owned schema and transient snapshot identity are represented in
    # the snapshot envelope rather than copied into evidence.
    expected = transport_fields - {"schema_version", "snapshot_id"}
    assert root_fields == expected
    assert allowlist["requirements"] == {
        "explicit_unavailable_sections": True,
        "listed_instrument_may_be_null": True,
        "risk_may_be_null": True,
        "market_window_history_included": False,
    }


def test_denylist_covers_every_forbidden_architecture_category():
    denylist = _load(SPEC / "denylist.json")

    assert set(denylist["categories"]) == {
        "runtime",
        "secrets",
        "internal_domain",
        "transport_and_operations",
        "probabilistic_and_execution",
    }
    flattened = " ".join(
        item
        for values in denylist["categories"].values()
        for item in values
    )
    for forbidden in (
        "API keys",
        "database DSNs",
        "AccountSnapshot",
        "PositionSnapshot",
        "CandidateTradeInput",
        "RiskPolicy",
        "MarketWindowArtifact",
        "AI input",
        "AI output",
        "orders",
    ):
        assert forbidden in flattened


def test_golden_files_are_exact_canonical_utf8_bytes():
    for _, raw, value in _vectors():
        assert raw == _canonical(value)
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw
        assert b"\n" not in raw


def test_golden_sha256_vectors_are_frozen_and_complete():
    for entry, raw, value in _vectors():
        assert value["integrity"] == {
            "algorithm": "sha256",
            "evidence_digest": None,
        }
        assert hashlib.sha256(_digest_preimage(value)).hexdigest() == entry["sha256"]
        assert LOWER_SHA256.fullmatch(entry["sha256"])


def test_golden_vectors_cover_all_approved_phase_17a_states():
    covered = {
        state
        for entry, _, _ in _vectors()
        for state in entry["covers"]
    }
    assert {
        "complete",
        "current",
        "delayed",
        "stale",
        "no_data",
        "insufficient_history",
        "unavailable",
        "unavailable_derived_stage",
        "listed_instrument_absent",
        "listed_instrument_present",
        "risk_absent",
        "risk_present",
        "candidate",
        "rejected",
        "no_signal",
        "supersession",
    } <= covered


def test_every_golden_envelope_obeys_identity_and_source_rules():
    for _, _, value in _vectors():
        assert value["snapshot_schema_version"] == "trader_now_snapshot.v1"
        assert value["evidence_profile"] == "trader_now_complete.v1"
        assert value["canonicalization_profile"] == "atlas-jcs.v1"
        assert UUID7.fullmatch(value["snapshot_id"])
        assert value["idempotency_key"].startswith("tns1:")
        assert LOWER_SHA256.fullmatch(value["idempotency_key"][5:])
        if value["supersedes_snapshot_id"] is not None:
            assert UUID7.fullmatch(value["supersedes_snapshot_id"])
            assert value["supersedes_snapshot_id"] != value["snapshot_id"]
        assert TIMESTAMP.fullmatch(value["created_at"])
        assert value["source"] == {
            "trader_now_domain_schema_version": "trader_now.v2",
            "trader_now_response_schema_version": "trader_now_response.v2",
        }


def test_fractional_evidence_values_are_strings_not_binary_floats():
    for _, _, value in _vectors():
        assert not any(isinstance(item, float) for item in _walk(value))


def test_digest_changes_for_any_payload_mutation():
    entry, _, value = _vectors()[0]
    original = entry["sha256"]
    value["evidence"]["identity"]["product"] = "NQ"

    assert hashlib.sha256(_digest_preimage(value)).hexdigest() != original


def test_record_metadata_does_not_change_evidence_digest():
    _, _, value = _vectors()[0]
    original = hashlib.sha256(_digest_preimage(value)).hexdigest()
    value["snapshot_id"] = "019849d1-8c00-7000-8000-000000000099"
    value["created_at"] = "2026-07-25T12:30:01.000000Z"
    value["idempotency_key"] = f"tns1:{'9' * 64}"
    value["supersedes_snapshot_id"] = "019849d1-8c00-7000-8000-000000000098"

    assert hashlib.sha256(_digest_preimage(value)).hexdigest() == original


def test_unavailable_and_optional_states_are_explicit():
    by_name = {entry["file"]: value for entry, _, value in _vectors()}
    no_data = by_name["no-data.canonical.json"]["evidence"]
    risk = by_name[
        "stale-unavailable-no-signal-with-risk.canonical.json"
    ]["evidence"]

    assert no_data["market"]["latest_bar"] is None
    assert no_data["market"]["listed_instrument"] is None
    assert no_data["risk"] is None
    assert no_data["context"]["data"] is None
    assert no_data["rules"]["availability"]["status"] == "unavailable"
    assert risk["risk"]["status"] == "rejected"
    assert risk["market"]["listed_instrument"]["contract_symbol"] == "MNQU6"
    assert risk["market"]["market_data_series"]["symbol"] == "MNQ1!"


def test_specification_forbids_runtime_implementation_and_persistence():
    files = {path.name for path in SPEC.rglob("*") if path.is_file()}
    assert not files.intersection(
        {
            "repository.py",
            "service.py",
            "api.py",
            "models.py",
            "serializer.py",
            "sdk.py",
        }
    )
    text = " ".join((SPEC / "README.md").read_text(encoding="utf-8").split())
    assert "contains no runtime implementation" in text
    assert "defines no persistence" in text
    assert "never modified" in text


def test_schema_evolution_rules_prohibit_historical_reinterpretation():
    text = (SPEC / "README.md").read_text(encoding="utf-8")

    for rule in (
        "Stored v1 envelopes are never rewritten",
        "requires a new version",
        "Readers must explicitly declare supported",
        "No version may reinterpret a historical enum value",
    ):
        assert rule in text
