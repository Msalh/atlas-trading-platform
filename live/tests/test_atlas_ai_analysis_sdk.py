"""Phase 18B golden, adversarial, semantic, and purity certification."""

from __future__ import annotations

import ast
import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import atlas_ai_analysis
from atlas_ai_analysis import (
    AIAnalysisAuthorityError,
    AIAnalysisCitationError,
    AIAnalysisValidationError,
    AnalysisAuditIdentity,
    AnalysisInputIdentity,
    EligibleAnalysis,
    GeneratorIdentity,
    RefusedAnalysis,
    SnapshotVerification,
    completed_audit,
    failed_audit,
    parse_audit,
    parse_input,
    parse_output,
    project_input,
    refused_audit,
    resolve_citation,
    resolve_evidence,
    serialize_audit,
    serialize_input,
    serialize_output,
    validate_audit,
    validate_input,
    validate_output,
)
from atlas_ai_analysis._json import plain

ROOT = Path(__file__).parents[1]
SPEC = ROOT / "specs" / "ai_analysis" / "v1"
SNAPSHOT = ROOT / "specs" / "trader_now_snapshot" / "v1"
PACKAGE = ROOT / "atlas_ai_analysis"

INPUT_ID = AnalysisInputIdentity(
    "019c1234-0000-7000-8000-000000000001",
    "2026-07-26T12:00:01.000000Z",
)
AUDIT_ID = AnalysisAuditIdentity(
    "019c1234-0000-7000-8000-000000000003",
    "2026-07-26T12:00:02.000000Z",
)
GENERATOR = GeneratorIdentity("synthetic-provider", "synthetic-model-v1")
GOLDEN_PATHS = (
    "/evidence/source_trust/freshness/status",
    "/evidence/strategy/decisions/0/disposition",
    "/evidence/strategy/decisions/0/confidence",
    "/evidence/risk",
    "/evidence/decision/availability",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_manifest() -> dict[str, Any]:
    return _load(SNAPSHOT / "golden" / "manifest.json")


def _snapshot(name: str) -> dict[str, Any]:
    value = _load(SNAPSHOT / "golden" / name)
    entry = next(
        item for item in _snapshot_manifest()["vectors"] if item["file"] == name
    )
    value["integrity"]["evidence_digest"] = entry["sha256"]
    return value


def _verification(snapshot: dict[str, Any], status: str = "verified") -> SnapshotVerification:
    return SnapshotVerification(
        snapshot_id=snapshot["snapshot_id"],
        evidence_digest=snapshot["integrity"]["evidence_digest"],
        status=status,  # type: ignore[arg-type]
    )


def _eligible(
    snapshot: dict[str, Any] | None = None,
    *,
    paths: tuple[str, ...] = GOLDEN_PATHS,
    purpose: str = "strategy_explanation",
) -> EligibleAnalysis:
    source = snapshot or _snapshot("complete-current-candidate.canonical.json")
    result = project_input(source, _verification(source), INPUT_ID, purpose, paths)
    assert isinstance(result, EligibleAnalysis)
    return result


def _golden(name: str) -> dict[str, Any]:
    return _load(SPEC / "golden" / name)


def _apply_mutation(value: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    operation, replacements = next(iter(mutation.items()))
    for pointer, replacement in replacements.items():
        tokens = pointer.split("/")[1:]
        current: Any = result
        for token in tokens[:-1]:
            current = current[int(token)] if isinstance(current, list) else current[token]
        key = tokens[-1]
        if isinstance(current, list):
            current[int(key)] = replacement
        else:
            if operation == "replace":
                assert key in current
            current[key] = replacement
    return result


def _replace_pointer(value: Any, pointer: str, replacement: Any) -> None:
    tokens = pointer.split("/")[1:]
    current = value
    for raw in tokens[:-1]:
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    key = tokens[-1].replace("~1", "/").replace("~0", "~")
    if isinstance(current, list):
        current[int(key)] = replacement
    else:
        current[key] = replacement


def test_public_api_is_small_explicit_and_provider_neutral():
    expected = {
        "AUDIT_SCHEMA_VERSION",
        "AIAnalysisAuthorityError",
        "AIAnalysisCitationError",
        "AIAnalysisError",
        "AIAnalysisValidationError",
        "AnalysisAuditIdentity",
        "AnalysisInputIdentity",
        "CANONICALIZATION_PROFILE",
        "EVIDENCE_PROFILE",
        "EXPLANATION_PURPOSES",
        "EligibleAnalysis",
        "GeneratorIdentity",
        "INPUT_SCHEMA_VERSION",
        "OUTPUT_SCHEMA_VERSION",
        "POLICY_VERSION",
        "PURPOSE_EVIDENCE_PATHS",
        "RefusedAnalysis",
        "SNAPSHOT_ALLOWLIST",
        "SNAPSHOT_SCHEMA_VERSION",
        "SnapshotVerification",
        "completed_audit",
        "failed_audit",
        "parse_audit",
        "parse_input",
        "parse_output",
        "project_input",
        "refused_audit",
        "resolve_citation",
        "resolve_evidence",
        "serialize_audit",
        "serialize_input",
        "serialize_output",
        "validate_audit",
        "validate_input",
        "validate_output",
    }
    assert set(atlas_ai_analysis.__all__) == expected


def test_frozen_policy_constants_match_phase_18a_and_snapshot_allowlist():
    policy = _load(SPEC / "policy.json")
    snapshot_allowlist = _load(SNAPSHOT / "allowlist.json")

    assert list(atlas_ai_analysis.EXPLANATION_PURPOSES) == policy[
        "explanation_purposes"
    ]
    assert list(atlas_ai_analysis.SNAPSHOT_ALLOWLIST) == snapshot_allowlist["paths"]
    assert atlas_ai_analysis.INPUT_SCHEMA_VERSION == policy["contracts"]["input"]
    assert atlas_ai_analysis.OUTPUT_SCHEMA_VERSION == policy["contracts"]["output"]
    assert atlas_ai_analysis.AUDIT_SCHEMA_VERSION == policy["contracts"]["audit"]
    assert atlas_ai_analysis.POLICY_VERSION == policy["policy_version"]
    with pytest.raises(TypeError):
        atlas_ai_analysis.PURPOSE_EVIDENCE_PATHS["strategy_explanation"] = ()


def test_projection_exactly_matches_phase_18a_golden_input():
    eligible = _eligible()

    assert serialize_input(eligible.analysis_input, eligible.snapshot) == json.dumps(
        _golden("input.complete-current.json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert plain(eligible.analysis_input) == _golden("input.complete-current.json")
    assert eligible.freshness == "current"


def test_projection_is_deterministic_and_recursively_immutable():
    source = _snapshot("complete-current-candidate.canonical.json")
    first = _eligible(source)
    second = _eligible(copy.deepcopy(source))

    assert serialize_input(first.analysis_input, first.snapshot) == serialize_input(
        second.analysis_input, second.snapshot
    )
    assert isinstance(first.analysis_input, MappingProxyType)
    with pytest.raises(TypeError):
        first.analysis_input["purpose"] = "risk_explanation"
    with pytest.raises(TypeError):
        first.analysis_input["evidence_items"][0]["value"] = "changed"
    with pytest.raises(TypeError):
        first.snapshot["evidence"]["strategy"]["decisions"][0]["disposition"] = "rejected"


@pytest.mark.parametrize("purpose", atlas_ai_analysis.EXPLANATION_PURPOSES)
def test_every_frozen_purpose_has_a_valid_default_projection(purpose):
    source = _snapshot("complete-current-candidate.canonical.json")
    result = project_input(source, _verification(source), INPUT_ID, purpose)

    assert isinstance(result, EligibleAnalysis)
    assert result.analysis_input["purpose"] == purpose
    validate_input(result.analysis_input, result.snapshot)


def test_unknown_purpose_is_rejected_before_projection():
    source = _snapshot("complete-current-candidate.canonical.json")
    with pytest.raises(AIAnalysisValidationError, match="purpose"):
        project_input(source, _verification(source), INPUT_ID, "trade_recommendation")


@pytest.mark.parametrize(
    ("filename", "verification_status", "expected"),
    (
        (
            "stale-unavailable-no-signal-with-risk.canonical.json",
            "verified",
            "snapshot_stale",
        ),
        ("no-data.canonical.json", "verified", "snapshot_unavailable"),
        (
            "complete-current-candidate.canonical.json",
            "corrupted",
            "snapshot_integrity_failed",
        ),
    ),
)
def test_fail_closed_refusal_mappings(filename, verification_status, expected):
    source = _snapshot(filename)
    result = project_input(
        source,
        _verification(source, verification_status),
        INPUT_ID,
        "market_snapshot_explanation",
    )

    assert isinstance(result, RefusedAnalysis)
    assert result.reason == expected
    assert not hasattr(result, "analysis_input")
    assert not hasattr(result, "analysis_output")
    assert not hasattr(result, "generator")


def test_unsupported_snapshot_refuses_without_digest_computation():
    source = _snapshot("complete-current-candidate.canonical.json")
    source["snapshot_schema_version"] = "trader_now_snapshot.v999"

    result = project_input(
        source, _verification(source), INPUT_ID, "market_snapshot_explanation"
    )

    assert isinstance(result, RefusedAnalysis)
    assert result.reason == "snapshot_schema_unsupported"


def test_verifier_identity_mismatch_is_not_coerced_into_a_refusal():
    source = _snapshot("complete-current-candidate.canonical.json")
    verification = SnapshotVerification(
        "019849d1-8c00-7000-8000-000000000099",
        source["integrity"]["evidence_digest"],
        "verified",
    )
    with pytest.raises(AIAnalysisValidationError, match="identity mismatch"):
        project_input(source, verification, INPUT_ID, "market_snapshot_explanation")


def test_declared_digest_disagreement_fails_closed_without_recomputing():
    source = _snapshot("complete-current-candidate.canonical.json")
    verification = _verification(source)
    source["integrity"]["evidence_digest"] = "a" * 64

    result = project_input(
        source, verification, INPUT_ID, "market_snapshot_explanation"
    )

    assert isinstance(result, RefusedAnalysis)
    assert result.reason == "snapshot_integrity_failed"


def test_duplicate_evidence_paths_are_rejected():
    source = _snapshot("complete-current-candidate.canonical.json")
    with pytest.raises(AIAnalysisValidationError, match="unique"):
        project_input(
            source,
            _verification(source),
            INPUT_ID,
            "strategy_explanation",
            (GOLDEN_PATHS[0], GOLDEN_PATHS[0]),
        )


@pytest.mark.parametrize(
    "path",
    (
        "",
        "/evidence",
        "/integrity/evidence_digest",
        "#/evidence/strategy",
        "/evidence/*/status",
        "/evidence/strategy/decisions/01/disposition",
        "/evidence/strategy/decisions/99/disposition",
        "/evidence/repository/private_connection",
    ),
)
def test_restricted_citation_boundary_rejects_invalid_paths(path):
    with pytest.raises(AIAnalysisCitationError):
        resolve_evidence(_eligible().snapshot, path)


def test_json_pointer_escaping_and_leaf_resolution():
    source = _snapshot("complete-current-candidate.canonical.json")
    source["evidence"]["context"]["data"]["a/b"] = {"c~d": "safe"}
    # Context is allowlisted as a complete section.
    assert resolve_evidence(source, "/evidence/context/data/a~1b/c~0d") == "safe"


def test_all_phase_18a_golden_outputs_and_audits_round_trip():
    eligible = _eligible()
    available = _golden("output.complete-current.json")
    unavailable = _golden("output.unavailable.json")
    completed = _golden("audit.complete-current.json")
    refused = _golden("audit.stale-refusal.json")

    validate_output(available, eligible)
    validate_output(unavailable, eligible)
    validate_audit(completed)
    validate_audit(refused)
    assert plain(parse_output(serialize_output(available, eligible), eligible)) == available
    assert plain(parse_output(serialize_output(unavailable, eligible), eligible)) == unavailable
    assert plain(parse_audit(serialize_audit(completed))) == completed
    assert plain(parse_audit(serialize_audit(refused))) == refused
    assert plain(
        parse_input(
            serialize_input(eligible.analysis_input, eligible.snapshot),
            eligible.snapshot,
        )
    ) == plain(eligible.analysis_input)


def test_available_and_unavailable_representations_are_exclusive():
    eligible = _eligible()
    available = _golden("output.complete-current.json")
    unavailable = _golden("output.unavailable.json")

    available["unavailable_reason"] = "provider_timeout"
    with pytest.raises(AIAnalysisValidationError):
        validate_output(available, eligible)
    unavailable["summary"] = "fallback prose is forbidden"
    with pytest.raises(AIAnalysisValidationError):
        validate_output(unavailable, eligible)


def test_every_material_claim_requires_unique_resolving_citations():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["citations"] = []
    with pytest.raises(AIAnalysisCitationError):
        validate_output(output, eligible)

    output = _golden("output.complete-current.json")
    citation = output["claims"][0]["citations"][0]
    output["claims"][0]["citations"].append(citation)
    with pytest.raises(AIAnalysisCitationError):
        validate_output(output, eligible)


def test_citation_must_be_present_in_input_even_when_snapshot_path_exists():
    eligible = _eligible()
    with pytest.raises(AIAnalysisCitationError, match="not present"):
        resolve_citation("/evidence/strategy/decisions/0/direction", eligible)


def test_delayed_evidence_requires_explicit_limitation():
    source = _snapshot("delayed-insufficient-rejected.canonical.json")
    eligible = _eligible(source)
    output = _golden("output.complete-current.json")
    output["snapshot_id"] = source["snapshot_id"]
    output["evidence_digest"] = source["integrity"]["evidence_digest"]
    output["claims"] = [
        {
            "claim_id": "claim-1",
            "kind": "explanation",
            "text": "The deterministic strategy state is rejected.",
            "citations": ["/evidence/strategy/decisions/0/disposition"],
        }
    ]
    output["summary"] = "The delayed snapshot contains a rejected strategy state."
    output["limitations"] = ["advisory_only", "single_snapshot_only"]

    with pytest.raises(AIAnalysisValidationError, match="delayed"):
        validate_output(output, eligible)
    output["limitations"].append("delayed_evidence")
    validate_output(output, eligible)


def test_strategy_state_contradiction_is_rejected():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["text"] = "The deterministic strategy rejected this setup."

    with pytest.raises(AIAnalysisAuthorityError, match="contradicts"):
        validate_output(output, eligible)


@pytest.mark.parametrize("contradiction", ("rejected", "declined", "denied"))
def test_strategy_state_contradiction_synonyms_are_rejected(contradiction):
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["text"] = (
        f"The deterministic strategy {contradiction} this setup."
    )

    with pytest.raises(AIAnalysisAuthorityError, match="contradicts"):
        validate_output(output, eligible)


def test_summary_cannot_bypass_deterministic_contradiction_detection():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["summary"] = "The deterministic strategy rejected this setup."

    with pytest.raises(AIAnalysisAuthorityError, match="contradicts"):
        validate_output(output, eligible)


@pytest.mark.parametrize(
    "text",
    (
        "Replace the deterministic candidate with an approved decision.",
        "Recalculate risk and override the deterministic result.",
        "Place a market buy order now.",
        "Query the database for more evidence.",
    ),
)
def test_recomputation_execution_and_external_access_are_rejected(text):
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["text"] = text

    with pytest.raises(AIAnalysisAuthorityError):
        validate_output(output, eligible)


def test_invented_deterministic_number_is_rejected():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["text"] = (
        "The deterministic strategy state is candidate with confidence 0.99."
    )
    with pytest.raises(AIAnalysisAuthorityError, match="numeric"):
        validate_output(output, eligible)


def test_adversarial_evidence_strings_remain_untrusted_values():
    vectors = _load(SPEC / "adversarial" / "vectors.json")["vectors"]
    for vector in vectors:
        source = _snapshot("complete-current-candidate.canonical.json")
        _replace_pointer(source, vector["evidence_path"], vector["untrusted_value"])
        eligible = _eligible(
            source,
            paths=(vector["evidence_path"],),
            purpose="market_snapshot_explanation",
        )
        assert eligible.analysis_input["evidence_items"][0]["value"] == (
            vector["untrusted_value"]
        )
        assert not hasattr(eligible, "instructions")
        assert not hasattr(eligible, "tools")


def test_completed_refused_and_failed_audits_match_contract():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    completed = completed_audit(eligible, output, AUDIT_ID, GENERATOR)
    assert completed == _golden("audit.complete-current.json")

    refusal = RefusedAnalysis(
        snapshot_id="019849d1-8c00-7000-8000-000000000004",
        evidence_digest=(
            "5812763f13238fe7258a5a8eaeda96da13ecbf87d7ee4d1f644929fdbb3d87d1"
        ),
        purpose="market_snapshot_explanation",
        reason="snapshot_stale",
    )
    refused = refused_audit(
        refusal,
        AnalysisAuditIdentity(
            "019c1234-0000-7000-8000-000000000004",
            "2026-07-26T12:00:03.000000Z",
        ),
    )
    assert plain(refused) == _golden("audit.stale-refusal.json")
    assert refused["generator"] is None

    failed = failed_audit(eligible, AUDIT_ID, "provider_timeout", GENERATOR)
    assert failed["outcome"] == "failed"
    assert failed["analysis_output_id"] is None
    assert failed["reason_code"] == "provider_timeout"
    validate_audit(failed)


def test_refused_audit_cannot_contain_input_output_or_generator():
    refused = _golden("audit.stale-refusal.json")
    for field, value in (
        ("analysis_input_id", INPUT_ID.analysis_input_id),
        ("analysis_output_id", "019c1234-0000-7000-8000-000000000002"),
        (
            "generator",
            {"provider_id": "synthetic-provider", "model_id": "synthetic-model-v1"},
        ),
    ):
        changed = copy.deepcopy(refused)
        changed[field] = value
        with pytest.raises(AIAnalysisValidationError, match="refused"):
            validate_audit(changed)


def test_identity_and_generator_value_types_are_immutable():
    with pytest.raises(FrozenInstanceError):
        INPUT_ID.created_at = "different"
    with pytest.raises(FrozenInstanceError):
        GENERATOR.model_id = "different"


def test_all_phase_18a_negative_vectors_are_enforced():
    eligible = _eligible()
    vectors = _load(SPEC / "negative" / "vectors.json")["vectors"]

    for vector in vectors:
        base = _load(SPEC / vector["base"])
        changed = _apply_mutation(base, vector["mutation"])
        name = vector["name"]
        with pytest.raises(AIAnalysisValidationError):
            if name.startswith("input_") or name == "unknown_contract_version":
                validate_input(changed, eligible.snapshot)
            elif name.startswith("output_"):
                validate_output(changed, eligible)
            elif name.startswith("audit_"):
                validate_audit(changed)
            else:  # pragma: no cover - vector manifest is itself frozen by 18A
                raise AssertionError(f"unrouted negative vector: {name}")


@pytest.mark.parametrize(
    "payload",
    (
        b"\xef\xbb\xbf{}",
        '{"schema_version":"ai_analysis_input.v1","schema_version":"duplicate"}',
        '{"not":"closed"}',
        '{"value":NaN}',
    ),
)
def test_parser_rejects_noncanonical_or_ambiguous_inputs(payload):
    source = _snapshot("complete-current-candidate.canonical.json")
    with pytest.raises(AIAnalysisValidationError):
        parse_input(payload, source)


def test_package_dependency_boundary_is_pure_and_one_way():
    forbidden = {
        "anthropic",
        "fastapi",
        "httpx",
        "openai",
        "psycopg",
        "railway",
        "requests",
        "sqlalchemy",
        "atlas",
        "atlas_snapshot_api",
        "atlas_snapshot_capture",
        "atlas_snapshot_store",
    }
    imports: set[str] = set()
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    assert not imports.intersection(forbidden)
    assert imports <= {
        "__future__",
        "ast",
        "collections",
        "dataclasses",
        "decimal",
        "json",
        "re",
        "types",
        "typing",
        "atlas_snapshot",
        "errors",
        "models",
        "sdk",
        "_json",
    }


def test_sdk_never_computes_snapshot_digest_or_invokes_any_provider():
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py")
    ).lower()

    assert "verify(" not in combined
    assert "digest(" not in combined
    assert "hashlib" not in combined
    assert "messages.create" not in combined
    assert "prompt" not in combined
    assert "http" not in combined
    assert "api_key" not in combined
