"""Storage-neutral repository interface for immutable snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .models import AppendResult, SnapshotListCursor, SnapshotPage


class SnapshotRepository(Protocol):
    async def append(self, canonical_payload: bytes) -> AppendResult: ...

    async def get_by_snapshot_id(self, snapshot_id: str) -> Mapping[str, Any]: ...

    async def get_by_evidence_digest(
        self, evidence_digest: str
    ) -> Mapping[str, Any]: ...

    async def list_metadata(
        self,
        *,
        limit: int,
        cursor: SnapshotListCursor | None = None,
    ) -> SnapshotPage: ...
