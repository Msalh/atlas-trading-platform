"""Typed persistence-boundary failures for the snapshot store."""


class SnapshotStoreError(RuntimeError):
    """Base class for snapshot persistence failures."""


class SnapshotConflictError(SnapshotStoreError):
    """A unique snapshot identity conflicts with different canonical bytes."""


class SnapshotIdempotencyConflictError(SnapshotConflictError):
    """The same idempotency key was presented with different canonical bytes."""


class SnapshotCorruptionError(SnapshotStoreError):
    """Stored canonical bytes, digest, or derived metadata disagree."""


class SnapshotNotFoundError(SnapshotStoreError):
    """No snapshot exists for the requested identity."""


class UnsupportedStoredSnapshotError(SnapshotCorruptionError):
    """A stored row declares a snapshot contract this repository cannot read."""
