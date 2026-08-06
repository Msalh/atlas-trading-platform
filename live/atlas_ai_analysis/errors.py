"""Typed deterministic failures for the AI Analysis Contract SDK."""

from enum import Enum


class OutputRejectionClassification(str, Enum):
    """Closed, content-free reason for rejecting decoded Phase 18B output."""

    INVALID_CITATION_REFERENCE = "invalid_citation_reference"
    SEMANTIC_CONTRADICTION = "semantic_contradiction"
    DETERMINISTIC_FIELD_MISMATCH = "deterministic_field_mismatch"
    NUMERIC_INVENTION = "numeric_invention"
    PROHIBITED_AUTHORITY_CONTENT = "prohibited_authority_content"
    OTHER_SEMANTIC_REJECTION = "other_semantic_rejection"


class AIAnalysisError(ValueError):
    """Base class for Phase 18B contract failures."""


class AIAnalysisValidationError(AIAnalysisError):
    """A value does not conform to a frozen AI analysis contract."""

    __slots__ = ("_output_rejection",)

    def __init__(
        self,
        *args: object,
        output_rejection: OutputRejectionClassification = (
            OutputRejectionClassification.OTHER_SEMANTIC_REJECTION
        ),
    ) -> None:
        super().__init__(*args)
        self._output_rejection = (
            output_rejection
            if type(output_rejection) is OutputRejectionClassification
            else OutputRejectionClassification.OTHER_SEMANTIC_REJECTION
        )

    @property
    def output_rejection(self) -> OutputRejectionClassification:
        return self._output_rejection


class AIAnalysisCitationError(AIAnalysisValidationError):
    """A citation is malformed, unresolved, or outside approved evidence."""

    def __init__(self, *args: object) -> None:
        super().__init__(
            *args,
            output_rejection=OutputRejectionClassification.INVALID_CITATION_REFERENCE,
        )


class AIAnalysisAuthorityError(AIAnalysisValidationError):
    """AI output attempts prohibited authority, contradiction, or recomputation."""
