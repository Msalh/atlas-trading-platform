"""Standalone, side-effect-free TraderNow Snapshot SDK."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from ._canonical import canonical_bytes, freeze, normalize
from .errors import (
    SnapshotIntegrityError,
    SnapshotProjectionError,
    SnapshotValidationError,
)
from .models import SnapshotMetadata, SnapshotRecordIdentity

SNAPSHOT_SCHEMA_VERSION = "trader_now_snapshot.v1"
EVIDENCE_PROFILE = "trader_now_complete.v1"
CANONICALIZATION_PROFILE = "atlas-jcs.v1"
SOURCE_RESPONSE_SCHEMA_VERSION = "trader_now_response.v2"
SOURCE_DOMAIN_SCHEMA_VERSION = "trader_now.v2"
DIGEST_ALGORITHM = "sha256"

_UUID7 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_DECIMAL_KEYS = frozenset(
    {
        "value",
        "tick_size",
        "volume",
        "volume_ratio",
        "atr",
        "atr_percentile_rank",
        "lateness_seconds",
        "confidence",
        "risk_dollars_per_contract",
        "approved_total_candidate_risk",
        "remaining_daily_risk_capacity",
        "remaining_drawdown_capacity",
    }
)
_ROOT_KEYS = frozenset(
    {
        "snapshot_schema_version",
        "evidence_profile",
        "canonicalization_profile",
        "snapshot_id",
        "idempotency_key",
        "supersedes_snapshot_id",
        "created_at",
        "source",
        "evidence",
        "integrity",
    }
)
_EVIDENCE_KEYS = (
    "evaluated_at",
    "input_snapshot_at",
    "identity",
    "trust",
    "availability",
    "market",
    "source_trust",
    "rules",
    "setups",
    "context",
    "interpretations",
    "strategy",
    "risk",
    "decision",
)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SnapshotProjectionError(f"{label} must be an object")
    return value


def _digest_preimage(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "canonicalization_profile": value["canonicalization_profile"],
        "evidence": value["evidence"],
        "evidence_profile": value["evidence_profile"],
        "snapshot_schema_version": value["snapshot_schema_version"],
        "source": value["source"],
    }


def _version_identities(value: Any, path: str = "") -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else key
            if (
                isinstance(item, str)
                and (key == "schema_version" or key.endswith("_version"))
            ):
                result.append((child, item))
            result.extend(_version_identities(item, child))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            result.extend(_version_identities(item, f"{path}[{index}]"))
    return result


def derive_idempotency_key(source_response: Any) -> str:
    """Derive the frozen tns1 idempotency identity from transport evidence."""
    source = _mapping(normalize(source_response), "TraderNow response")
    identity = _mapping(source.get("identity"), "identity")
    market = _mapping(source.get("market"), "market")
    series_value = market.get("market_data_series")
    series = {} if series_value is None else _mapping(series_value, "market_data_series")
    trust = _mapping(source.get("trust"), "trust")
    preimage = {
        "engine_definition_versions": sorted(_version_identities(source)),
        "evaluation_time": source.get("evaluated_at"),
        "evidence_profile": EVIDENCE_PROFILE,
        "freshness_policy_version": trust.get("policy_version"),
        "latest_closed_bar_time": market.get("latest_closed_at"),
        "market_data_provider": series.get("provider"),
        "market_data_resolution_version": series.get("resolution_version"),
        "market_data_series_symbol": series.get("symbol"),
        "market_data_series_type": series.get("series_type"),
        "product": identity.get("product"),
        "strategy_id": identity.get("strategy_id"),
        "strategy_version": identity.get("strategy_version"),
        "timeframe": identity.get("timeframe"),
    }
    return f"tns1:{hashlib.sha256(canonical_bytes(preimage)).hexdigest()}"


def project(
    source_response: Any,
    record_identity: SnapshotRecordIdentity,
) -> Mapping[str, Any]:
    """Project and seal one supported TraderNow transport response."""
    source = _mapping(normalize(source_response), "TraderNow response")
    if source.get("schema_version") != SOURCE_RESPONSE_SCHEMA_VERSION:
        raise SnapshotProjectionError("unsupported TraderNow response schema")
    if source.get("domain_schema_version") != SOURCE_DOMAIN_SCHEMA_VERSION:
        raise SnapshotProjectionError("unsupported TraderNow domain schema")
    missing = [key for key in _EVIDENCE_KEYS if key not in source]
    if missing:
        raise SnapshotProjectionError(
            f"TraderNow response is missing evidence fields: {missing}"
        )

    evidence = {key: source[key] for key in _EVIDENCE_KEYS}
    envelope: dict[str, Any] = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "evidence_profile": EVIDENCE_PROFILE,
        "canonicalization_profile": CANONICALIZATION_PROFILE,
        "snapshot_id": record_identity.snapshot_id,
        "idempotency_key": derive_idempotency_key(source),
        "supersedes_snapshot_id": record_identity.supersedes_snapshot_id,
        "created_at": record_identity.created_at,
        "source": {
            "trader_now_response_schema_version": SOURCE_RESPONSE_SCHEMA_VERSION,
            "trader_now_domain_schema_version": SOURCE_DOMAIN_SCHEMA_VERSION,
        },
        "evidence": evidence,
        "integrity": {
            "algorithm": DIGEST_ALGORITHM,
            "evidence_digest": None,
        },
    }
    normalized = normalize(envelope)
    normalized["integrity"]["evidence_digest"] = digest(normalized)
    validate(normalized)
    return freeze(normalized)


def validate(snapshot: Any) -> None:
    """Validate the closed v1 envelope and canonical value restrictions."""
    value = _mapping(snapshot, "snapshot")
    if set(value) != _ROOT_KEYS:
        raise SnapshotValidationError("snapshot envelope fields do not match v1")
    if value["snapshot_schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError("unsupported snapshot schema")
    if value["evidence_profile"] != EVIDENCE_PROFILE:
        raise SnapshotValidationError("unsupported evidence profile")
    if value["canonicalization_profile"] != CANONICALIZATION_PROFILE:
        raise SnapshotValidationError("unsupported canonicalization profile")
    if not isinstance(value["snapshot_id"], str) or not _UUID7.fullmatch(
        value["snapshot_id"]
    ):
        raise SnapshotValidationError("snapshot_id must be a lowercase UUIDv7")
    if not isinstance(value["idempotency_key"], str) or not (
        value["idempotency_key"].startswith("tns1:")
        and _SHA256.fullmatch(value["idempotency_key"][5:])
    ):
        raise SnapshotValidationError("invalid idempotency_key")
    supersedes = value["supersedes_snapshot_id"]
    if supersedes is not None and (
        not isinstance(supersedes, str)
        or not _UUID7.fullmatch(supersedes)
        or supersedes == value["snapshot_id"]
    ):
        raise SnapshotValidationError("invalid supersedes_snapshot_id")
    if not isinstance(value["created_at"], str) or not _TIMESTAMP.fullmatch(
        value["created_at"]
    ):
        raise SnapshotValidationError("created_at must be canonical UTC")

    source = _mapping(value["source"], "source")
    if source != {
        "trader_now_response_schema_version": SOURCE_RESPONSE_SCHEMA_VERSION,
        "trader_now_domain_schema_version": SOURCE_DOMAIN_SCHEMA_VERSION,
    }:
        raise SnapshotValidationError("unsupported source contract")
    evidence = _mapping(value["evidence"], "evidence")
    if set(evidence) != set(_EVIDENCE_KEYS):
        raise SnapshotValidationError("evidence fields do not match v1")

    integrity = _mapping(value["integrity"], "integrity")
    if set(integrity) != {"algorithm", "evidence_digest"}:
        raise SnapshotValidationError("integrity fields do not match v1")
    if integrity["algorithm"] != DIGEST_ALGORITHM:
        raise SnapshotValidationError("unsupported digest algorithm")
    declared = integrity["evidence_digest"]
    if declared is not None and (
        not isinstance(declared, str) or not _SHA256.fullmatch(declared)
    ):
        raise SnapshotValidationError("invalid evidence digest")

    _validate_canonical_tree(value)


def _validate_canonical_tree(value: Any, key: str | None = None) -> None:
    if value is None or isinstance(value, (str, bool)):
        if (
            isinstance(value, str)
            and key is not None
            and key.endswith("_at")
            and not _TIMESTAMP.fullmatch(value)
        ):
            raise SnapshotValidationError(f"{key} must be canonical UTC")
        if (
            isinstance(value, str)
            and key in _DECIMAL_KEYS
            and (not _DECIMAL.fullmatch(value) or value == "-0")
        ):
            raise SnapshotValidationError(f"{key} must be a canonical decimal string")
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if key in _DECIMAL_KEYS:
            raise SnapshotValidationError(f"{key} must be a canonical decimal string")
        if abs(value) > 9_007_199_254_740_991:
            raise SnapshotValidationError("integer exceeds the I-JSON safe range")
        return
    if isinstance(value, Mapping):
        if any(not isinstance(item, str) for item in value):
            raise SnapshotValidationError("mapping keys must be strings")
        for child_key, item in value.items():
            _validate_canonical_tree(item, child_key)
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _validate_canonical_tree(item)
        return
    if isinstance(value, (float, Decimal)):
        raise SnapshotValidationError("fractional values must be decimal strings")
    raise SnapshotValidationError(
        f"unsupported canonical value type: {type(value).__name__}"
    )


def serialize(snapshot: Any) -> bytes:
    """Return the sole canonical UTF-8 representation of a valid envelope."""
    validate(snapshot)
    return canonical_bytes(snapshot)


def digest(snapshot: Any) -> str:
    """Compute the evidence-only SHA-256 digest."""
    value = _mapping(snapshot, "snapshot")
    for key in (
        "canonicalization_profile",
        "evidence",
        "evidence_profile",
        "snapshot_schema_version",
        "source",
    ):
        if key not in value:
            raise SnapshotValidationError(f"snapshot is missing {key}")
    return hashlib.sha256(canonical_bytes(_digest_preimage(value))).hexdigest()


def verify(snapshot: Any) -> bool:
    """Validate and constant-time verify an envelope's evidence digest."""
    validate(snapshot)
    value = _mapping(snapshot, "snapshot")
    declared = _mapping(value["integrity"], "integrity")["evidence_digest"]
    if declared is None:
        raise SnapshotIntegrityError("snapshot is not sealed")
    if not hmac.compare_digest(declared, digest(value)):
        raise SnapshotIntegrityError("snapshot evidence digest mismatch")
    return True


