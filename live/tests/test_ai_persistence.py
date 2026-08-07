"""Offline Phase 18F atomic persistence contract qualification."""

from __future__ import annotations

import copy
import json
import inspect
import pickle
import threading
from asyncio import CancelledError
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
import atlas_ai_orchestration as public_orchestration
from atlas_ai_analysis import (
    AnalysisInputIdentity,
    GeneratorIdentity,
    RefusedAnalysis,
    SnapshotVerification,
    parse_audit,
    project_input,
    serialize_audit,
)
from atlas_ai_orchestration import (
    CompletedOutcome,
    DeterministicPromptBuilder,
    FailedOutcome,
    ProviderOrchestrator,
    RefusedOutcome,
    ServiceUnavailableOutcome,
)
from atlas_ai_orchestration.models import (
    _completed_outcome,
    _failed_outcome,
)
from atlas_ai_analysis._json import freeze
from atlas_ai_persistence import (
    NotPersistableResult,
    PersistedResult,
    PersistenceConflictError,
    PersistenceCoordinator,
    PersistenceIntegrityError,
    PersistenceReceipt,
    PersistenceTimeoutError,
    PersistenceUnavailableError,
)
from atlas_ai_persistence.models import (
    AuditOnlyPersistenceRecord,
    CompletedPersistenceRecord,
)


ROOT = Path(__file__).parents[1]
AI_GOLDEN = ROOT / "specs" / "ai_analysis" / "v1" / "golden"
SNAPSHOT_GOLDEN = ROOT / "specs" / "trader_now_snapshot" / "v1" / "golden"
INPUT_ID = "019c1234-0000-7000-8000-000000000001"
OUTPUT_ID = "019c1234-0000-7000-8000-000000000002"
AUDIT_ID = "019c1234-0000-7000-8000-000000000003"
GENERATOR = GeneratorIdentity("synthetic-provider", "synthetic-model-v1")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _eligible():
    snapshot = _load(SNAPSHOT_GOLDEN / "complete-current-candidate.canonical.json")
    manifest = _load(SNAPSHOT_GOLDEN / "manifest.json")
    item = next(
        value
        for value in manifest["vectors"]
        if value["file"] == "complete-current-candidate.canonical.json"
    )
    snapshot["integrity"]["evidence_digest"] = item["sha256"]
    verification = SnapshotVerification(
        snapshot["snapshot_id"], item["sha256"], "verified"
    )
    result = project_input(
        snapshot,
        verification,
        AnalysisInputIdentity(INPUT_ID, "2026-07-26T12:00:01.000000Z"),
        "strategy_explanation",
        (
            "/evidence/source_trust/freshness/status",
            "/evidence/strategy/decisions/0/disposition",
            "/evidence/strategy/decisions/0/confidence",
            "/evidence/risk",
            "/evidence/decision/availability",
        ),
    )
    return result


class _Fixed:
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


class _Allowed:
    def allows(self, request) -> bool:
        return True


class _Provider:
    identity = GENERATOR

    def __init__(self, unavailable: bool = False) -> None:
        self.unavailable = unavailable

    def invoke(self, request):
        name = "output.unavailable.json" if self.unavailable else "output.complete-current.json"
        value = _load(AI_GOLDEN / name)
        value.update(
            analysis_output_id=request.analysis_output_id,
            analysis_input_id=request.analysis_input_id,
            snapshot_id=request.snapshot_id,
            evidence_digest=request.evidence_digest,
            purpose=request.purpose,
        )
        return value


def _core(*, unavailable: bool = False, audit_id: str = AUDIT_ID):
    return ProviderOrchestrator(
        prompt_builder=DeterministicPromptBuilder(_Fixed(OUTPUT_ID)),
        provider=_Provider(unavailable),
        cost_policy=_Allowed(),
        audit_id_factory=_Fixed(audit_id),
        clock=_Fixed("2026-07-26T12:00:02.000000Z"),
        generator=GENERATOR,
    )


def _completed(*, audit_id: str = AUDIT_ID) -> CompletedOutcome:
    outcome = _core(audit_id=audit_id).run(_eligible())
    assert isinstance(outcome, CompletedOutcome)
    return outcome


