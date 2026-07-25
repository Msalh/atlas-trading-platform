"""Immutable public value types for the standalone Snapshot SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SnapshotRecordIdentity:
    """Record metadata supplied by a future external capture component."""

    snapshot_id: str
    created_at: datetime | str
    supersedes_snapshot_id: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotMetadata:
    """Non-authoritative index values derived from canonical evidence."""

    snapshot_id: str
    evidence_digest: str
    created_at: str
    evaluated_at: str | None
    latest_closed_at: str | None
    economic_instrument: str | None
    market_data_provider: str | None
    market_data_series_symbol: str | None
    market_data_series_type: str | None
    timeframe: str
    strategy_id: str
    strategy_version: str
    trust_status: str
    supersedes_snapshot_id: str | None
