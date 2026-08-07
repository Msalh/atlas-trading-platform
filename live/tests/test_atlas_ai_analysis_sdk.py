"""Phase 18B golden, adversarial, semantic, and purity certification."""

from __future__ import annotations

import ast
import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import Any, get_type_hints

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
    ValidatedAnalysisOutput,
    completed_audit,
    completed_audit_from_validated_output,
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
from atlas_ai_analysis.errors import (
    OutputRejectionClassification,
    SemanticContradictionSubreason,
)
from atlas_ai_analysis.models import JSONValue

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
        "ValidatedAnalysisOutput",
        "completed_audit",
        "completed_audit_from_validated_output",
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


@pytest.mark.parametrize("candidate", [None, True, 7, 1.5, "text", [], [1]])
def test_validate_output_recursive_json_contract_rejects_non_objects(candidate):
    with pytest.raises(AIAnalysisValidationError, match="must be an object"):
        validate_output(candidate, _eligible())


def test_validate_output_annotation_uses_recursive_json_value_contract():
    assert validate_output.__annotations__["value"] == "JSONValue"
    assert get_type_hints(validate_output)["value"] is JSONValue


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

    with pytest.raises(AIAnalysisAuthorityError, match="contradicts") as raised:
        validate_output(output, eligible)
    assert (
        raised.value.semantic_contradiction_subreason
        is SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED
    )


@pytest.mark.parametrize("contradiction", ("rejected", "declined", "denied"))
def test_strategy_state_contradiction_synonyms_are_rejected(contradiction):
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["text"] = (
        f"The deterministic strategy {contradiction} this setup."
    )

    with pytest.raises(AIAnalysisAuthorityError, match="contradicts") as raised:
        validate_output(output, eligible)
    assert (
        raised.value.semantic_contradiction_subreason
        is SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED
    )


def test_summary_cannot_bypass_deterministic_contradiction_detection():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["summary"] = "The deterministic strategy rejected this setup."

    with pytest.raises(AIAnalysisAuthorityError, match="contradicts") as raised:
        validate_output(output, eligible)
    assert (
        raised.value.semantic_contradiction_subreason
        is SemanticContradictionSubreason.SUMMARY_STATE_UNSUPPORTED
    )


def test_claim_state_support_omitted_is_distinct_from_unsupported():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["citations"] = [
        "/evidence/strategy/decisions/0/confidence"
    ]
    output["claims"][0]["text"] = "The deterministic strategy is a candidate."

    with pytest.raises(AIAnalysisAuthorityError) as raised:
        validate_output(output, eligible)

    assert (
        raised.value.semantic_contradiction_subreason
        is SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED
    )


@pytest.mark.parametrize("state", ("no-signal", "not-implemented", "absent"))
def test_claim_state_unsupported_subreason_is_closed(state):
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["text"] = f"The deterministic strategy is {state}."

    with pytest.raises(AIAnalysisAuthorityError) as raised:
        validate_output(output, eligible)

    assert (
        raised.value.semantic_contradiction_subreason
        in {
            SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED,
            SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED,
        }
    )