def _failed() -> FailedOutcome:
    outcome = _core(unavailable=True).run(_eligible())
    assert isinstance(outcome, FailedOutcome)
    return outcome


def _refused() -> RefusedOutcome:
    eligible = _eligible()
    outcome = _core().run(
        RefusedAnalysis(
            eligible.snapshot["snapshot_id"],
            eligible.snapshot["integrity"]["evidence_digest"],
            "strategy_explanation",
            "snapshot_stale",
        )
    )
    assert isinstance(outcome, RefusedOutcome)
    return outcome


def _plain(value: Any) -> Any:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


class TransactionalFake:
    """Test-only transactional state machine with isolated staged state."""

    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.calls = 0
        self._lock = threading.RLock()
        self._committed: dict[str, tuple[str | None, str]] = {}
        self._outputs: dict[str, tuple[str | None, str]] = {}
        self.staged_output: tuple[str, tuple[str | None, str]] | None = None
        self.staged_audit: tuple[str, tuple[str | None, str]] | None = None
        self.boundaries: list[str] = []
        self.commit_attempts = 0
        self.rollback_attempts = 0

    def store_atomic(self, record):
        with self._lock:
            self.calls += 1
            fingerprint = (
                getattr(record, "output_digest", None),
                record.audit_digest,
            )
            existing = self._committed.get(record.operation_id)
            if existing is not None:
                if existing != fingerprint:
                    raise PersistenceConflictError()
                return PersistenceReceipt(record.operation_id, "replayed")
            if isinstance(record, CompletedPersistenceRecord):
                existing_output = self._outputs.get(record.output_id)
                if existing_output is not None and existing_output != fingerprint:
                    raise PersistenceConflictError()
            self.boundaries.append("transaction_start")
            try:
                if self.mode == "before":
                    raise RuntimeError("hostile backend credential diagnostic")
                if isinstance(record, CompletedPersistenceRecord):
                    self.staged_output = (record.output_id, fingerprint)
                    self.boundaries.append("output_staged")
                    if self.mode.startswith("between_"):
                        raise RuntimeError("hostile between-write diagnostic")
                self.staged_audit = (record.operation_id, fingerprint)
                self.boundaries.append("audit_staged")
                self.boundaries.append("pre_commit")
                if self.mode == "timeout":
                    raise PersistenceTimeoutError()
                if self.mode == "cancel":
                    raise CancelledError("hostile cancellation diagnostic")
                self.commit_attempts += 1
                self.boundaries.append("commit_attempt")
                if self.mode.startswith("commit_"):
                    raise RuntimeError("hostile commit diagnostic")
                if self.staged_output is not None:
                    output_id, output_value = self.staged_output
                    self._outputs[output_id] = output_value
                audit_id, audit_value = self.staged_audit
                self._committed[audit_id] = audit_value
                self._clear_staged()
                self.boundaries.append("commit_success")
                return PersistenceReceipt(record.operation_id, "committed")
            except BaseException as original:
                self.rollback_attempts += 1
                self.boundaries.append("rollback_attempt")
                if self.mode.endswith("rollback_failure"):
                    self.boundaries.append("rollback_failure")
                    try:
                        raise RuntimeError(
                            "Bearer hostile rollback SQL backend credential"
                        )
                    except RuntimeError as rollback_error:
                        raise rollback_error from original
                self._clear_staged()
                self.boundaries.append("rollback_success")
                raise

    def _clear_staged(self) -> None:
        self.staged_output = None
        self.staged_audit = None

    @property
    def committed(self) -> dict[str, tuple[str | None, str]]:
        with self._lock:
            return dict(self._committed)

    @property
    def outputs(self) -> dict[str, tuple[str | None, str]]:
        with self._lock:
            return dict(self._outputs)


def test_completed_atomic_success_retains_exact_trusted_provenance() -> None:
    outcome = _completed()
    trusted = outcome._validated_output
    port = TransactionalFake()
    result = PersistenceCoordinator(port).persist(outcome)

    assert isinstance(result, PersistedResult)
    assert result.receipt.disposition == "committed"
    assert port.calls == 1
    assert outcome._validated_output is trusted
    with pytest.raises(FrozenInstanceError):
        result.receipt.disposition = "replayed"


