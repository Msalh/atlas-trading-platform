"""Typed failures raised by the standalone Snapshot SDK."""


class SnapshotError(ValueError):
    """Base class for deterministic snapshot contract failures."""


class SnapshotProjectionError(SnapshotError):
    """The source transport value cannot be projected."""


class SnapshotValidationError(SnapshotError):
    """A snapshot does not conform to the frozen v1 contract."""


class SnapshotIntegrityError(SnapshotError):
    """Canonical bytes or their declared digest fail integrity verification."""
