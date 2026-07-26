"""Phase 17D explicit capture orchestration and failure-isolation tests."""

from __future__ import annotations

import ast
import asyncio
import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

import atlas_snapshot_capture.service as service_module
from atlas_snapshot import extract_metadata, parse, serialize, verify
from atlas_snapshot_capture import (
    CaptureDisposition,
    CaptureFailure,
    CaptureFailureCode,
    CaptureRequest,
    CaptureServiceConfig,
    SnapshotCaptureService,
    TraderNowClientFailure,
    generate_uuid7,
)
from atlas_snapshot_store import (
    AppendResult,
    SnapshotIdempotencyConflictError,
    SnapshotNotFoundError,
    SnapshotPage,
    SnapshotStoreError,
)

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "specs" / "trader_now_snapshot" / "v1" / "golden"
NOW = datetime(2026, 7, 25, 14, 0, tzinfo=timezone.utc)


def _response(name="complete-current-candidate.canonical.json"):
    golden = json.loads((GOLDEN / name).read_text(encoding="utf-8"))
    return {
        "schema_version": golden["source"]["trader_now_response_schema_version"],
        "domain_schema_version": golden["source"][
            "trader_now_domain_schema_version"
        ],
        "snapshot_id": None,
        **golden["evidence"],
    }


def _config(*, enabled=True, key="operator-secret"):
    return CaptureServiceConfig(
        trader_now_base_url="https://trader-now.internal",
        trader_now_api_key=key,
        enabled=enabled,
    )


class FakeClient:
    def __init__(self, response=None, failure=None):
        self.response = response or _response()
        self.failure = failure
        self.started = False
        self.closed = False
        self.calls = []

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def fetch_latest(self, request, *, correlation_id):
        self.calls.append((request, correlation_id))
        if self.failure:
            failure = self.failure
            self.failure = None
            raise failure
        return copy.deepcopy(self.response)


class FakeRepository:
    def __init__(self):
        self.by_id = {}
        self.by_digest = {}
        self.by_idempotency = {}
        self.payloads = {}
        self.append_failure = None
        self.get_failure = None
        self.retrieve_override = None
        self.list_failure = None

    async def append(self, canonical_payload):
        if self.append_failure:
            raise self.append_failure
        snapshot = parse(canonical_payload)
        metadata = extract_metadata(snapshot)
        key = snapshot["idempotency_key"]
        existing_id = self.by_idempotency.get(key)
        if existing_id:
            if self.payloads[existing_id] == canonical_payload:
                return AppendResult(extract_metadata(self.by_id[existing_id]), False)
            raise SnapshotIdempotencyConflictError("conflict")
        self.by_id[metadata.snapshot_id] = snapshot
        self.by_digest[metadata.evidence_digest] = snapshot
        self.by_idempotency[key] = metadata.snapshot_id
        self.payloads[metadata.snapshot_id] = canonical_payload
        return AppendResult(metadata, True)

    async def get_by_snapshot_id(self, snapshot_id):
        if self.get_failure:
            raise self.get_failure
        if self.retrieve_override is not None:
            return self.retrieve_override
        if snapshot_id not in self.by_id:
            raise SnapshotNotFoundError("missing")
        return self.by_id[snapshot_id]

    async def get_by_evidence_digest(self, evidence_digest):
        if self.get_failure:
            raise self.get_failure
        if evidence_digest not in self.by_digest:
            raise SnapshotNotFoundError("missing")
        return self.by_digest[evidence_digest]

    async def list_metadata(self, *, limit, cursor=None):
        if self.list_failure:
            raise self.list_failure
        return SnapshotPage((), None)


