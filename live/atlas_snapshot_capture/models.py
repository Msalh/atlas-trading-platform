"""Immutable capture-service request, result, and status values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from atlas_snapshot import SnapshotMetadata


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    symbol: str
    timeframe: str
    strategy_id: str
    correlation_id: str | None = None


class CaptureDisposition(str, Enum):
    CREATED = "created"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class CaptureResult:
    disposition: CaptureDisposition
    snapshot_id: str
    evidence_digest: str
    idempotency_key: str
    correlation_id: str
    metadata: SnapshotMetadata


@dataclass(frozen=True, slots=True)
class HealthStatus:
    status: str = "healthy"


@dataclass(frozen=True, slots=True)
class ReadinessStatus:
    ready: bool
    code: str