@pytest.mark.parametrize("outcome_type,factory", [(FailedOutcome, _failed), (RefusedOutcome, _refused)])
def test_audit_only_outcomes_store_no_output(outcome_type, factory) -> None:
    outcome = factory()
    assert isinstance(outcome, outcome_type)
    port = TransactionalFake()
    PersistenceCoordinator(port).persist(outcome)
    assert port.calls == 1
    assert port.outputs == {}


def test_service_unavailable_is_ephemeral_and_never_calls_port() -> None:
    port = TransactionalFake()
    result = PersistenceCoordinator(port).persist(ServiceUnavailableOutcome())
    assert result == NotPersistableResult()
    assert port.calls == 0


def test_raw_completed_outcome_and_records_are_not_constructible() -> None:
    with pytest.raises(TypeError):
        CompletedOutcome(object(), GENERATOR, {}, object())
    with pytest.raises(TypeError):
        CompletedPersistenceRecord(
            validated_output=object(),
            audit={},
            output_bytes=b"",
            audit_bytes=b"",
            output_digest="x",
            audit_digest="x",
            operation_id="x",
            output_id="x",
            capability=object(),
        )
    with pytest.raises(TypeError):
        AuditOnlyPersistenceRecord(
            audit={},
            audit_bytes=b"",
            audit_digest="x",
            operation_id="x",
            outcome="failed",
            capability=object(),
        )


@pytest.mark.parametrize("factory", [_failed, _refused])
def test_publicly_reparsed_or_copied_audit_cannot_recreate_outcome_authority(
    factory,
) -> None:
    genuine = factory()
    copied = parse_audit(serialize_audit(genuine.audit))
    assert copied is not genuine.audit
    port = TransactionalFake()
    constructor = FailedOutcome if isinstance(genuine, FailedOutcome) else RefusedOutcome
    args = (genuine.reason, copied) if isinstance(genuine, FailedOutcome) else (copied,)
    with pytest.raises(TypeError):
        constructor(*args)
    assert port.calls == 0


@pytest.mark.parametrize(
    "audit_value",
    [
        {},
        MappingProxyType({}),
        type("DuckAudit", (), {"items": lambda self: ()})(),
    ],
)
@pytest.mark.parametrize("outcome_type", [FailedOutcome, RefusedOutcome])
def test_raw_mapping_proxy_and_duck_audits_cannot_create_trusted_outcome(
    audit_value, outcome_type
) -> None:
    port = TransactionalFake()
    args = ("internal_unavailable", audit_value) if outcome_type is FailedOutcome else (audit_value,)
    with pytest.raises(TypeError):
        outcome_type(*args)
    assert port.calls == 0


def test_structurally_similar_outcome_and_cross_execution_audit_are_rejected() -> None:
    class FailedSubclass(FailedOutcome):
        pass

    class SimilarFailed:
        reason = "internal_unavailable"
        audit = _failed().audit

    port = TransactionalFake()
    with pytest.raises(PersistenceIntegrityError):
        PersistenceCoordinator(port).persist(SimilarFailed())
    with pytest.raises(TypeError):
        FailedSubclass("internal_unavailable", _failed().audit)
    assert port.calls == 0

    failed = _failed()
    refused = _refused()
    with pytest.raises(TypeError):
        FailedOutcome(failed.reason, refused.audit)
    with pytest.raises(TypeError):
        RefusedOutcome(failed.audit)
    assert "analysis_audit_id" not in repr(failed)
    assert "analysis_audit_id" not in repr(refused)
    assert "capability" not in str(inspect.signature(FailedOutcome))
    assert "capability" not in str(inspect.signature(RefusedOutcome))
    assert "_failed_outcome" not in public_orchestration.__all__
    assert "_refused_outcome" not in public_orchestration.__all__
    assert b"capability" not in serialize_audit(failed.audit)
    assert copy.copy(failed) is failed
    assert copy.copy(refused) is refused
    with pytest.raises(TypeError):
        copy.deepcopy(failed)
    with pytest.raises(TypeError):
        copy.deepcopy(refused)
    with pytest.raises(TypeError):
        pickle.dumps(failed)
    with pytest.raises(TypeError):
        pickle.dumps(refused)


