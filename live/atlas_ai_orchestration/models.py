"""Immutable public values for the Phase 18D orchestration core."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from atlas_ai_analysis.models import (
    FailureReason,
    GeneratorIdentity,
    JSONScalar as JSONScalar,
    JSONValue as JSONValue,
    ValidatedAnalysisOutput,
)


_COMPLETED_OUTCOME_CAPABILITY = object()


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


@dataclass(frozen=True, slots=True, init=False)
class CompletedOutcome:
    _validated_output: ValidatedAnalysisOutput = field(repr=False)
    _generator: GeneratorIdentity = field(repr=False)
    audit: Mapping[str, Any]

    def __init__(
        self,
        validated_output: ValidatedAnalysisOutput,
        generator: GeneratorIdentity,
        audit: Mapping[str, Any],
        capability: object,
    ) -> None:
        if capability is not _COMPLETED_OUTCOME_CAPABILITY:
            raise TypeError("completed outcome construction is private")
        if type(validated_output) is not ValidatedAnalysisOutput:
            raise TypeError("trusted validated output is required")
        object.__setattr__(self, "_validated_output", validated_output)
        object.__setattr__(self, "_generator", generator)
        object.__setattr__(self, "audit", audit)

    @property
    def output(self) -> Mapping[str, Any]:
        """Compatibility view of the immutable Phase 18B-validated output."""

        return self._validated_output.value


def _completed_outcome(
    validated_output: ValidatedAnalysisOutput,
    generator: GeneratorIdentity,
    audit: Mapping[str, Any],
) -> CompletedOutcome:
    return CompletedOutcome(
        validated_output, generator, audit, _COMPLETED_OUTCOME_CAPABILITY
    )


@dataclass(frozen=True, slots=True, init=False)
class FailedOutcome:
    reason: FailureReason
    _trusted_audit: Mapping[str, Any] = field(repr=False)

    def __init__(
        self,
        *args: object,
        **kwargs: object,
    ) -> None:
        raise TypeError("failed outcome construction is private")

    @property
    def audit(self) -> Mapping[str, Any]:
        return self._trusted_audit

    def __copy__(self) -> FailedOutcome:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> FailedOutcome:
        raise TypeError("failed outcome copying is private")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("failed outcome serialization is private")


@dataclass(frozen=True, slots=True, init=False)
class RefusedOutcome:
    _trusted_audit: Mapping[str, Any] = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("refused outcome construction is private")

    @property
    def audit(self) -> Mapping[str, Any]:
        return self._trusted_audit

    def __copy__(self) -> RefusedOutcome:
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> RefusedOutcome:
        raise TypeError("refused outcome copying is private")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("refused outcome serialization is private")


def _failed_outcome(reason: FailureReason, audit: Mapping[str, Any]) -> FailedOutcome:
    outcome = object.__new__(FailedOutcome)
    object.__setattr__(outcome, "reason", reason)
    object.__setattr__(outcome, "_trusted_audit", audit)
    return outcome


def _refused_outcome(audit: Mapping[str, Any]) -> RefusedOutcome:
    outcome = object.__new__(RefusedOutcome)
    object.__setattr__(outcome, "_trusted_audit", audit)
    return outcome


@dataclass(frozen=True, slots=True)
class ServiceUnavailableOutcome:
    reason: Literal["internal_unavailable"] = "internal_unavailable"
    detail: Literal["analysis_unavailable"] = "analysis_unavailable"


type OrchestrationOutcome = (
    CompletedOutcome | FailedOutcome | RefusedOutcome | ServiceUnavailableOutcome
)
