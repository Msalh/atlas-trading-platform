"""Typed deterministic failures for the AI Analysis Contract SDK."""


class AIAnalysisError(ValueError):
    """Base class for Phase 18B contract failures."""


class AIAnalysisValidationError(AIAnalysisError):
    """A value does not conform to a frozen AI analysis contract."""


class AIAnalysisCitationError(AIAnalysisValidationError):
    """A citation is malformed, unresolved, or outside approved evidence."""


class AIAnalysisAuthorityError(AIAnalysisValidationError):
    """AI output attempts prohibited authority, contradiction, or recomputation."""