@pytest.mark.parametrize(
    "path,value",
    [
        (("analysis_input_id",), "019c1234-0000-7000-8000-000000000099"),
        (("analysis_output_id",), "019c1234-0000-7000-8000-000000000099"),
        (("snapshot_id",), "019c1234-0000-7000-8000-000000000099"),
        (("evidence_digest",), "a" * 64),
        (("purpose",), "market_snapshot_explanation"),
        (("contract_versions", "input"), "wrong.v1"),
        (("generator", "provider_id"), "other-provider"),
        (("generator", "model_id"), "other-model"),
        (("outcome",), "failed"),
    ],
)
def test_completed_identity_mismatch_fails_before_port(path, value) -> None:
    original = _completed()
    audit = _plain(original.audit)
    target = audit
    for item in path[:-1]:
        target = target[item]
    target[path[-1]] = value
    forged = _completed_outcome(
        original._validated_output, original._generator, freeze(audit)
    )
    port = TransactionalFake()
    with pytest.raises(PersistenceIntegrityError):
        PersistenceCoordinator(port).persist(forged)
    assert port.calls == 0


def test_failed_reason_mismatch_and_refused_outcome_mismatch_fail_before_port() -> None:
    failed = _failed()
    audit = _plain(failed.audit)
    audit["reason_code"] = "provider_unavailable"
    port = TransactionalFake()
    with pytest.raises(PersistenceIntegrityError):
        PersistenceCoordinator(port).persist(
            _failed_outcome(failed.reason, freeze(audit))
        )
    assert port.calls == 0


def test_exact_replay_is_idempotent_and_single_logical_record() -> None:
    outcome = _completed()
    port = TransactionalFake()
    coordinator = PersistenceCoordinator(port)
    first = coordinator.persist(outcome)
    second = coordinator.persist(outcome)
    assert first.receipt.disposition == "committed"
    assert second.receipt.disposition == "replayed"
    assert len(port.committed) == len(port.outputs) == 1


def test_audit_id_conflict_and_output_id_collision_fail_closed() -> None:
    first = _completed()
    port = TransactionalFake()
    coordinator = PersistenceCoordinator(port)
    coordinator.persist(first)

    audit = _plain(first.audit)
    audit["recorded_at"] = "2026-07-26T12:00:03.000000Z"
    conflict = _completed_outcome(
        first._validated_output, first._generator, freeze(audit)
    )
    with pytest.raises(PersistenceConflictError):
        coordinator.persist(conflict)

    second = _completed(audit_id="019c1234-0000-7000-8000-000000000099")
    with pytest.raises(PersistenceConflictError):
        coordinator.persist(second)
    assert len(port.committed) == len(port.outputs) == 1


def test_concurrent_identical_and_conflicting_submissions_are_atomic() -> None:
    outcome = _completed()
    port = TransactionalFake()
    coordinator = PersistenceCoordinator(port)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(coordinator.persist, [outcome] * 4))
    assert sorted(item.receipt.disposition for item in results) == [
        "committed",
        "replayed",
        "replayed",
        "replayed",
    ]
    assert len(port.committed) == len(port.outputs) == 1

    conflicting_audit = _plain(outcome.audit)
    conflicting_audit["recorded_at"] = "2026-07-26T12:00:03.000000Z"
    conflicting = _completed_outcome(
        outcome._validated_output, outcome._generator, freeze(conflicting_audit)
    )
    conflict_port = TransactionalFake()
    conflict_coordinator = PersistenceCoordinator(conflict_port)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(conflict_coordinator.persist, item)
            for item in (outcome, conflicting)
        ]
        successes = 0
        conflicts = 0
        for future in futures:
            try:
                assert isinstance(future.result(), PersistedResult)
                successes += 1
            except PersistenceConflictError:
                conflicts += 1
    assert (successes, conflicts) == (1, 1)
    assert len(conflict_port.committed) == len(conflict_port.outputs) == 1


