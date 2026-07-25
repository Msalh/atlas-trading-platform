"""Append-only persistence boundary for canonical Atlas snapshots."""

from .errors import (
    SnapshotConflictError,
    SnapshotCorruptionError,
    SnapshotIdempotencyConflictError,
    SnapshotNotFoundError,
    SnapshotStoreError,
    UnsupportedStoredSnapshotError,
)
from .models import AppendResult, SnapshotListCursor, SnapshotPage
from .ports import SnapshotRepository
from .postgres import PostgresSnapshotRepository

__all__ = [
    "AppendResult",
    "PostgresSnapshotRepository",
    "SnapshotConflictError",
    "SnapshotCorruptionError",
    "SnapshotIdempotencyConflictError",
    "SnapshotListCursor",
    "SnapshotNotFoundError",
    "SnapshotPage",
    "SnapshotRepository",
    "SnapshotStoreError",
    "UnsupportedStoredSnapshotError",
]
