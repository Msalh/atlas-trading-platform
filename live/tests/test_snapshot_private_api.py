"""Phase 17E private API contract and security tests."""

from __future__ import annotations

import ast
import copy
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from atlas_snapshot import SnapshotMetadata, digest, parse, serialize
from atlas_snapshot_api import (
    FixedWindowRateLimiter,
    SnapshotAuthConfig,
    create_snapshot_app,
)
from atlas_snapshot_capture import (
    CaptureDisposition,
    CaptureFailure,
    CaptureFailureCode,
    CaptureResult,
    HealthStatus,
    ReadinessStatus,
)
from atlas_snapshot_store import SnapshotNotFoundError, SnapshotPage
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]
GOLDEN = (
    ROOT
    / "specs"
    / "trader_now_snapshot"
    / "v1"
    / "golden"
    / "complete-current-candidate.canonical.json"
)
SNAPSHOT = copy.deepcopy(json.loads(GOLDEN.read_text(encoding="utf-8")))
SNAPSHOT["integrity"]["evidence_digest"] = digest(SNAPSHOT)
METADATA = SnapshotMetadata(
    snapshot_id=SNAPSHOT["snapshot_id"],
    evidence_digest=SNAPSHOT["integrity"]["evidence_digest"],
    created_at=SNAPSHOT["created_at"],
    evaluated_at=SNAPSHOT["evidence"]["evaluated_at"],
    latest_closed_at=SNAPSHOT["evidence"]["market"]["latest_closed_at"],
    economic_instrument="MNQ",
    market_data_provider="tradingview",
    market_data_series_symbol="MNQ1!",
    market_data_series_type="continuous",
    timeframe="5m",
    strategy_id="displacement_volume_context",
    strategy_version="displacement_volume_context.v1",
    trust_status="trusted",
    supersedes_snapshot_id=None,
)
READER = {"Authorization": "Bearer reader-secret"}
OPERATOR = {"Authorization": "Bearer operator-secret"}
BODY = {
    "symbol": "MNQ",
    "timeframe": "5m",
    "strategy_id": "displacement_volume_context",
}


class FakeCaptureService:
    def __init__(self) -> None:
        self.calls = []
        self.disposition = CaptureDisposition.CREATED
        self.failure: CaptureFailure | None = None
        self.ready = True
        self.started = 0
        self.closed = 0

    async def start(self):
        self.started += 1

    async def close(self):
        self.closed += 1

    def health(self):
        return HealthStatus()

    async def readiness(self):
        return ReadinessStatus(self.ready, "ready" if self.ready else "disabled")

    async def capture(self, request):
        self.calls.append(request)
        if self.failure:
            raise self.failure
        return CaptureResult(
            disposition=self.disposition,
            snapshot_id=METADATA.snapshot_id,
            evidence_digest=METADATA.evidence_digest,
            idempotency_key=SNAPSHOT["idempotency_key"],
            correlation_id=request.correlation_id,
            metadata=METADATA,
        )


class FakeRepository:
    def __init__(self) -> None:
        self.snapshot = parse(serialize(SNAPSHOT))
        self.page = SnapshotPage(items=(METADATA,), next_cursor=None)
        self.list_calls = []

    async def append(self, canonical_payload):
        raise AssertionError("reader repository must never append")

    async def get_by_snapshot_id(self, snapshot_id):
        if snapshot_id != METADATA.snapshot_id:
            raise SnapshotNotFoundError("not found")
        return self.snapshot

    async def get_by_evidence_digest(self, evidence_digest):
        raise AssertionError("API retrieval must use snapshot identity")

    async def list_metadata(self, *, limit, cursor=None):
        self.list_calls.append((limit, cursor))
        return self.page


@dataclass
class Harness:
    capture: FakeCaptureService
    repository: FakeRepository
    client: TestClient


@pytest.fixture
def harness():
    capture = FakeCaptureService()
    repository = FakeRepository()
    app = create_snapshot_app(
        capture_service=capture,
        reader_repository=repository,
        auth=SnapshotAuthConfig(
            reader_token="reader-secret",
            operator_token="operator-secret",
        ),
    )
    with TestClient(app) as client:
        yield Harness(capture, repository, client)


def test_health_is_process_only_and_lifecycle_is_clean(harness):
    response = harness.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "atlas-snapshot-private-api",
        "code": None,
    }
    assert harness.capture.started == 1
    assert harness.capture.closed == 0


def test_all_snapshot_routes_require_authentication(harness):
    paths = [
        ("post", "/api/v1/snapshots/capture"),
        ("get", f"/api/v1/snapshots/{METADATA.snapshot_id}"),
        ("get", f"/api/v1/snapshots/{METADATA.snapshot_id}/metadata"),
        ("get", f"/api/v1/snapshots/{METADATA.snapshot_id}/integrity"),
        ("get", "/api/v1/snapshots"),
        ("get", "/readiness"),
    ]
    for method, path in paths:
        response = harness.client.request(
            method.upper(), path, json=BODY if method == "post" else None
        )
        assert response.status_code == 401


def test_reader_cannot_capture(harness):
    response = harness.client.post(
        "/api/v1/snapshots/capture", headers=READER, json=BODY
    )
    assert response.status_code == 403
    assert harness.capture.calls == []


