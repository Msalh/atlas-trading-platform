"""Immutable public values for the Phase 18D orchestration core."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from atlas_ai_analysis.models import (
    FailureReason,
    JSONScalar as JSONScalar,
    JSONValue as JSONValue,
)


@dataclass(frozen=True, slots=True)
class TrustedProviderRequest:
    """Trusted instructions plus explicitly delimited untrusted evidence.

    This value is passed only to the injected provider port and is never part of
    a public orchestration outcome.
    """

    schema_version: Literal["trusted_provider_request.v1"]
    output_schema_version: Literal["ai_analysis_output.v1"]
    analysis_output_id: str
    analysis_input_id: str
    snapshot_id: str
    evidence_digest: str
    purpose: str
    trusted_instructions: tuple[str, ...]
    untrusted_evidence_json: str


@dataclass(frozen=True, slots=True)
class CompletedOutcome:
    output: Mapping[str, Any]
    audit: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FailedOutcome:
    reason: FailureReason
    audit: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RefusedOutcome:
    audit: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ServiceUnavailableOutcome:
    reason: Literal["internal_unavailable"] = "internal_unavailable"
    detail: Literal["analysis_unavailable"] = "analysis_unavailable"


type OrchestrationOutcome = (
    CompletedOutcome | FailedOutcome | RefusedOutcome | ServiceUnavailableOutcome
)
