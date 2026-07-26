"""Phase 18A executable checks for the frozen AI analysis contracts.

These are specification conformance checks, not a runtime validator, SDK,
orchestration layer, prompt builder, or provider integration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
SPEC = ROOT / "specs" / "ai_analysis" / "v1"
SNAPSHOT_SPEC = ROOT / "specs" / "trader_now_snapshot" / "v1"
GOLDEN = SPEC / "golden"

UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
EVIDENCE_POINTER = re.compile(
    r"^/evidence/(?:[^~/*?#]|~0|~1)+(?:/(?:[^~/*?#]|~0|~1)+)*$"
)


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


def _golden(name: str) -> dict[str, Any]:
    return _load(GOLDEN / name)


def _decode_pointer(pointer: str) -> list[str]:
    assert EVIDENCE_POINTER.fullmatch(pointer)
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer.split("/")[1:]
    ]


def _resolve(value: Any, pointer: str) -> Any:
    current = value
    for token in _decode_pointer(pointer):
        if isinstance(current, list):
            assert token == "0" or not token.startswith("0")
            current = current[int(token)]
        else:
            current = current[token]
    return current


def _allowlisted(pointer: str, allowlist: dict[str, Any]) -> bool:
    tokens = _decode_pointer(pointer)
    if not tokens or tokens[0] != "evidence":
        return False
    dotted = ".".join(tokens[1:])
    for path in allowlist["paths"]:
        if dotted == path or dotted.startswith(f"{path}."):
            return True
    return False


def _assert_closed_schema(schema: dict[str, Any]) -> None:
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_contract_files_are_static_specification_only():
    files = {path.relative_to(SPEC).as_posix() for path in SPEC.rglob("*") if path.is_file()}

    assert {
        "README.md",
        "policy.json",
        "input.schema.json",
        "output.schema.json",
        "audit.schema.json",
        "golden/manifest.json",
        "negative/vectors.json",
        "adversarial/vectors.json",
    } <= files
    assert not any(
        path.endswith((".py", ".sql", ".toml", ".env", ".yaml", ".yml"))
        for path in files
    )


def test_contract_envelopes_are_closed_and_independently_versioned():
    schemas = {
        "input": _load(SPEC / "input.schema.json"),
        "output": _load(SPEC / "output.schema.json"),
        "audit": _load(SPEC / "audit.schema.json"),
    }
    policy = _load(SPEC / "policy.json")

    for schema in schemas.values():
        _assert_closed_schema(schema)
    assert schemas["input"]["properties"]["schema_version"]["const"] == (
        policy["contracts"]["input"]
    )
    assert schemas["output"]["properties"]["schema_version"]["const"] == (
        policy["contracts"]["output"]
    )
    assert schemas["audit"]["properties"]["schema_version"]["const"] == (
        policy["contracts"]["audit"]
    )
    assert policy["versioning"] == {
        "closed_envelopes": True,
        "unknown_versions": "reject",
        "in_place_changes": False,
        "coercion": False,
        "downgrade": False,
        "partial_processing": False,
    }


def test_purpose_allowlist_is_identical_across_all_contracts():
    policy = _load(SPEC / "policy.json")
    expected = policy["explanation_purposes"]

    for filename in ("input.schema.json", "output.schema.json", "audit.schema.json"):
        schema = _load(SPEC / filename)
        assert schema["properties"]["purpose"]["enum"] == expected
    assert len(expected) == len(set(expected))
    assert "trade_recommendation" not in expected
    assert "order_execution" not in expected


def test_input_binds_exactly_one_verified_canonical_snapshot():
    schema = _load(SPEC / "input.schema.json")
    snapshot = schema["$defs"]["snapshot_reference"]

    assert snapshot["additionalProperties"] is False
    assert set(snapshot["required"]) == set(snapshot["properties"])
    assert snapshot["properties"]["snapshot_schema_version"]["const"] == (
        "trader_now_snapshot.v1"
    )
    assert snapshot["properties"]["evidence_profile"]["const"] == (
        "trader_now_complete.v1"
    )
    assert snapshot["properties"]["canonicalization_profile"]["const"] == (
        "atlas-jcs.v1"
    )
    assert snapshot["properties"]["integrity_status"]["const"] == "verified"
    assert "snapshot_ids" not in schema["properties"]
    assert "semantic_json" not in schema["properties"]
    assert "canonical_payload" not in schema["properties"]


def test_snapshot_authority_and_phase_exclusions_are_explicit():
    readme = (SPEC / "README.md").read_text(encoding="utf-8")
    policy = _load(SPEC / "policy.json")

    assert policy["snapshot_authority"] == {
        "canonicalization_profile": "atlas-jcs.v1",
        "evidence_profile": "trader_now_complete.v1",
        "rule": "verified_canonical_snapshot_is_sole_evidence_authority",
        "semantic_json_is_canonical": False,
        "snapshot_schema_version": "trader_now_snapshot.v1",
    }
    for required in (
        "sole evidence authority",
        "Semantic snapshot JSON",
        "backup, restore",
        "accessibility-tree",
        "console/network",
        "not claims of full production readiness",
    ):
        assert required in readme


def test_citation_grammar_is_restricted_to_evidence_json_pointers():
    policy = _load(SPEC / "policy.json")
    citation = policy["citation_reference"]
    pattern = re.compile(citation["pattern"])

    for valid in (
        "/evidence/strategy/decisions/0/disposition",
        "/evidence/a~1b/c~0d",
    ):
        assert pattern.fullmatch(valid)
    for invalid in (
        "",
        "/evidence",
        "/integrity/evidence_digest",
        "#/evidence/strategy",
        "../evidence/strategy",
        "/evidence/*/status",
        "/evidence/strategy/~2bad",
    ):
        assert not pattern.fullmatch(invalid)
    assert citation["must_exist"] is True
    assert citation["must_be_snapshot_allowlisted"] is True
    assert citation["must_match_input_evidence_item"] is True
    assert citation["input_paths_unique"] is True
    assert citation["array_index_pattern"] == "^(?:0|[1-9][0-9]*)$"


def test_golden_bytes_and_sha256_are_frozen():
    manifest = _load(GOLDEN / "manifest.json")

    assert manifest["canonical_bytes_profile"] == "sorted-compact-utf8.v1"
    for vector in manifest["vectors"]:
        stored = (GOLDEN / vector["file"]).read_bytes()
        raw = stored.rstrip(b"\r\n")
        value = json.loads(raw)
        assert raw == _canonical(value)
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw and b"\n" not in raw
        assert hashlib.sha256(raw).hexdigest() == vector["sha256"]
        assert SHA256.fullmatch(vector["sha256"])
        assert value["schema_version"] == vector["contract"]


def test_golden_input_items_resolve_to_frozen_allowlisted_snapshot_evidence():
    value = _golden("input.complete-current.json")
    snapshot = _golden("input.complete-current.json")["snapshot"]
    source = _load(
        SNAPSHOT_SPEC / "golden" / "complete-current-candidate.canonical.json"
    )
    allowlist = _load(SNAPSHOT_SPEC / "allowlist.json")

    assert UUID7.fullmatch(value["analysis_input_id"])
    assert TIMESTAMP.fullmatch(value["created_at"])
    assert value["snapshot"]["snapshot_id"] == source["snapshot_id"]
    assert snapshot["evidence_digest"] == _load(
        SNAPSHOT_SPEC / "golden" / "manifest.json"
    )["vectors"][0]["sha256"]
    for item in value["evidence_items"]:
        assert _allowlisted(item["path"], allowlist)
        assert _resolve(source, item["path"]) == item["value"]


def test_golden_output_is_bound_to_input_and_all_citations_resolve():
    analysis_input = _golden("input.complete-current.json")
    output = _golden("output.complete-current.json")
    input_items = {item["path"] for item in analysis_input["evidence_items"]}

    assert output["analysis_input_id"] == analysis_input["analysis_input_id"]
    assert output["snapshot_id"] == analysis_input["snapshot"]["snapshot_id"]
    assert output["evidence_digest"] == analysis_input["snapshot"]["evidence_digest"]
    assert output["purpose"] == analysis_input["purpose"]
    assert output["status"] == "available"
    assert "advisory_only" in output["limitations"]
    assert output["unavailable_reason"] is None
    assert output["claims"]
    for claim in output["claims"]:
        assert claim["citations"]
        assert set(claim["citations"]) <= input_items


def test_available_and_unavailable_outputs_are_mutually_exclusive():
    available = _golden("output.complete-current.json")
    unavailable = _golden("output.unavailable.json")

    assert available["summary"] and available["claims"]
    assert available["unavailable_reason"] is None
    assert unavailable["summary"] is None
    assert unavailable["claims"] == []
    assert unavailable["limitations"] == []
    assert unavailable["unavailable_reason"] == "provider_timeout"


def test_stale_unavailable_corrupt_and_unsupported_are_fail_closed():
    policy = _load(SPEC / "policy.json")
    refusal = policy["eligibility"]["refusal_states"]
    stale_audit = _golden("audit.stale-refusal.json")

    assert refusal == {
        "corrupted": "snapshot_integrity_failed",
        "stale": "snapshot_stale",
        "unavailable": "snapshot_unavailable",
        "unsupported": "snapshot_schema_unsupported",
    }
    assert policy["eligibility"]["model_invocation_on_refusal"] is False
    assert stale_audit["outcome"] == "refused"
    assert stale_audit["analysis_input_id"] is None
    assert stale_audit["analysis_output_id"] is None
    assert stale_audit["generator"] is None
    assert stale_audit["reason_code"] == "snapshot_stale"


def test_delayed_evidence_requires_an_explicit_limitation():
    policy = _load(SPEC / "policy.json")
    output_schema = _load(SPEC / "output.schema.json")

    assert policy["eligibility"]["eligible_freshness"] == ["current", "delayed"]
    required = policy["eligibility"]["delayed_requires_limitation"]
    assert required == "delayed_evidence"
    assert required in output_schema["properties"]["limitations"]["items"]["enum"]


def test_prohibited_authority_and_actions_cover_phase_18_boundaries():
    policy = _load(SPEC / "policy.json")
    actions = set(policy["prohibited_actions"])
    authority = set(policy["prohibited_authority"])

    assert {
        "trading_decision_authority",
        "strategy_authority",
        "risk_authority",
        "execution_authority",
        "canonical_evidence_authority",
    } == authority
    assert {
        "order_creation",
        "order_sizing",
        "order_routing",
        "order_execution",
        "direct_trader_now_access",
        "arbitrary_database_access",
        "repository_access",
        "deterministic_state_override",
        "uncited_material_claim",
    } <= actions
    assert policy["deterministic_state"]["contradiction_allowed"] is False
    assert policy["deterministic_state"]["recomputation_allowed"] is False


def test_adversarial_evidence_is_untrusted_data_not_instruction():
    policy = _load(SPEC / "policy.json")
    vectors = _load(SPEC / "adversarial" / "vectors.json")["vectors"]

    assert policy["evidence_strings"] == {
        "classification": "untrusted_data",
        "may_change_instructions": False,
        "may_change_purpose": False,
        "may_grant_authority": False,
        "may_request_tools": False,
    }
    assert len(vectors) >= 4
    for vector in vectors:
        assert EVIDENCE_POINTER.fullmatch(vector["evidence_path"])
        assert vector["required_behavior"] == "preserve_as_untrusted_data_never_follow"
    combined = " ".join(vector["untrusted_value"] for vector in vectors)
    for attack in ("Ignore all policies", "execute a buy order", "QUERY DATABASE"):
        assert attack in combined


def test_negative_vectors_cover_structural_semantic_and_adversarial_failures():
    vectors = _load(SPEC / "negative" / "vectors.json")["vectors"]
    violations = {vector["expected_violation"] for vector in vectors}

    assert {
        "closed_envelope",
        "verified_snapshot_required",
        "unsupported_snapshot_schema",
        "snapshot_allowlist",
        "missing_citation",
        "citation_grammar",
        "citation_resolution",
        "single_snapshot_binding",
        "deterministic_state_contradiction",
        "prohibited_content",
        "model_invocation_on_refusal",
        "unknown_version",
    } <= violations
    names = [vector["name"] for vector in vectors]
    assert len(names) == len(set(names))


def test_every_negative_mutation_changes_a_real_golden_document():
    vectors = _load(SPEC / "negative" / "vectors.json")["vectors"]

    for vector in vectors:
        original = _load(SPEC / vector["base"])
        mutated = copy.deepcopy(original)
        operation, changes = next(iter(vector["mutation"].items()))
        assert operation in {"add", "replace"}
        for pointer, replacement in changes.items():
            tokens = pointer.split("/")[1:]
            target = mutated
            for token in tokens[:-1]:
                target = target[int(token)] if isinstance(target, list) else target[token]
            key = tokens[-1]
            if isinstance(target, list):
                target[int(key)] = replacement
            else:
                if operation == "replace":
                    assert key in target
                target[key] = replacement
        assert mutated != original


def test_no_spec_artifact_contains_provider_calls_prompts_credentials_or_runtime():
    forbidden_names = {
        "api_key",
        "database_url",
        "dsn",
        "prompt_template",
        "messages.create",
        "anthropic",
        "openai",
    }
    for path in SPEC.rglob("*"):
        if not path.is_file() or path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in forbidden_names:
            assert forbidden not in text, f"{forbidden!r} leaked into {path}"