async def _service(
    *,
    response=None,
    enabled=True,
    client=None,
    repository=None,
    uuid7="019849f0-0000-7000-8000-000000000001",
):
    client = client or FakeClient(response)
    repository = repository or FakeRepository()
    service = SnapshotCaptureService(
        config=_config(enabled=enabled),
        client=client,
        repository=repository,
        clock=lambda: NOW,
        uuid7_factory=lambda: uuid7,
    )
    await service.start()
    return service, client, repository


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture",
    [
        "complete-current-candidate.canonical.json",
        "no-data.canonical.json",
        "delayed-insufficient-rejected.canonical.json",
        "stale-unavailable-no-signal-with-risk.canonical.json",
    ],
)
async def test_successful_capture_preserves_all_approved_snapshot_states(fixture):
    service, client, repository = await _service(response=_response(fixture))

    result = await service.capture(
        CaptureRequest("MNQ", "5m", "displacement_volume_context", "corr-1")
    )

    assert result.disposition is CaptureDisposition.CREATED
    assert result.correlation_id == "corr-1"
    assert verify(repository.by_id[result.snapshot_id])
    assert serialize(repository.by_id[result.snapshot_id]) == (
        repository.payloads[result.snapshot_id]
    )
    assert client.calls[0][0].symbol == "MNQ"
    await service.close()


@pytest.mark.asyncio
async def test_approved_identity_and_absent_listed_instrument_are_preserved():
    service, _, repository = await _service()
    result = await service.capture(
        CaptureRequest("MNQ", "5m", "displacement_volume_context")
    )
    snapshot = repository.by_id[result.snapshot_id]

    assert snapshot["evidence"]["identity"]["product"] == "MNQ"
    assert snapshot["evidence"]["market"]["market_data_series"]["symbol"] == "MNQ1!"
    assert snapshot["evidence"]["market"]["listed_instrument"] is None
    assert snapshot["evidence"]["risk"] is None


@pytest.mark.asyncio
async def test_matching_retry_returns_existing_snapshot_without_second_insert():
    service, _, repository = await _service()
    request = CaptureRequest("MNQ", "5m", "displacement_volume_context")
    first = await service.capture(request)
    second = await service.capture(request)

    assert first.disposition is CaptureDisposition.CREATED
    assert second.disposition is CaptureDisposition.DUPLICATE
    assert second.snapshot_id == first.snapshot_id
    assert len(repository.by_id) == 1


@pytest.mark.asyncio
async def test_new_evaluation_time_is_a_new_capture_not_a_retry():
    response = _response()
    client = FakeClient(response)
    identifiers = iter(
        (
            "019849f0-0000-7000-8000-000000000001",
            "019849f0-0000-7000-8000-000000000002",
        )
    )
    repository = FakeRepository()
    service = SnapshotCaptureService(
        config=_config(),
        client=client,
        repository=repository,
        clock=lambda: NOW,
        uuid7_factory=lambda: next(identifiers),
    )
    await service.start()
    request = CaptureRequest("MNQ", "5m", "displacement_volume_context")

    first = await service.capture(request)
    client.response["evaluated_at"] = "2026-07-25T14:00:01.000000Z"
    second = await service.capture(request)

    assert first.disposition is CaptureDisposition.CREATED
    assert second.disposition is CaptureDisposition.CREATED
    assert second.idempotency_key != first.idempotency_key
    assert second.snapshot_id != first.snapshot_id
    assert len(repository.by_id) == 2


@pytest.mark.asyncio
async def test_concurrent_matching_frozen_evidence_converges_to_one_snapshot():
    service, _, repository = await _service()
    request = CaptureRequest("MNQ", "5m", "displacement_volume_context")

    results = await asyncio.gather(
        service.capture(request),
        service.capture(request),
        service.capture(request),
    )

    assert sum(
        result.disposition is CaptureDisposition.CREATED for result in results
    ) == 1
    assert sum(
        result.disposition is CaptureDisposition.DUPLICATE for result in results
    ) == 2
    assert {result.snapshot_id for result in results} == {
        "019849f0-0000-7000-8000-000000000001"
    }
    assert len(repository.by_id) == 1


@pytest.mark.asyncio
async def test_conflicting_idempotency_is_rejected_without_partial_insert():
    repository = FakeRepository()
    service, client, _ = await _service(repository=repository)
    await service.capture(CaptureRequest("MNQ", "5m", "displacement_volume_context"))
    changed = _response()
    changed["rules"]["facts"][0]["value"] = False
    client.response = changed

    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )

    assert failure.value.code is CaptureFailureCode.IDEMPOTENCY_CONFLICT
    assert len(repository.by_id) == 1