def test_operator_capture_forwards_correlation_and_returns_created(harness):
    response = harness.client.post(
        "/api/v1/snapshots/capture",
        headers={**OPERATOR, "X-Correlation-ID": "operator-123"},
        json=BODY,
    )
    assert response.status_code == 201
    assert response.headers["X-Correlation-ID"] == "operator-123"
    assert response.json()["schema_version"] == "snapshot_private_api.v1"
    assert response.json()["disposition"] == "created"
    assert harness.capture.calls[0].correlation_id == "operator-123"


def test_matching_duplicate_returns_existing_snapshot_with_200(harness):
    harness.capture.disposition = CaptureDisposition.DUPLICATE
    response = harness.client.post(
        "/api/v1/snapshots/capture", headers=OPERATOR, json=BODY
    )
    assert response.status_code == 200
    assert response.json()["disposition"] == "duplicate"


def test_capture_request_is_exact_and_extra_fields_are_rejected(harness):
    invalid = {**BODY, "symbol": "MNQZ99"}
    assert (
        harness.client.post(
            "/api/v1/snapshots/capture", headers=OPERATOR, json=invalid
        ).status_code
        == 422
    )
    assert (
        harness.client.post(
            "/api/v1/snapshots/capture",
            headers=OPERATOR,
            json={**BODY, "unexpected": True},
        ).status_code
        == 422
    )


def test_capture_failure_is_sanitized(harness):
    harness.capture.failure = CaptureFailure(CaptureFailureCode.STORE_TRANSACTION)
    response = harness.client.post(
        "/api/v1/snapshots/capture", headers=OPERATOR, json=BODY
    )
    assert response.status_code == 502
    assert response.json()["code"] == "snapshot_store_transaction_failed"
    assert "postgres" not in response.text.lower()


def test_snapshot_metadata_integrity_and_listing(harness):
    snapshot = harness.client.get(
        f"/api/v1/snapshots/{METADATA.snapshot_id}", headers=READER
    )
    metadata = harness.client.get(
        f"/api/v1/snapshots/{METADATA.snapshot_id}/metadata", headers=READER
    )
    integrity = harness.client.get(
        f"/api/v1/snapshots/{METADATA.snapshot_id}/integrity", headers=READER
    )
    listing = harness.client.get("/api/v1/snapshots?limit=1", headers=READER)
    assert snapshot.json()["snapshot"] == SNAPSHOT
    assert metadata.json()["evidence_digest"] == METADATA.evidence_digest
    assert integrity.json()["valid"] is True
    assert listing.json()["items"][0]["snapshot_id"] == METADATA.snapshot_id
    assert harness.repository.list_calls[-1] == (1, None)


def test_unknown_snapshot_is_404_with_correlation_id(harness):
    response = harness.client.get(
        "/api/v1/snapshots/00000000-0000-7000-8000-000000000099",
        headers=READER,
    )
    assert response.status_code == 404
    assert response.json()["correlation_id"] == response.headers["X-Correlation-ID"]


def test_listing_is_bounded_and_cursor_is_validated(harness):
    assert (
        harness.client.get("/api/v1/snapshots?limit=101", headers=READER).status_code
        == 422
    )
    assert (
        harness.client.get(
            "/api/v1/snapshots?cursor=not-valid", headers=READER
        ).status_code
        == 400
    )


def test_readiness_checks_capture_and_reader_dependencies(harness):
    assert harness.client.get("/readiness", headers=READER).status_code == 200
    harness.capture.ready = False
    response = harness.client.get("/readiness", headers=READER)
    assert response.status_code == 503
    assert response.json()["code"] == "disabled"


def test_rate_limit_is_enforced():
    capture = FakeCaptureService()
    repository = FakeRepository()
    app = create_snapshot_app(
        capture_service=capture,
        reader_repository=repository,
        auth=SnapshotAuthConfig("reader-secret", "operator-secret"),
        limiter=FixedWindowRateLimiter(clock=lambda: 1.0),
    )
    with TestClient(app) as client:
        for _ in range(10):
            assert (
                client.post(
                    "/api/v1/snapshots/capture", headers=OPERATOR, json=BODY
                ).status_code
                == 201
            )
        assert (
            client.post(
                "/api/v1/snapshots/capture", headers=OPERATOR, json=BODY
            ).status_code
            == 429
        )


def test_auth_configuration_requires_distinct_tokens():
    with pytest.raises(ValueError):
        SnapshotAuthConfig("same", "same").validate()


def test_phase_17e_dependency_boundary_and_no_automation():
    package = ROOT / "atlas_snapshot_api"
    imports: set[str] = set()
    infrastructure_imports: dict[str, set[str]] = {}
    text = ""
    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        text += source.lower()
        tree = ast.parse(source)
        file_imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                file_imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                file_imports.add(node.module)
        imports.update(file_imports)
        infrastructure_imports[path.name] = file_imports
    assert not any(name.startswith("atlas.trader_now") for name in imports)
    assert "asyncpg" not in imports
    assert "anthropic" not in imports
    assert "openai" not in imports
    assert not any(
        any(name.startswith("psycopg") for name in names)
        for filename, names in infrastructure_imports.items()
        if filename not in {"conninfo.py", "runtime.py"}
    )
    assert "scheduler" not in text
    assert "backgroundtasks" not in text
    assert "create_task(" not in text