@pytest.mark.parametrize(
    "mode,expected_boundaries,staged_after",
    [
        ("before", ("transaction_start", "rollback_attempt", "rollback_success"), False),
        (
            "between_rollback_success",
            ("output_staged", "rollback_attempt", "rollback_success"),
            False,
        ),
        (
            "between_rollback_failure",
            ("output_staged", "rollback_attempt", "rollback_failure"),
            True,
        ),
        (
            "commit_rollback_success",
            ("audit_staged", "commit_attempt", "rollback_success"),
            False,
        ),
        (
            "commit_rollback_failure",
            ("audit_staged", "commit_attempt", "rollback_failure"),
            True,
        ),
        ("cancel", ("pre_commit", "rollback_attempt", "rollback_success"), False),
    ],
)
def test_completed_transaction_failures_are_distinct_atomic_and_sanitized(
    mode, expected_boundaries, staged_after
) -> None:
    port = TransactionalFake(mode)
    with pytest.raises(PersistenceUnavailableError) as caught:
        PersistenceCoordinator(port).persist(_completed())
    assert port.calls == 1
    assert port.committed == port.outputs == {}
    assert all(boundary in port.boundaries for boundary in expected_boundaries)
    assert (port.staged_output is not None or port.staged_audit is not None) is staged_after
    assert port.rollback_attempts == 1
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "hostile" not in str(caught.value)
    assert "hostile" not in repr(caught.value)
    assert "Bearer" not in repr(caught.value)


def test_timeout_is_sanitized_and_no_retry_occurs() -> None:
    port = TransactionalFake("timeout")
    with pytest.raises(PersistenceTimeoutError) as caught:
        PersistenceCoordinator(port).persist(_completed())
    assert port.calls == 1
    assert port.committed == port.outputs == {}
    assert port.boundaries == [
        "transaction_start",
        "output_staged",
        "audit_staged",
        "pre_commit",
        "rollback_attempt",
        "rollback_success",
    ]
    assert port.staged_output is port.staged_audit is None
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "mode,rollback_failure",
    [
        ("before", False),
        ("commit_rollback_success", False),
        ("commit_rollback_failure", True),
    ],
)
def test_audit_only_transaction_boundaries_never_expose_partial_state(
    mode, rollback_failure
) -> None:
    port = TransactionalFake(mode)
    with pytest.raises(PersistenceUnavailableError):
        PersistenceCoordinator(port).persist(_failed())
    assert port.calls == 1
    assert port.outputs == port.committed == {}
    if mode != "before":
        assert "audit_staged" in port.boundaries
        assert "output_staged" not in port.boundaries
        assert port.commit_attempts == 1
    assert (port.staged_audit is not None) is rollback_failure
    assert port.staged_output is None


def test_success_boundaries_publish_completed_pair_or_audit_only_together() -> None:
    completed_port = TransactionalFake()
    PersistenceCoordinator(completed_port).persist(_completed())
    assert len(completed_port.outputs) == len(completed_port.committed) == 1
    assert completed_port.staged_output is completed_port.staged_audit is None
    assert completed_port.boundaries[-1] == "commit_success"

    audit_port = TransactionalFake()
    PersistenceCoordinator(audit_port).persist(_failed())
    assert audit_port.outputs == {}
    assert len(audit_port.committed) == 1
    assert audit_port.staged_output is audit_port.staged_audit is None
    assert audit_port.boundaries[-1] == "commit_success"


def test_invalid_receipt_is_not_reported_as_success() -> None:
    class BadReceiptPort:
        calls = 0

        def store_atomic(self, record):
            self.calls += 1
            return PersistenceReceipt("019c1234-0000-7000-8000-000000000099", "committed")

    port = BadReceiptPort()
    with pytest.raises(PersistenceIntegrityError):
        PersistenceCoordinator(port).persist(_completed())
    assert port.calls == 1


@pytest.mark.parametrize(
    "untrusted",
    [
        {},
        {"prompt": "credential-like-value"},
        {"provider_payload": {"raw": True}},
        ["malformed-candidate"],
        "raw-evidence",
    ],
)
def test_untrusted_raw_values_are_rejected_before_port(untrusted) -> None:
    port = TransactionalFake()
    with pytest.raises(PersistenceIntegrityError):
        PersistenceCoordinator(port).persist(untrusted)
    assert port.calls == 0