@pytest.mark.asyncio
async def test_store_transaction_failure_leaves_no_partial_snapshot():
    repository = FakeRepository()
    repository.append_failure = SnapshotStoreError("database DSN secret")
    service, _, _ = await _service(repository=repository)

    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )

    assert failure.value.code is CaptureFailureCode.STORE_TRANSACTION
    assert repository.by_id == {}


@pytest.mark.asyncio
async def test_store_unavailable_before_insert_leaves_no_partial_snapshot():
    repository = FakeRepository()
    repository.get_failure = SnapshotStoreError("private infrastructure detail")
    service, _, _ = await _service(repository=repository)

    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )

    assert failure.value.code is CaptureFailureCode.STORE_UNAVAILABLE
    assert repository.by_id == {}


@pytest.mark.asyncio
async def test_integrity_failure_after_retrieval_is_fail_closed():
    repository = FakeRepository()
    service, _, _ = await _service(repository=repository)
    original_append = repository.append

    async def append_then_corrupt(payload):
        result = await original_append(payload)
        value = json.loads(payload)
        value["evidence"]["identity"]["product"] = "NQ"
        repository.retrieve_override = value
        return result

    repository.append = append_then_corrupt
    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert failure.value.code is CaptureFailureCode.INTEGRITY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "trader_now_response.v99"),
        ("domain_schema_version", "trader_now.v99"),
    ],
)
async def test_unsupported_source_versions_are_rejected(field, value):
    response = _response()
    response[field] = value
    service, _, repository = await _service(response=response)

    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert failure.value.code is CaptureFailureCode.UNSUPPORTED_SOURCE_SCHEMA
    assert repository.by_id == {}


@pytest.mark.asyncio
async def test_malformed_response_is_rejected_before_projection():
    response = _response()
    del response["strategy"]
    service, _, repository = await _service(response=response)

    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert failure.value.code is CaptureFailureCode.TRADER_NOW_RESPONSE
    assert repository.by_id == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capture_request",
    [
        CaptureRequest("", "5m", "displacement_volume_context"),
        CaptureRequest("NQ", "5m", "displacement_volume_context"),
        CaptureRequest("MNQ", "1m", "displacement_volume_context"),
        CaptureRequest("MNQ", "5m", "other"),
    ],
)
async def test_invalid_operator_or_identity_request_is_rejected(capture_request):
    service, client, _ = await _service()
    with pytest.raises(CaptureFailure) as failure:
        await service.capture(capture_request)
    assert failure.value.code in {
        CaptureFailureCode.INVALID_REQUEST,
        CaptureFailureCode.INVALID_IDENTITY,
    }
    assert client.calls == []


@pytest.mark.asyncio
async def test_response_series_identity_must_be_approved():
    response = _response()
    response["market"]["market_data_series"]["symbol"] = "MNQ2!"
    service, _, _ = await _service(response=response)
    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert failure.value.code is CaptureFailureCode.INVALID_IDENTITY


@pytest.mark.asyncio
async def test_service_is_disabled_by_default_and_requires_explicit_enablement():
    config = CaptureServiceConfig(
        trader_now_base_url="https://trader-now.internal",
        trader_now_api_key="secret",
    )
    client = FakeClient()
    service = SnapshotCaptureService(
        config=config,
        client=client,
        repository=FakeRepository(),
        clock=lambda: NOW,
    )
    await service.start()

    assert (await service.readiness()).code == "service_disabled"
    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert failure.value.code is CaptureFailureCode.SERVICE_DISABLED


@pytest.mark.asyncio
async def test_health_is_process_only_and_readiness_checks_required_dependencies():
    repository = FakeRepository()
    service, _, _ = await _service(repository=repository)

    assert service.health().status == "healthy"
    assert (await service.readiness()).ready is True

    repository.list_failure = SnapshotStoreError("unavailable")
    readiness = await service.readiness()
    assert readiness.ready is False
    assert readiness.code == "snapshot_store_unavailable"
    assert service.health().status == "healthy"


@pytest.mark.asyncio
async def test_clean_startup_and_shutdown_have_no_capture_side_effect():
    service, client, repository = await _service()
    assert client.started is True
    assert repository.by_id == {}

    await service.close()

    assert client.closed is True
    assert (await service.readiness()).code == "not_started"
    assert repository.by_id == {}


