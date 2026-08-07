"""Reviewed typed failures at the Phase 18D provider port boundary."""

from .diagnostics import ProviderFailureClassification


class ProviderPortError(Exception):
    """Base class for provider failures the core may classify."""

    __slots__ = ("_classification",)

    def __init__(
        self,
        classification: ProviderFailureClassification = ProviderFailureClassification.UNKNOWN,
    ) -> None:
        super().__init__()
        self._classification = (
            classification
            if type(classification) is ProviderFailureClassification
            else ProviderFailureClassification.UNKNOWN
        )

    @property
    def classification(self) -> ProviderFailureClassification:
        return self._classification


class ProviderTimeoutError(ProviderPortError):
    """A concrete adapter enforced its timeout before returning output."""

    def __init__(self, *_discarded: object) -> None:
        super().__init__(ProviderFailureClassification.TIMEOUT)


class ProviderUnavailableError(ProviderPortError):
    """A concrete adapter reports the provider as unavailable."""
