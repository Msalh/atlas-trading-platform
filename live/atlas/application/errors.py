"""Typed errors for HTTP-independent application composition."""


class TraderNowApplicationError(Exception):
    """Base error for invalid TraderNow application composition."""


class InvalidCompositionTimeError(TraderNowApplicationError):
    """Raised when an explicit or injected composition time is not aware."""