@pytest.mark.parametrize(
    ("term", "expected"),
    (
        ("candidate", SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED),
        ("rejected", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("no_signal", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("no-signal", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("no signal", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("approved", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        (
            "not_implemented",
            SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED,
        ),
        (
            "not-implemented",
            SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED,
        ),
        (
            "not implemented",
            SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED,
        ),
        ("available", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("unavailable", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("null", SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED),
        ("declined", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("denied", SemanticContradictionSubreason.CLAIM_STATE_UNSUPPORTED),
        ("absent", SemanticContradictionSubreason.CLAIM_STATE_SUPPORT_OMITTED),
    ),
)
def test_complete_semantic_state_term_and_alias_matrix(term, expected):
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["citations"] = [
        "/evidence/strategy/decisions/0/confidence"
    ]
    output["claims"][0]["text"] = f"The deterministic strategy state is {term}."

    with pytest.raises(AIAnalysisAuthorityError) as raised:
        validate_output(output, eligible)

    assert raised.value.output_rejection is OutputRejectionClassification.SEMANTIC_CONTRADICTION
    assert raised.value.semantic_contradiction_subreason is expected


def test_mixed_supported_and_unsupported_terms_are_ambiguous():
    eligible = _eligible()
    output = _golden("output.complete-current.json")
    output["claims"][0]["citations"] = [
        "/evidence/strategy/decisions/0/confidence"
    ]
    output["claims"][0]["text"] = (
        "The deterministic strategy state is candidate and rejected."
    )

    with pytest.raises(AIAnalysisAuthorityError) as raised:
        validate_output(output, eligible)

    assert raised.value.output_rejection is OutputRejectionClassification.SEMANTIC_CONTRADICTION
    assert (
        raised.value.semantic_contradiction_subreason
        is SemanticContradictionSubreason.CLASSIFICATION_AMBIGUOUS
    )


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


def test_validate_output_returns_deeply_immutable_trusted_copy():
    eligible = _eligible()
    output = _golden("output.complete-current.json")

    validated = validate_output(output, eligible)
    original_summary = validated.value["summary"]
    original_claim_text = validated.value["claims"][0]["text"]
    original_claim_count = len(validated.value["claims"])
    output["summary"] = "mutated"
    output["claims"][0]["text"] = "mutated"
    output["claims"].append({"untrusted": "new"})

    assert isinstance(validated, ValidatedAnalysisOutput)
    assert validated.status == "available"
    assert validated.value["summary"] == original_summary
    assert validated.value["claims"][0]["text"] == original_claim_text
    assert len(validated.value["claims"]) == original_claim_count
    with pytest.raises(TypeError):
        validated.value["summary"] = "changed"
    with pytest.raises(TypeError):
        validated.value["claims"][0]["text"] = "changed"


def test_validate_output_normalizes_provider_scalar_subclasses_recursively():
    class MutableText(str):
        def __new__(cls, value):
            instance = super().__new__(cls, value)
            instance.mutable = []
            return instance

        def __str__(self):
            raise AssertionError("provider conversion override must not run")

    eligible = _eligible()
    output = _golden("output.complete-current.json")
    originals = []

    def text(value):
        item = MutableText(value)
        originals.append(item)
        return item

    for field in (
        "schema_version",
        "analysis_output_id",
        "analysis_input_id",
        "snapshot_id",
        "evidence_digest",
        "purpose",
        "status",
        "summary",
    ):
        output[field] = text(output[field])
    output["claims"] = tuple(
        {
            text(key): (
                tuple(text(item) for item in value)
                if key == "citations"
                else text(value)
            )
            for key, value in claim.items()
        }
        for claim in output["claims"]
    )
    output["limitations"] = [text(item) for item in output["limitations"]]

    validated = validate_output(output, eligible)

    def scalars(value):
        if isinstance(value, dict | MappingProxyType):
            for key, item in value.items():
                yield key
                yield from scalars(item)
        elif isinstance(value, tuple):
            for item in value:
                yield from scalars(item)
        else:
            yield value

    trusted_scalars = tuple(scalars(validated.value))
    assert validated.status == "available"
    assert type(validated.status) is str
    assert all(type(item) in {str, bool, int, float, type(None)} for item in trusted_scalars)
    assert not any(item is original for item in trusted_scalars for original in originals)
    assert all(not hasattr(item, "mutable") for item in trusted_scalars)
    for original in originals:
        original.mutable.append("changed")
    assert validated.status == "available"
    assert validated.value["summary"] == _golden("output.complete-current.json")["summary"]


def test_validate_output_normalizes_stateful_status_before_validation():
    class StatefulStatus(str):
        def __new__(cls):
            instance = super().__new__(cls, "available")
            instance.comparisons = 0
            return instance

        def __eq__(self, other):
            self.comparisons += 1
            return self.comparisons == 1 and other == "available"

        __hash__ = str.__hash__

    eligible = _eligible()
    output = _golden("output.complete-current.json")
    provider_status = StatefulStatus()
    output["status"] = provider_status

    validated = validate_output(output, eligible)

    assert provider_status.comparisons == 0
    assert type(validated.status) is str
    assert validated.status == "available"
    assert validated.status == "available"


def test_validate_output_normalizes_unavailable_reason_subclass():
    class MutableReason(str):
        pass

    eligible = _eligible()
    output = _golden("output.unavailable.json")
    reason = MutableReason(output["unavailable_reason"])
    reason.mutable = []
    output["unavailable_reason"] = reason

    validated = validate_output(output, eligible)
    reason.mutable.append("changed")

    assert validated.status == "unavailable"
    assert type(validated.unavailable_reason) is str
    assert validated.unavailable_reason == "provider_timeout"
    assert validated.unavailable_reason is not reason
    assert not hasattr(validated.unavailable_reason, "mutable")


@pytest.mark.parametrize("subclass_first", [False, True])
def test_validate_output_rejects_exact_and_subclass_key_collision(subclass_first):
    class DistinctKey(str):
        __hash__ = object.__hash__
        __eq__ = object.__eq__

        def __str__(self):
            raise AssertionError("provider conversion override must not run")

    eligible = _eligible()
    output = _golden("output.complete-current.json")
    exact_key = "status"
    subclass_key = DistinctKey("status")
    remaining = [(key, value) for key, value in output.items() if key != exact_key]
    collision = [(exact_key, "unavailable"), (subclass_key, "available")]
    if subclass_first:
        collision.reverse()
    raw = dict([*remaining, *collision])

    assert len(raw) == len(output) + 1
    assert str.__str__(subclass_key) == exact_key
    with pytest.raises(AIAnalysisValidationError, match="keys collide"):
        validate_output(raw, eligible)


def test_validate_output_rejects_two_subclass_keys_with_same_normalized_value():
    class DistinctKey(str):
        __hash__ = object.__hash__
        __eq__ = object.__eq__

        def __str__(self):
            raise AssertionError("provider conversion override must not run")

    eligible = _eligible()
    output = _golden("output.complete-current.json")
    first = DistinctKey("status")
    second = DistinctKey("status")
    remaining = [(key, value) for key, value in output.items() if key != "status"]
    raw = dict([*remaining, (first, "unavailable"), (second, "available")])

    assert len(raw) == len(output) + 1
    assert first is not second
    assert str.__str__(first) == str.__str__(second) == "status"
    with pytest.raises(AIAnalysisValidationError, match="keys collide"):
        validate_output(raw, eligible)


def test_validate_output_rejects_nested_normalized_key_collision():
    class DistinctKey(str):
        __hash__ = object.__hash__
        __eq__ = object.__eq__

        def __str__(self):
            raise AssertionError("provider conversion override must not run")

    eligible = _eligible()
    output = _golden("output.complete-current.json")
    claim = output["claims"][0]
    alias = DistinctKey("text")
    claim[alias] = "a value that must never replace the exact text field"

    assert len(claim) == 5
    assert str.__str__(alias) == "text"
    with pytest.raises(AIAnalysisValidationError, match="keys collide"):
        validate_output(output, eligible)


def test_validate_output_accepts_unique_subclass_keys_as_exact_builtins():
    class DistinctKey(str):
        __hash__ = object.__hash__
        __eq__ = object.__eq__

        def __str__(self):
            raise AssertionError("provider conversion override must not run")

    eligible = _eligible()
    output = _golden("output.complete-current.json")
    provider_keys = tuple(DistinctKey(key) for key in output)
    raw = dict(zip(provider_keys, output.values(), strict=True))

    validated = validate_output(raw, eligible)

    assert validated.status == "available"
    assert all(type(key) is str for key in validated.value)
    assert not any(key is provider_key for key in validated.value for provider_key in provider_keys)


def test_validated_output_supported_api_rejects_unchecked_construction():
    raw = _golden("output.complete-current.json")
    with pytest.raises(TypeError, match="private"):
        ValidatedAnalysisOutput(raw, object())


def test_completed_audit_from_validated_output_rejects_raw_and_lookalike_values():
    eligible = _eligible()
    raw = _golden("output.complete-current.json")

    class Lookalike:
        status = "available"
        value = raw

    class Subclass(ValidatedAnalysisOutput):
        pass

    for unchecked in (raw, Lookalike(), object.__new__(Subclass)):
        with pytest.raises(TypeError, match="validated output"):
            completed_audit_from_validated_output(
                eligible, unchecked, AUDIT_ID, GENERATOR
            )


def test_completed_audit_from_validated_output_matches_legacy_without_revalidation(
    monkeypatch,
):
    eligible = _eligible()
    raw = _golden("output.complete-current.json")
    validated = validate_output(raw, eligible)
    expected = completed_audit(eligible, raw, AUDIT_ID, GENERATOR)

    def forbidden(*args, **kwargs):
        raise AssertionError("validation must not run")

    monkeypatch.setattr(atlas_ai_analysis.sdk, "validate_output", forbidden)
    actual = completed_audit_from_validated_output(
        eligible, validated, AUDIT_ID, GENERATOR
    )

    assert actual == expected


def test_completed_audit_from_validated_output_rejects_unavailable_result():
    eligible = _eligible()
    validated = validate_output(_golden("output.unavailable.json"), eligible)
    assert validated.status == "unavailable"
    with pytest.raises(AIAnalysisValidationError, match="requires available"):
        completed_audit_from_validated_output(
            eligible, validated, AUDIT_ID, GENERATOR
        )


def test_legacy_completed_audit_still_validates_exactly_once(monkeypatch):
    eligible = _eligible()
    raw = _golden("output.complete-current.json")
    calls = 0
    original = atlas_ai_analysis.sdk.validate_output

    def counted(value, analysis):
        nonlocal calls
        calls += 1
        return original(value, analysis)

    monkeypatch.setattr(atlas_ai_analysis.sdk, "validate_output", counted)
    completed_audit(eligible, raw, AUDIT_ID, GENERATOR)
    assert calls == 1


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
        "enum",
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
