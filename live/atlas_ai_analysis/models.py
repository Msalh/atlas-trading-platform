"""Immutable public value types for the pure AI Analysis Contract SDK."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

RefusalReason = Literal[
    "snapshot_stale",
    "snapshot_unavailable",
    "snapshot_integrity_failed",
    "snapshot_schema_unsupported",
]
FailureReason = Literal[
    "provider_timeout",
    "provider_unavailable",
    "invalid_output",
    "missing_citation",
    "deterministic_state_contradiction",
    "prohibited_content",
    "cost_limit",
    "internal_unavailable",
]


@dataclass(frozen=True, slots=True)
class SnapshotVerification:
    """Trusted verifier attestation; this SDK never computes Snapshot digests."""

    snapshot_id: str
    evidence_digest: str
    status: Literal["verified", "corrupted"]


@dataclass(frozen=True, slots=True)
class AnalysisInputIdentity:
    analysis_input_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class AnalysisAuditIdentity:
    analysis_audit_id: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class GeneratorIdentity:
    """Non-secret generator identifiers, never provider configuration."""

    provider_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class EligibleAnalysis:
    """An invocation-safe input derived from one externally verified Snapshot."""

    snapshot: Mapping[str, Any]
    analysis_input: Mapping[str, Any]
    freshness: Literal["current", "delayed"]


@dataclass(frozen=True, slots=True)
class RefusedAnalysis:
    """Fail-closed result; deliberately contains no analysis input or output."""

    snapshot_id: str
    evidence_digest: str
    purpose: str
    reason: RefusalReason
