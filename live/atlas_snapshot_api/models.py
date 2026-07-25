"""Versioned transport models for the private Snapshot API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

API_SCHEMA_VERSION: Literal["snapshot_private_api.v1"] = "snapshot_private_api.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaptureBody(StrictModel):
    symbol: Literal["MNQ"]
    timeframe: Literal["5m"]
    strategy_id: Literal["displacement_volume_context"]


class MetadataResponse(StrictModel):
    schema_version: Literal["snapshot_private_api.v1"] = API_SCHEMA_VERSION
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


class CaptureResponse(StrictModel):
    schema_version: Literal["snapshot_private_api.v1"] = API_SCHEMA_VERSION
    disposition: Literal["created", "duplicate"]
    snapshot_id: str
    evidence_digest: str
    idempotency_key: str
    correlation_id: str
    metadata: MetadataResponse


class SnapshotResponse(StrictModel):
    schema_version: Literal["snapshot_private_api.v1"] = API_SCHEMA_VERSION
    snapshot: dict[str, Any]


class IntegrityResponse(StrictModel):
    schema_version: Literal["snapshot_private_api.v1"] = API_SCHEMA_VERSION
    snapshot_id: str
    evidence_digest: str
    valid: Literal[True] = True


class SnapshotListResponse(StrictModel):
    schema_version: Literal["snapshot_private_api.v1"] = API_SCHEMA_VERSION
    items: tuple[MetadataResponse, ...]
    next_cursor: str | None


class StatusResponse(StrictModel):
    ok: bool
    service: Literal["atlas-snapshot-private-api"] = "atlas-snapshot-private-api"
    code: str | None = None


class ErrorResponse(StrictModel):
    schema_version: Literal["snapshot_private_api.v1"] = API_SCHEMA_VERSION
    code: str
    message: str
    correlation_id: str
