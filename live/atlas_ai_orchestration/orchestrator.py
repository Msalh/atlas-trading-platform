"""Pure Phase 18D provider orchestration with deterministic fail-closed routing."""

from __future__ import annotations

from atlas_ai_analysis import (
    AnalysisAuditIdentity,
    EligibleAnalysis,
    GeneratorIdentity,
    RefusedAnalysis,
    completed_audit_from_validated_output,
    failed_audit,
    refused_audit,
    validate_output,
)
from atlas_ai_analysis.models import FailureReason
from atlas_ai_service import ServiceFailure

from .errors import ProviderTimeoutError, ProviderUnavailableError
from .models import (
    CompletedOutcome,
    FailedOutcome,
    OrchestrationOutcome,
    RefusedOutcome,
    ServiceUnavailableOutcome,
    TrustedProviderRequest,
)
from .ports import (
    CostPolicy,
    IdentityFactory,
    ProviderPort,
    TrustedPromptBuilder,
    UTCClock,
)


class ProviderOrchestrator:
    def __init__(
        self,
        *,
        prompt_builder: TrustedPromptBuilder,
        provider: ProviderPort,
        cost_policy: CostPolicy,
        audit_id_factory: IdentityFactory,
        clock: UTCClock,
        generator: GeneratorIdentity,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._provider = provider
        self._cost_policy = cost_policy
        self._audit_id_factory = audit_id_factory
        self._clock = clock
        self._generator = generator

    def run(
        self,
        evaluation: EligibleAnalysis | RefusedAnalysis | ServiceFailure,
    ) -> OrchestrationOutcome:
        if isinstance(evaluation, ServiceFailure):
            return ServiceUnavailableOutcome()
        if isinstance(evaluation, RefusedAnalysis):
            return self._refused(evaluation)
        if not isinstance(evaluation, EligibleAnalysis):
            return ServiceUnavailableOutcome()
        return self._eligible(evaluation)

    def _audit_identity(self) -> AnalysisAuditIdentity:
        return AnalysisAuditIdentity(self._audit_id_factory(), self._clock())

    def _refused(self, refusal: RefusedAnalysis) -> OrchestrationOutcome:
        try:
            return RefusedOutcome(audit=refused_audit(refusal, self._audit_identity()))
        except Exception:
            return ServiceUnavailableOutcome()

    def _failure(
        self,
        eligible: EligibleAnalysis,
        reason: FailureReason,
    ) -> OrchestrationOutcome:
        try:
            audit = failed_audit(
                eligible,
                self._audit_identity(),
                reason,
                self._generator,
            )
        except Exception:
            return ServiceUnavailableOutcome()
        return FailedOutcome(reason=reason, audit=audit)

    def _eligible(self, eligible: EligibleAnalysis) -> OrchestrationOutcome:
        try:
            provider_identity = self._provider.identity
        except Exception:
            return self._failure(eligible, "internal_unavailable")
        if (
            type(provider_identity) is not GeneratorIdentity
            or provider_identity != self._generator
        ):
            return self._failure(eligible, "internal_unavailable")
        try:
            request = self._prompt_builder.build(eligible.analysis_input)
            if not isinstance(request, TrustedProviderRequest):
                return self._failure(eligible, "internal_unavailable")
            allowed = self._cost_policy.allows(request)
        except Exception:
            return self._failure(eligible, "internal_unavailable")
        if type(allowed) is not bool:
            return self._failure(eligible, "internal_unavailable")
        if not allowed:
            return self._failure(eligible, "cost_limit")

        try:
            candidate = self._provider.invoke(request)
        except ProviderTimeoutError:
            return self._failure(eligible, "provider_timeout")
        except ProviderUnavailableError:
            return self._failure(eligible, "provider_unavailable")
        except Exception:
            return self._failure(eligible, "internal_unavailable")

        try:
            validated = validate_output(candidate, eligible)
        except Exception:
            return self._failure(eligible, "invalid_output")

        if validated.status == "available":
            try:
                audit = completed_audit_from_validated_output(
                    eligible,
                    validated,
                    self._audit_identity(),
                    self._generator,
                )
            except Exception:
                return self._failure(eligible, "internal_unavailable")
            return CompletedOutcome(output=validated.value, audit=audit)

        try:
            reason = validated.unavailable_reason
            if reason is None:
                return self._failure(eligible, "internal_unavailable")
        except Exception:
            return self._failure(eligible, "internal_unavailable")
        return self._failure(eligible, reason)