@pytest.mark.asyncio
async def test_retry_after_timeout_has_no_partial_first_attempt():
    client = FakeClient(
        failure=TraderNowClientFailure(CaptureFailureCode.TRADER_NOW_TIMEOUT)
    )
    service, _, repository = await _service(client=client)
    request = CaptureRequest("MNQ", "5m", "displacement_volume_context")

    with pytest.raises(CaptureFailure) as failure:
        await service.capture(request)
    assert failure.value.code is CaptureFailureCode.TRADER_NOW_TIMEOUT
    assert repository.by_id == {}

    result = await service.capture(request)
    assert result.disposition is CaptureDisposition.CREATED
    assert len(repository.by_id) == 1


def test_uuid7_record_identity_is_rfc_compliant_and_deterministic_with_injection():
    value = generate_uuid7(now=lambda: NOW, randbits=lambda bits: 0)
    parsed = UUID(value)

    assert parsed.version == 7
    assert parsed.variant == "specified in RFC 4122"
    assert value == "019f9993-5f00-7000-8000-000000000000"


@pytest.mark.asyncio
async def test_sdk_projection_validation_and_serialization_failures_are_typed(
    monkeypatch,
):
    service, _, repository = await _service()

    monkeypatch.setattr(
        service_module,
        "project",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            service_module.SnapshotProjectionError("bad")
        ),
    )
    with pytest.raises(CaptureFailure) as projection:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert projection.value.code is CaptureFailureCode.SDK_PROJECTION
    assert repository.by_id == {}

    monkeypatch.setattr(service_module, "project", lambda *_args, **_kwargs: {})
    with pytest.raises(CaptureFailure) as validation:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert validation.value.code is CaptureFailureCode.SDK_VALIDATION
    assert repository.by_id == {}

    monkeypatch.undo()
    monkeypatch.setattr(
        service_module,
        "serialize",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            service_module.SnapshotValidationError("bad")
        ),
    )
    with pytest.raises(CaptureFailure) as serialization:
        await service.capture(
            CaptureRequest("MNQ", "5m", "displacement_volume_context")
        )
    assert serialization.value.code is CaptureFailureCode.SDK_SERIALIZATION
    assert repository.by_id == {}


@pytest.mark.asyncio
async def test_sanitized_failures_and_logs_never_expose_secrets(caplog):
    secret = "never-log-this-api-key"
    config = _config(key=secret)
    client = FakeClient(
        failure=TraderNowClientFailure(CaptureFailureCode.TRADER_NOW_NETWORK)
    )
    service = SnapshotCaptureService(
        config=config,
        client=client,
        repository=FakeRepository(),
        clock=lambda: NOW,
    )
    await service.start()
    caplog.set_level(logging.INFO, logger="atlas.snapshot_capture")

    with pytest.raises(CaptureFailure) as failure:
        await service.capture(
            CaptureRequest(
                "MNQ",
                "5m",
                "displacement_volume_context",
                "safe-correlation",
            )
        )

    rendered = caplog.text + repr(config) + str(failure.value)
    assert secret not in rendered
    assert "trader-now.internal" not in caplog.text
    assert caplog.records[-1].correlation_id == "safe-correlation"
    assert failure.value.code is CaptureFailureCode.TRADER_NOW_NETWORK


def test_architecture_has_no_scheduler_ai_database_or_trader_now_runtime_dependency():
    package = ROOT / "atlas_snapshot_capture"
    forbidden_import_roots = {
        "atlas",
        "psycopg",
        "asyncpg",
        "anthropic",
        "openai",
        "apscheduler",
    }
    forbidden_tokens = {
        "backgroundtasks",
        "create_task(",
        "schedule(",
        "cron",
        "database_url",
        "postgresql",
        "trader_now_application",
        "trader_now.models",
    }

    for path in package.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        assert imports.isdisjoint(forbidden_import_roots), path.name
        lowered = source.lower()
        assert not any(token in lowered for token in forbidden_tokens), path.name


def test_dependency_direction_points_only_to_frozen_sdk_and_store():
    imports = set()
    for path in (ROOT / "atlas_snapshot_capture").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("atlas_")
            ):
                imports.add(node.module.split(".", 1)[0])
    assert imports == {"atlas_snapshot", "atlas_snapshot_store"}
