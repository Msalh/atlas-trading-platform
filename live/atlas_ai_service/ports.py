"""Injectable transport boundary. atlas_ai_service never performs I/O itself -
a concrete adapter (HTTP client against the Snapshot API, etc.) is wired in by
a caller at a later Phase 18 subphase; this package only defines the shape it
depends on, so it stays testable with a fake and importable without network,
database, or provider dependencies."""

from __future__ import annotations

from typing import Protocol


class EvidenceTransport(Protocol):
    def fetch_snapshot(self, snapshot_id: str) -> bytes | str:
        """Return the raw canonical-JSON bytes (or str) of a previously
        captured snapshot, or raise on failure. Implementations own their own
        network/timeout/retry behavior; this package treats any exception
        raised here as an evidence-fetch failure."""
        ...
