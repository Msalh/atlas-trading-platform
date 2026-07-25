"""Immutable repository values; canonical evidence remains SDK-owned."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from atlas_snapshot import SnapshotMetadata


@dataclass(frozen=True, slots=True)
class AppendResult:
    metadata: SnapshotMetadata
    created: bool


@dataclass(frozen=True, slots=True)
class SnapshotListCursor:
    created_at: datetime
    snapshot_id: str


@dataclass(frozen=True, slots=True)
class SnapshotPage:
    items: tuple[SnapshotMetadata, ...]
    next_cursor: SnapshotListCursor | None
