"""Reviewed typed failures at the Phase 18D provider port boundary."""


class ProviderPortError(Exception):
    """Base class for provider failures the core may classify."""


class ProviderTimeoutError(ProviderPortError):
    """A concrete adapter enforced its timeout before returning output."""


class ProviderUnavailableError(ProviderPortError):
    """A concrete adapter reports the provider as unavailable."""
