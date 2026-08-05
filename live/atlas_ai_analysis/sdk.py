"""Pure deterministic implementation of the frozen Phase 18A contracts."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, cast

from atlas_snapshot import SnapshotValidationError
from atlas_snapshot import validate as validate_snapshot

from ._json import canonical_bytes, freeze, parse_json, plain
from .errors import (
    AIAnalysisAuthorityError,
    AIAnalysisCitationError,
    AIAnalysisValidationError,
)
from .models import (
    AnalysisAuditIdentity,
    AnalysisInputIdentity,
    EligibleAnalysis,
    FailureReason,
    GeneratorIdentity,
    RefusedAnalysis,
    SnapshotVerification,
    ValidatedAnalysisOutput,
    _validated_analysis_output,
)

INPUT_SCHEMA_VERSION = "ai_analysis_input.v1"
OUTPUT_SCHEMA_VERSION = "ai_analysis_output.v1"
AUDIT_SCHEMA_VERSION = "ai_analysis_audit.v1"
POLICY_VERSION = "ai_analysis_policy.v1"
SNAPSHOT_SCHEMA_VERSION = "trader_now_snapshot.v1"
EVIDENCE_PROFILE = "trader_now_complete.v1"
CANONICALIZATION_PROFILE = "atlas-jcs.v1"

EXPLANATION_PURPOSES = (
    "market_snapshot_explanation",
    "setup_explanation",
    "strategy_explanation",
    "risk_explanation",
    "availability_explanation",
)
REFUSAL_REASONS = (
    "snapshot_stale",
    "snapshot_unavailable",
    "snapshot_integrity_failed",
    "snapshot_schema_unsupported",
)
FAILURE_REASONS = (
    "provider_timeout",
    "provider_unavailable",
    "invalid_output",
    "missing_citation",
    "deterministic_state_contradiction",
    "prohibited_content",
    "cost_limit",
    "internal_unavailable",
)
LIMITATIONS = (
    "advisory_only",
    "single_snapshot_only",
    "delayed_evidence",
    "risk_unavailable",
    "decision_unavailable",
    "insufficient_evidence",
)

_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
_POINTER = re.compile(
    r"^/evidence/(?:[^~/*?#]|~0|~1)+(?:/(?:[^~/*?#]|~0|~1)+)*$"
)
_CLAIM_ID = re.compile(r"^claim-[1-9][0-9]*$")
_DECIMAL_TOKEN = re.compile(r"(?<![A-Za-z0-9_.])-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")

# Frozen from trader_now_snapshot/v1/allowlist.json. A Phase 17 contract change
# requires a new Phase 18 contract version rather than in-place widening.
SNAPSHOT_ALLOWLIST = (
    "domain_schema_version",
    "evaluated_at",
    "input_snapshot_at",
    "identity",
    "trust",
    "availability",
    "market.availability",
    "market.history_availability",
    "market.economic_instrument",
    "market.market_data_series",
    "market.listed_instrument",
    "market.observed_at",
    "market.latest_closed_at",
    "market.bar_count",
    "market.source_schema_versions",
    "market.latest_bar",
    "source_trust",
    "rules",
    "setups",
    "context",
    "interpretations",
    "strategy",
    "risk",
    "decision",
)

PURPOSE_EVIDENCE_PATHS = MappingProxyType({
    "market_snapshot_explanation": (
        "/evidence/evaluated_at",
        "/evidence/input_snapshot_at",
        "/evidence/identity",
        "/evidence/trust",
        "/evidence/availability",
        "/evidence/market/availability",
        "/evidence/market/history_availability",
        "/evidence/market/economic_instrument",
        "/evidence/market/market_data_series",
        "/evidence/market/listed_instrument",
        "/evidence/market/observed_at",
        "/evidence/market/latest_closed_at",
        "/evidence/market/bar_count",
        "/evidence/market/source_schema_versions",
        "/evidence/market/latest_bar",
        "/evidence/source_trust",
    ),
    "setup_explanation": (
        "/evidence/identity",
        "/evidence/trust",
        "/evidence/rules",
        "/evidence/setups",
        "/evidence/context",
        "/evidence/interpretations",
    ),
    "strategy_explanation": (
        "/evidence/identity",
        "/evidence/trust",
        "/evidence/availability",
        "/evidence/strategy",
        "/evidence/risk",
        "/evidence/decision",
    ),
    "risk_explanation": (
        "/evidence/identity",
        "/evidence/trust",
        "/evidence/strategy",
        "/evidence/risk",
        "/evidence/decision",
    ),
    "availability_explanation": (
        "/evidence/evaluated_at",
        "/evidence/input_snapshot_at",
        "/evidence/trust",
        "/evidence/availability",
        "/evidence/market/availability",
        "/evidence/market/history_availability",
        "/evidence/source_trust",
    ),
})

_PROHIBITED_PATTERNS = (
    re.compile(r"\b(?:place|submit|send|route|execute|cancel|approve)\b.{0,30}\border\b", re.IGNORECASE),
    re.compile(r"\b(?:buy|sell)\b.{0,20}\b(?:now|market|limit|contract)", re.IGNORECASE),
    re.compile(r"\bquery\b.{0,20}\bdatabase\b", re.IGNORECASE),
    re.compile(r"\baccess\b.{0,20}\b(?:repository|broker|tradernow)\b", re.IGNORECASE),
)
_RECOMPUTATION_PATTERNS = (
    re.compile(r"\b(?:override|replace|recompute|recalculate)\b", re.IGNORECASE),
    re.compile(r"\bstrategy\b.{0,20}\b(?:wrong|incorrect)\b", re.IGNORECASE),
    re.compile(r"\brisk\b.{0,20}\b(?:wrong|incorrect)\b", re.IGNORECASE),
)
_STATE_TERMS = frozenset(
    {
        "candidate",
        "rejected",
        "no_signal",
        "approved",
        "not_implemented",
        "available",
        "unavailable",
    }
)
_STATE_ALIASES = {
    "candidate": (re.compile(r"\bcandidate\b", re.IGNORECASE),),
    "rejected": (
        re.compile(r"\brejected\b", re.IGNORECASE),
        re.compile(r"\bdeclined\b", re.IGNORECASE),
        re.compile(r"\bdenied\b", re.IGNORECASE),
    ),
    "no_signal": (re.compile(r"\bno[ _-]signal\b", re.IGNORECASE),),
    "approved": (re.compile(r"\bapproved\b", re.IGNORECASE),),
    "not_implemented": (
        re.compile(r"\bnot[ _-]implemented\b", re.IGNORECASE),
    ),
    "available": (re.compile(r"\bavailable\b", re.IGNORECASE),),
    "unavailable": (re.compile(r"\bunavailable\b", re.IGNORECASE),),
    "null": (
        re.compile(r"\babsent\b", re.IGNORECASE),
        re.compile(r"\bnull\b", re.IGNORECASE),
    ),
}

_INPUT_KEYS = frozenset(
    {
        "schema_version",
        "analysis_input_id",
        "created_at",
        "purpose",
        "snapshot",
        "evidence_items",
    }
)
_SNAPSHOT_REF_KEYS = frozenset(
    {
        "snapshot_id",
        "evidence_digest",
        "snapshot_schema_version",
        "evidence_profile",
        "canonicalization_profile",
        "integrity_status",
    }
)
_OUTPUT_KEYS = frozenset(
    {
        "schema_version",
        "analysis_output_id",
        "analysis_input_id",
        "snapshot_id",
        "evidence_digest",
        "purpose",
        "status",
        "summary",
        "claims",
        "limitations",
        "unavailable_reason",
    }
)
_AUDIT_KEYS = frozenset(
    {
        "schema_version",
        "analysis_audit_id",
        "recorded_at",
        "analysis_input_id",
        "analysis_output_id",
        "snapshot_id",
        "evidence_digest",
        "purpose",
        "contract_versions",
        "outcome",
        "reason_code",
        "generator",
    }
)


def project_input(
    snapshot: Mapping[str, Any],
    verification: SnapshotVerification,
    identity: AnalysisInputIdentity,
    purpose: str,
    evidence_paths: Sequence[str] | None = None,
) -> EligibleAnalysis | RefusedAnalysis:
    """Project one verified Snapshot or return a fail-closed refusal."""
    _purpose(purpose)
    snapshot_id, declared_digest = _snapshot_identity(snapshot, verification)
    if verification.status == "corrupted":
        return RefusedAnalysis(
            snapshot_id, verification.evidence_digest, purpose, "snapshot_integrity_failed"
        )
    if not _supported_snapshot(snapshot):
        return RefusedAnalysis(
            snapshot_id, verification.evidence_digest, purpose, "snapshot_schema_unsupported"
        )
    try:
        validate_snapshot(snapshot)
    except SnapshotValidationError:
        return RefusedAnalysis(
            snapshot_id, verification.evidence_digest, purpose, "snapshot_integrity_failed"
        )
    if declared_digest != verification.evidence_digest:
        return RefusedAnalysis(
            snapshot_id, verification.evidence_digest, purpose, "snapshot_integrity_failed"
        )

    freshness = _freshness(snapshot)
    if freshness == "stale":
        return RefusedAnalysis(snapshot_id, declared_digest, purpose, "snapshot_stale")
    if freshness not in {"current", "delayed"} or _snapshot_unavailable(snapshot):
        return RefusedAnalysis(snapshot_id, declared_digest, purpose, "snapshot_unavailable")

    _uuid7(identity.analysis_input_id, "analysis_input_id")
    _timestamp(identity.created_at, "created_at")
    selected = tuple(evidence_paths or PURPOSE_EVIDENCE_PATHS[purpose])
    if not selected or len(selected) > 128 or len(selected) != len(set(selected)):
        raise AIAnalysisValidationError(
            "evidence paths must be unique and contain between 1 and 128 items"
        )
    items = []
    for path in selected:
        value = resolve_evidence(snapshot, path)
        items.append({"path": path, "value": plain(value)})

    analysis_input = {
        "schema_version": INPUT_SCHEMA_VERSION,
        "analysis_input_id": identity.analysis_input_id,
        "created_at": identity.created_at,
        "purpose": purpose,
        "snapshot": {
            "snapshot_id": snapshot_id,
            "evidence_digest": declared_digest,
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
            "evidence_profile": EVIDENCE_PROFILE,
            "canonicalization_profile": CANONICALIZATION_PROFILE,
            "integrity_status": "verified",
        },
        "evidence_items": items,
    }
    frozen = freeze(analysis_input)
    validate_input(frozen, snapshot)
    return EligibleAnalysis(snapshot=freeze(plain(snapshot)), analysis_input=frozen, freshness=cast(Any, freshness))


def validate_input(value: Mapping[str, Any], snapshot: Mapping[str, Any]) -> None:
    _closed(value, _INPUT_KEYS, "analysis input")
    if value["schema_version"] != INPUT_SCHEMA_VERSION:
        raise AIAnalysisValidationError("unsupported analysis input schema")
    _uuid7(value["analysis_input_id"], "analysis_input_id")
    _timestamp(value["created_at"], "created_at")
    _purpose(value["purpose"])
    reference = _mapping(value["snapshot"], "snapshot reference")
    _closed(reference, _SNAPSHOT_REF_KEYS, "snapshot reference")
    if reference["snapshot_schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise AIAnalysisValidationError("unsupported snapshot schema")
    if reference["evidence_profile"] != EVIDENCE_PROFILE:
        raise AIAnalysisValidationError("unsupported evidence profile")
    if reference["canonicalization_profile"] != CANONICALIZATION_PROFILE:
        raise AIAnalysisValidationError("unsupported canonicalization profile")
    if reference["integrity_status"] != "verified":
        raise AIAnalysisValidationError("verified snapshot is required")
    _uuid7(reference["snapshot_id"], "snapshot_id")
    _sha256(reference["evidence_digest"], "evidence_digest")
    if reference["snapshot_id"] != snapshot.get("snapshot_id"):
        raise AIAnalysisValidationError("analysis input snapshot identity mismatch")
    integrity = _mapping(snapshot.get("integrity"), "snapshot integrity")
    if reference["evidence_digest"] != integrity.get("evidence_digest"):
        raise AIAnalysisValidationError("analysis input digest mismatch")

    items = value["evidence_items"]
    if not isinstance(items, (tuple, list)) or not 1 <= len(items) <= 128:
        raise AIAnalysisValidationError("evidence_items must contain 1 to 128 items")
    paths: set[str] = set()
    for item_value in items:
        item = _mapping(item_value, "evidence item")
        _closed(item, frozenset({"path", "value"}), "evidence item")
        path = item["path"]
        if not isinstance(path, str):
            raise AIAnalysisValidationError("evidence path must be text")
        if path in paths:
            raise AIAnalysisValidationError("evidence paths must be unique")
        paths.add(path)
        if plain(resolve_evidence(snapshot, path)) != plain(item["value"]):
            raise AIAnalysisValidationError("evidence item disagrees with Snapshot")


def validate_output(
    value: Mapping[str, Any],
    eligible: EligibleAnalysis,
) -> ValidatedAnalysisOutput:
    """Validate structural and semantic output against one eligible input."""
    normalization_failed = False
    try:
        value = cast(Mapping[str, Any], _trusted_output_value(value))
    except AIAnalysisValidationError:
        raise
    except Exception:
        normalization_failed = True
    if normalization_failed:
        raise AIAnalysisValidationError("analysis output normalization failed")
    _closed(value, _OUTPUT_KEYS, "analysis output")
    if value["schema_version"] != OUTPUT_SCHEMA_VERSION:
        raise AIAnalysisValidationError("unsupported analysis output schema")
    _uuid7(value["analysis_output_id"], "analysis_output_id")
    _uuid7(value["analysis_input_id"], "analysis_input_id")
    _uuid7(value["snapshot_id"], "snapshot_id")
    _sha256(value["evidence_digest"], "evidence_digest")
    _purpose(value["purpose"])
    analysis_input = eligible.analysis_input
    reference = cast(Mapping[str, Any], analysis_input["snapshot"])
    for field, expected in (
        ("analysis_input_id", analysis_input["analysis_input_id"]),
        ("snapshot_id", reference["snapshot_id"]),
        ("evidence_digest", reference["evidence_digest"]),
        ("purpose", analysis_input["purpose"]),
    ):
        if value[field] != expected:
            raise AIAnalysisValidationError(f"output {field} mismatch")

    status = value["status"]
    claims = value["claims"]
    limitations = value["limitations"]
    if not isinstance(claims, (tuple, list)) or not isinstance(limitations, (tuple, list)):
        raise AIAnalysisValidationError("claims and limitations must be arrays")
    if len(limitations) > 16 or len(limitations) != len(set(limitations)) or any(
        item not in LIMITATIONS for item in limitations
    ):
        raise AIAnalysisValidationError("invalid or duplicate limitation")
    if status == "available":
        if not isinstance(value["summary"], str) or not 1 <= len(value["summary"]) <= 4000:
            raise AIAnalysisValidationError("available output requires a summary")
        if not 1 <= len(claims) <= 32:
            raise AIAnalysisValidationError("available output requires 1 to 32 claims")
        if value["unavailable_reason"] is not None:
            raise AIAnalysisValidationError("available output cannot have unavailable_reason")
        if "advisory_only" not in limitations:
            raise AIAnalysisValidationError("available output must be advisory_only")
        if eligible.freshness == "delayed" and "delayed_evidence" not in limitations:
            raise AIAnalysisValidationError("delayed evidence limitation is required")
        _validate_claims(claims, eligible)
        _validate_prohibited_text(value["summary"])
        deterministic_items = [
            (item["path"], item["value"])
            for item in cast(
                Sequence[Mapping[str, Any]],
                eligible.analysis_input["evidence_items"],
            )
            if any(
                item["path"] == root or item["path"].startswith(f"{root}/")
                for root in (
                    "/evidence/strategy",
                    "/evidence/risk",
                    "/evidence/decision",
                )
            )
        ]
        _validate_deterministic_claim(
            value["summary"],
            [item[0] for item in deterministic_items],
            [item[1] for item in deterministic_items],
        )
    elif status == "unavailable":
        if value["summary"] is not None or claims or limitations:
            raise AIAnalysisValidationError(
                "unavailable output cannot contain narrative, claims, or limitations"
            )
        if value["unavailable_reason"] not in FAILURE_REASONS:
            raise AIAnalysisValidationError("unavailable output requires a failure reason")
    else:
        raise AIAnalysisValidationError("invalid output status")
    return _validated_analysis_output(value)


def _trusted_output_value(value: Any) -> Any:
    """Copy provider data into exact immutable JSON-domain built-in values."""
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AIAnalysisValidationError("analysis output key must be text")
            normalized_key = str.__str__(key)
            if normalized_key in copied:
                raise AIAnalysisValidationError("analysis output keys collide")
            copied[normalized_key] = _trusted_output_value(item)
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(_trusted_output_value(item) for item in value)
    if value is None or type(value) is bool:
        return value
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, int):
        return int.__int__(value)
    if isinstance(value, float):
        return float.__float__(value)
    raise AIAnalysisValidationError("analysis output contains a non-JSON value")


def resolve_citation(path: str, eligible: EligibleAnalysis) -> Any:
    input_items = {
        item["path"]: item["value"]
        for item in cast(Sequence[Mapping[str, Any]], eligible.analysis_input["evidence_items"])
    }
    if path not in input_items:
        raise AIAnalysisCitationError("citation is not present in analysis input")
    authoritative = resolve_evidence(eligible.snapshot, path)
    if plain(authoritative) != plain(input_items[path]):
        raise AIAnalysisCitationError("citation value disagrees with Snapshot")
    return authoritative


def resolve_evidence(snapshot: Mapping[str, Any], path: str) -> Any:
    tokens = _pointer_tokens(path)
    dotted = ".".join(tokens[1:])
    if not any(dotted == item or dotted.startswith(f"{item}.") for item in SNAPSHOT_ALLOWLIST):
        raise AIAnalysisCitationError("evidence path is not Snapshot-allowlisted")
    current: Any = snapshot
    try:
        for token in tokens:
            if isinstance(current, (tuple, list)):
                if not re.fullmatch(r"(?:0|[1-9][0-9]*)", token):
                    raise AIAnalysisCitationError("invalid array index in citation")
                current = current[int(token)]
            elif isinstance(current, Mapping):
                current = current[token]
            else:
                raise AIAnalysisCitationError("citation traverses a scalar")
    except (KeyError, IndexError) as error:
        raise AIAnalysisCitationError("citation does not resolve") from error
    return current


def parse_input(payload: bytes | str, snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _mapping(parse_json(payload), "analysis input")
    validate_input(value, snapshot)
    return freeze(value)


def parse_output(payload: bytes | str, eligible: EligibleAnalysis) -> Mapping[str, Any]:
    value = _mapping(parse_json(payload), "analysis output")
    validate_output(value, eligible)
    return freeze(value)


def parse_audit(payload: bytes | str) -> Mapping[str, Any]:
    value = _mapping(parse_json(payload), "analysis audit")
    validate_audit(value)
    return freeze(value)


def serialize_input(value: Mapping[str, Any], snapshot: Mapping[str, Any]) -> bytes:
    validate_input(value, snapshot)
    return canonical_bytes(value)


def serialize_output(value: Mapping[str, Any], eligible: EligibleAnalysis) -> bytes:
    validate_output(value, eligible)
    return canonical_bytes(value)


def serialize_audit(value: Mapping[str, Any]) -> bytes:
    validate_audit(value)
    return canonical_bytes(value)


def completed_audit(
    eligible: EligibleAnalysis,
    output: Mapping[str, Any],
    identity: AnalysisAuditIdentity,
    generator: GeneratorIdentity,
) -> Mapping[str, Any]:
    validated = validate_output(output, eligible)
    return completed_audit_from_validated_output(eligible, validated, identity, generator)


def completed_audit_from_validated_output(
    eligible: EligibleAnalysis,
    output: ValidatedAnalysisOutput,
    identity: AnalysisAuditIdentity,
    generator: GeneratorIdentity,
) -> Mapping[str, Any]:
    """Build a completed audit from the exact trusted Phase 18B output type."""
    if type(output) is not ValidatedAnalysisOutput:
        raise TypeError("validated output is required")
    if output.status != "available":
        raise AIAnalysisValidationError("completed audit requires available output")
    value = output.value
    return _audit(
        identity=identity,
        analysis_input_id=eligible.analysis_input["analysis_input_id"],
        analysis_output_id=value["analysis_output_id"],
        snapshot_id=value["snapshot_id"],
        evidence_digest=value["evidence_digest"],
        purpose=value["purpose"],
        outcome="completed",
        reason_code=None,
        generator=generator,
    )


def refused_audit(
    refusal: RefusedAnalysis,
    identity: AnalysisAuditIdentity,
) -> Mapping[str, Any]:
    return _audit(
        identity=identity,
        analysis_input_id=None,
        analysis_output_id=None,
        snapshot_id=refusal.snapshot_id,
        evidence_digest=refusal.evidence_digest,
        purpose=refusal.purpose,
        outcome="refused",
        reason_code=refusal.reason,
        generator=None,
    )


def failed_audit(
    eligible: EligibleAnalysis,
    identity: AnalysisAuditIdentity,
    reason: FailureReason,
    generator: GeneratorIdentity | None = None,
) -> Mapping[str, Any]:
    if reason not in FAILURE_REASONS:
        raise AIAnalysisValidationError("invalid analysis failure reason")
    reference = cast(Mapping[str, Any], eligible.analysis_input["snapshot"])
    return _audit(
        identity=identity,
        analysis_input_id=eligible.analysis_input["analysis_input_id"],
        analysis_output_id=None,
        snapshot_id=reference["snapshot_id"],
        evidence_digest=reference["evidence_digest"],
        purpose=eligible.analysis_input["purpose"],
        outcome="failed",
        reason_code=reason,
        generator=generator,
    )


def validate_audit(value: Mapping[str, Any]) -> None:
    _closed(value, _AUDIT_KEYS, "analysis audit")
    if value["schema_version"] != AUDIT_SCHEMA_VERSION:
        raise AIAnalysisValidationError("unsupported analysis audit schema")
    _uuid7(value["analysis_audit_id"], "analysis_audit_id")
    _timestamp(value["recorded_at"], "recorded_at")
    _uuid7(value["snapshot_id"], "snapshot_id")
    _sha256(value["evidence_digest"], "evidence_digest")
    _purpose(value["purpose"])
    versions = _mapping(value["contract_versions"], "contract_versions")
    _closed(versions, frozenset({"input", "output", "policy"}), "contract_versions")
    if versions != {
        "input": INPUT_SCHEMA_VERSION,
        "output": OUTPUT_SCHEMA_VERSION,
        "policy": POLICY_VERSION,
    }:
        raise AIAnalysisValidationError("unsupported audit contract versions")
    outcome = value["outcome"]
    reason = value["reason_code"]
    generator = value["generator"]
    if outcome == "completed":
        _uuid7(value["analysis_input_id"], "analysis_input_id")
        _uuid7(value["analysis_output_id"], "analysis_output_id")
        if reason is not None or generator is None:
            raise AIAnalysisValidationError("invalid completed audit")
    elif outcome == "refused":
        if (
            value["analysis_input_id"] is not None
            or value["analysis_output_id"] is not None
            or reason not in REFUSAL_REASONS
            or generator is not None
        ):
            raise AIAnalysisValidationError("invalid refused audit")
    elif outcome == "failed":
        _uuid7(value["analysis_input_id"], "analysis_input_id")
        if value["analysis_output_id"] is not None or reason not in FAILURE_REASONS:
            raise AIAnalysisValidationError("invalid failed audit")
    else:
        raise AIAnalysisValidationError("invalid audit outcome")
    if generator is not None:
        _generator(_mapping(generator, "generator"))


def _audit(
    *,
    identity: AnalysisAuditIdentity,
    analysis_input_id: Any,
    analysis_output_id: Any,
    snapshot_id: str,
    evidence_digest: str,
    purpose: str,
    outcome: str,
    reason_code: Any,
    generator: GeneratorIdentity | None,
) -> Mapping[str, Any]:
    value = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "analysis_audit_id": identity.analysis_audit_id,
        "recorded_at": identity.recorded_at,
        "analysis_input_id": analysis_input_id,
        "analysis_output_id": analysis_output_id,
        "snapshot_id": snapshot_id,
        "evidence_digest": evidence_digest,
        "purpose": purpose,
        "contract_versions": {
            "input": INPUT_SCHEMA_VERSION,
            "output": OUTPUT_SCHEMA_VERSION,
            "policy": POLICY_VERSION,
        },
        "outcome": outcome,
        "reason_code": reason_code,
        "generator": (
            None
            if generator is None
            else {"provider_id": generator.provider_id, "model_id": generator.model_id}
        ),
    }
    frozen = freeze(value)
    validate_audit(frozen)
    return frozen


def _validate_claims(claims: Sequence[Any], eligible: EligibleAnalysis) -> None:
    claim_ids: set[str] = set()
    for claim_value in claims:
        claim = _mapping(claim_value, "claim")
        _closed(claim, frozenset({"claim_id", "kind", "text", "citations"}), "claim")
        claim_id = claim["claim_id"]
        if not isinstance(claim_id, str) or not _CLAIM_ID.fullmatch(claim_id):
            raise AIAnalysisValidationError("invalid claim_id")
        if claim_id in claim_ids:
            raise AIAnalysisValidationError("claim IDs must be unique")
        claim_ids.add(claim_id)
        if claim["kind"] not in {"explanation", "attention_guidance"}:
            raise AIAnalysisValidationError("invalid claim kind")
        text = claim["text"]
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            raise AIAnalysisValidationError("invalid claim text")
        citations = claim["citations"]
        if (
            not isinstance(citations, (tuple, list))
            or not 1 <= len(citations) <= 16
            or len(citations) != len(set(citations))
        ):
            raise AIAnalysisCitationError("material claim requires unique citations")
        cited_values = [resolve_citation(path, eligible) for path in citations]
        _validate_prohibited_text(text)
        _validate_deterministic_claim(text, citations, cited_values)


def _validate_deterministic_claim(
    text: str,
    citations: Sequence[str],
    cited_values: Sequence[Any],
) -> None:
    deterministic = any(
        path == root or path.startswith(f"{root}/")
        for path in citations
        for root in ("/evidence/strategy", "/evidence/risk", "/evidence/decision")
    )
    if not deterministic:
        return
    if any(pattern.search(text) for pattern in _RECOMPUTATION_PATTERNS):
        raise AIAnalysisAuthorityError("deterministic state recomputation is prohibited")
    cited_terms = {
        item.lower()
        for value in cited_values
        for item in _scalar_texts(value)
        if item.lower() in _STATE_TERMS or item == "null"
    }
    mentioned_terms = {
        canonical
        for canonical, patterns in _STATE_ALIASES.items()
        if any(pattern.search(text) for pattern in patterns)
    }
    if not mentioned_terms <= cited_terms:
        raise AIAnalysisAuthorityError("claim contradicts deterministic state")
    cited_scalars = {item for value in cited_values for item in _scalar_texts(value)}
    for token in _DECIMAL_TOKEN.findall(text):
        if token not in cited_scalars:
            raise AIAnalysisAuthorityError(
                "claim recomputes or invents a deterministic numeric value"
            )


def _validate_prohibited_text(text: str) -> None:
    if any(pattern.search(text) for pattern in _PROHIBITED_PATTERNS):
        raise AIAnalysisAuthorityError("output contains prohibited authority or action")


def _scalar_texts(value: Any) -> Iterable[str]:
    if value is None:
        yield "null"
    elif isinstance(value, bool):
        yield str(value).lower()
    elif isinstance(value, (str, int)):
        yield str(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _scalar_texts(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _scalar_texts(item)


def _snapshot_identity(
    snapshot: Mapping[str, Any], verification: SnapshotVerification
) -> tuple[str, str | None]:
    _uuid7(verification.snapshot_id, "verified snapshot_id")
    _sha256(verification.evidence_digest, "verified evidence_digest")
    if verification.status not in {"verified", "corrupted"}:
        raise AIAnalysisValidationError("invalid verification status")
    snapshot_id = snapshot.get("snapshot_id")
    if snapshot_id != verification.snapshot_id:
        raise AIAnalysisValidationError("verification snapshot identity mismatch")
    integrity = snapshot.get("integrity")
    declared = integrity.get("evidence_digest") if isinstance(integrity, Mapping) else None
    return verification.snapshot_id, declared


def _supported_snapshot(snapshot: Mapping[str, Any]) -> bool:
    return (
        snapshot.get("snapshot_schema_version") == SNAPSHOT_SCHEMA_VERSION
        and snapshot.get("evidence_profile") == EVIDENCE_PROFILE
        and snapshot.get("canonicalization_profile") == CANONICALIZATION_PROFILE
    )


def _freshness(snapshot: Mapping[str, Any]) -> Any:
    try:
        return snapshot["evidence"]["source_trust"]["freshness"]["status"]
    except (KeyError, TypeError):
        return "unavailable"


def _snapshot_unavailable(snapshot: Mapping[str, Any]) -> bool:
    try:
        availability = snapshot["evidence"]["availability"]
        market = availability["market"]["status"]
        trust = snapshot["evidence"]["trust"]["status"]
    except (KeyError, TypeError):
        return True
    return market != "available" or trust == "untrusted"


def _pointer_tokens(path: str) -> list[str]:
    if not isinstance(path, str) or not _POINTER.fullmatch(path):
        raise AIAnalysisCitationError("citation is not an approved evidence pointer")
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in path.split("/")[1:]
    ]


def _purpose(value: Any) -> None:
    if value not in EXPLANATION_PURPOSES:
        raise AIAnalysisValidationError("unsupported explanation purpose")


def _closed(value: Mapping[str, Any], keys: frozenset[str], label: str) -> None:
    if set(value) != keys:
        raise AIAnalysisValidationError(f"{label} fields do not match v1")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AIAnalysisValidationError(f"{label} must be an object")
    return value


def _uuid7(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _UUID7.fullmatch(value):
        raise AIAnalysisValidationError(f"{label} must be a lowercase UUIDv7")


def _sha256(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AIAnalysisValidationError(f"{label} must be lowercase SHA-256")


def _timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise AIAnalysisValidationError(f"{label} must be canonical UTC")


def _generator(value: Mapping[str, Any]) -> None:
    _closed(value, frozenset({"provider_id", "model_id"}), "generator")
    for field, limit in (("provider_id", 100), ("model_id", 200)):
        item = value[field]
        if not isinstance(item, str) or not 1 <= len(item) <= limit:
            raise AIAnalysisValidationError(f"invalid generator {field}")
