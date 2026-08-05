"""Sanitized failures for the offline Phase 18F persistence boundary."""

from __future__ import annotations


class PersistenceError(RuntimeError):
    """Base class whose instances never retain adapter diagnostics."""

    classification = "persistence_error"

    def __init__(self) -> None:
        super().__init__(self.classification)


class PersistenceUnavailableError(PersistenceError):
    classification = "persistence_unavailable"


class PersistenceTimeoutError(PersistenceError):
    classification = "persistence_timeout"


class PersistenceConflictError(PersistenceError):
    classification = "persistence_conflict"


class PersistenceIntegrityError(PersistenceError):
    classification = "persistence_integrity"
