"""Immutable value types owned by Phase 18C. These are new, not part of the
frozen Phase 18A/18B contracts - `EligibleAnalysis` and `RefusedAnalysis`
still come from `atlas_ai_analysis` and flow through this package unchanged."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Union

from atlas_ai_analysis import EligibleAnalysis, RefusedAnalysis

ServiceFailureReason = Literal["internal_unavailable"]


@dataclass(frozen=True, slots=True)
class FetchedEvidence:
    """Result of a successful fetch-and-parse. `recomputed_digest` is always
    derived independently via atlas_snapshot.digest() - never read from the
    snapshot's own declared `integrity.evidence_digest` field. `verified` is
    False when atlas_snapshot.verify() rejected the snapshot (tampered
    evidence or an unsealed digest); the snapshot itself may still be a
    well-formed Mapping in that case."""

    snapshot: Mapping
    recomputed_digest: str
    verified: bool


@dataclass(frozen=True, slots=True)
class ServiceFailure:
    """An outcome that occurs before an EligibleAnalysis can exist (evidence
    could not be fetched, or the bytes did not even parse as a snapshot). The
    frozen Phase 18A audit contract has no representable code for this - its
    own `failed_audit()` builder requires an already-eligible analysis -
    so this is a Phase 18C-local type. Persisting it as a new audit record
    (e.g. `ai_analysis_service_error.v1`) is out of Phase 18C's scope."""

    requested_snapshot_id: str
    reason: ServiceFailureReason
    detail: str


EvaluationOutcome = Union[EligibleAnalysis, RefusedAnalysis, ServiceFailure]