def parse(payload: bytes | str) -> Mapping[str, Any]:
    """Parse canonical JSON, reject alternate encodings, and return immutability."""
    if isinstance(payload, bytes):
        if payload.startswith(b"\xef\xbb\xbf"):
            raise SnapshotValidationError("UTF-8 BOM is forbidden")
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise SnapshotValidationError("payload must be valid UTF-8") from error
    elif isinstance(payload, str):
        text = payload
    else:
        raise SnapshotValidationError("payload must be bytes or text")
    try:
        value = json.loads(
            text,
            parse_float=Decimal,
            parse_constant=lambda token: (_raise_non_finite(token)),
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        raise SnapshotValidationError("payload is not valid JSON") from error
    validate(value)
    if canonical_bytes(value) != text.encode("utf-8"):
        raise SnapshotValidationError("payload is not canonical atlas-jcs.v1 JSON")
    return freeze(value)


def _raise_non_finite(token: str) -> None:
    raise SnapshotValidationError(f"non-finite number is forbidden: {token}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotValidationError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def extract_metadata(snapshot: Any) -> SnapshotMetadata:
    """Derive non-authoritative index metadata from canonical evidence."""
    verify(snapshot)
    value = _mapping(snapshot, "snapshot")
    evidence = _mapping(value["evidence"], "evidence")
    identity = _mapping(evidence["identity"], "identity")
    market = _mapping(evidence["market"], "market")
    economic_value = market.get("economic_instrument")
    economic = (
        {} if economic_value is None else _mapping(economic_value, "economic_instrument")
    )
    series_value = market.get("market_data_series")
    series = (
        {} if series_value is None else _mapping(series_value, "market_data_series")
    )
    trust = _mapping(evidence["trust"], "trust")
    integrity = _mapping(value["integrity"], "integrity")
    evidence_digest = integrity["evidence_digest"]
    if not isinstance(evidence_digest, str):
        raise SnapshotIntegrityError("verified snapshot has no evidence digest")
    return SnapshotMetadata(
        snapshot_id=value["snapshot_id"],
        evidence_digest=evidence_digest,
        created_at=value["created_at"],
        evaluated_at=evidence["evaluated_at"],
        latest_closed_at=market.get("latest_closed_at"),
        economic_instrument=economic.get("symbol"),
        market_data_provider=series.get("provider"),
        market_data_series_symbol=series.get("symbol"),
        market_data_series_type=series.get("series_type"),
        timeframe=identity["timeframe"],
        strategy_id=identity["strategy_id"],
        strategy_version=identity["strategy_version"],
        trust_status=trust["status"],
        supersedes_snapshot_id=value["supersedes_snapshot_id"],
    )
