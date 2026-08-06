"""Pure Phase 18D provider orchestration with deterministic fail-closed routing."""

from __future__ import annotations

from atlas_ai_analysis import (
    AIAnalysisValidationError,
    AnalysisAuditIdentity,
    EligibleAnalysis,
    GeneratorIdentity,
    RefusedAnalysis,
    completed_audit_from_validated_output,
    failed_audit,
    refused_audit,
    validate_output,
)
from atlas_ai_analysis.errors import (
    OutputRejectionClassification,
    SemanticContradictionSubreason,
)
from atlas_ai_analysis.models import FailureReason
from atlas_ai_service import ServiceFailure

from .diagnostics import ProviderFailureClassification, ProviderFailureDiagnostics
from .errors import ProviderPortError, ProviderTimeoutError, ProviderUnavailableError
from .models import (
    OrchestrationOutcome,
    ServiceUnavailableOutcome,
    TrustedProviderRequest,
    _completed_outcome,
    _failed_outcome,
    _refused_outcome,
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
        failure_diagnostics: ProviderFailureDiagnostics | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._provider = provider
        self._cost_policy = cost_policy
        self._audit_id_factory = audit_id_factory
        self._clock = clock
        self._generator = generator
        self._failure_diagnostics = failure_diagnostics

    def _record_provider_failure(
        self, classification: ProviderFailureClassification
    ) -> None:
        if self._failure_diagnostics is None:
            return
        try:
            self._failure_diagnostics.record(classification)
        except Exception:
            try:
                self._failure_diagnostics.record(
                    ProviderFailureClassification.UNKNOWN
                )
            except Exception:
                pass

    def _record_phase18b_failure(
        self,
        classification: OutputRejectionClassification,
        subreason: SemanticContradictionSubreason | None = None,
    ) -> None:
        if self._failure_diagnostics is None:
            return
        try:
            self._failure_diagnostics.record_phase18b(classification, subreason)
        except Exception:
            try:
                self._failure_diagnostics.record_phase18b(
                    OutputRejectionClassification.OTHER_SEMANTIC_REJECTION,
                )
            except Exception:
                pass

    @staticmethod
    def _safe_classification(error: ProviderPortError) -> ProviderFailureClassification:
        try:
            classification = error.classification
        except Exception:
            return ProviderFailureClassification.UNKNOWN
        return (
            classification
            if type(classification) is ProviderFailureClassification
            else ProviderFailureClassification.UNKNOWN
        )

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
            return _refused_outcome(refused_audit(refusal, self._audit_identity()))
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
        return _failed_outcome(reason, audit)

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
        except ProviderTimeoutError as error:
            self._record_provider_failure(self._safe_classification(error))
            return self._failure(eligible, "provider_timeout")
        except ProviderUnavailableError as error:
            self._record_provider_failure(self._safe_classification(error))
            return self._failure(eligible, "provider_unavailable")
        except ProviderPortError as error:
            self._record_provider_failure(self._safe_classification(error))
            return self._failure(eligible, "internal_unavailable")
        except Exception:
            self._record_provider_failure(ProviderFailureClassification.UNKNOWN)
            return self._failure(eligible, "internal_unavailable")

        try:
            validated = validate_output(candidate, eligible)
        except AIAnalysisValidationError as error:
            self._record_provider_failure(
                ProviderFailureClassification.PHASE18B_INVALID_OUTPUT
            )
            try:
                classification = error.output_rejection
            except Exception:
                classification = OutputRejectionClassification.OTHER_SEMANTIC_REJECTION
            try:
                subreason = error.semantic_contradiction_subreason
            except Exception:
                subreason = SemanticContradictionSubreason.CLASSIFICATION_AMBIGUOUS
            self._record_phase18b_failure(classification, subreason)
            return self._failure(eligible, "invalid_output")
        except Exception:
            self._record_provider_failure(
                ProviderFailureClassification.PHASE18B_INVALID_OUTPUT
            )
            self._record_phase18b_failure(
                OutputRejectionClassification.OTHER_SEMANTIC_REJECTION
            )
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
                self._record_provider_failure(ProviderFailureClassification.UNKNOWN)
                return self._failure(eligible, "internal_unavailable")
            return _completed_outcome(validated, self._generator, audit)

        try:
            reason = validated.unavailable_reason
            if reason is None:
                self._record_provider_failure(
                    ProviderFailureClassification.PHASE18B_INVALID_OUTPUT
                )
                return self._failure(eligible, "internal_unavailable")
        except Exception:
            self._record_provider_failure(
                ProviderFailureClassification.PHASE18B_INVALID_OUTPUT
            )
            return self._failure(eligible, "internal_unavailable")
        self._record_provider_failure(
            ProviderFailureClassification.PHASE18B_INVALID_OUTPUT
        )
        return self._failure(eligible, reason)
