"""Phase 18C: evidence retrieval and orchestration, tested end-to-end with a
fake EvidenceTransport (no network) against the real frozen
trader_now_snapshot v1 golden fixtures. Every RefusalReason that is actually
reachable through this orchestrator is exercised, plus the two digest-trust
attacks DR-3 exists to prevent (evidence tamper, declared-digest lie) and the
evidence-layer failure modes (oversize, malformed JSON, BOM, duplicate keys,
non-canonical formatting, transport exception)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import atlas_snapshot
from atlas_ai_analysis import AnalysisInputIdentity, EligibleAnalysis, RefusedAnalysis
from atlas_snapshot import SnapshotRecordIdentity

from atlas_ai_service import AIServiceOrchestrator, EvidenceClient, ServiceFailure

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "specs" / "trader_now_snapshot" / "v1" / "golden"

IDENTITY = AnalysisInputIdentity(
    analysis_input_id="019849d1-8c00-7000-8000-0000000000aa",
    created_at="2026-07-25T12:00:01.000000Z",
)
PURPOSE = "strategy_explanation"


class FakeTransport:
    """Injected in place of a real Snapshot API client. Values in `responses`
    are returned verbatim for a matching snapshot_id; an Exception instance is
    raised instead, simulating a transport-level failure (e.g. not found)."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses

    def fetch_snapshot(self, snapshot_id: str) -> bytes:
        result = self._responses.get(
            snapshot_id, KeyError(f"no fixture registered for {snapshot_id}")
        )
        if isinstance(result, Exception):
            raise result
        return result


def _golden(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _transport_source(golden: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": golden["source"]["trader_now_response_schema_version"],
        "domain_schema_version": golden["source"]["trader_now_domain_schema_version"],
        "snapshot_id": None,
        **golden["evidence"],
    }


def _record_identity(golden: dict[str, Any]) -> SnapshotRecordIdentity:
    return SnapshotRecordIdentity(
        snapshot_id=golden["snapshot_id"],
        created_at=golden["created_at"],
        supersedes_snapshot_id=golden["supersedes_snapshot_id"],
    )


def _sealed_snapshot(fixture_name: str):
    golden = _golden(fixture_name)
    return atlas_snapshot.project(_transport_source(golden), _record_identity(golden))


def _sealed_bytes(fixture_name: str) -> bytes:
    return atlas_snapshot.serialize(_sealed_snapshot(fixture_name))


def _orchestrator(responses: dict[str, Any], **client_kwargs) -> AIServiceOrchestrator:
    return AIServiceOrchestrator(EvidenceClient(FakeTransport(responses), **client_kwargs))


def test_verified_current_snapshot_is_eligible():
    payload = _sealed_bytes("complete-current-candidate.canonical.json")
    outcome = _orchestrator({"snap-1": payload}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, EligibleAnalysis)
    assert outcome.freshness == "current"


def test_stale_snapshot_is_refused():
    payload = _sealed_bytes("stale-unavailable-no-signal-with-risk.canonical.json")
    outcome = _orchestrator({"snap-1": payload}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, RefusedAnalysis)
    assert outcome.reason == "snapshot_stale"


def test_unavailable_snapshot_is_refused():
    payload = _sealed_bytes("no-data.canonical.json")
    outcome = _orchestrator({"snap-1": payload}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, RefusedAnalysis)
    assert outcome.reason == "snapshot_unavailable"


def test_schema_unsupported_refusal_is_unreachable_here_by_construction():
    """atlas_snapshot.parse()/serialize() already enforce the identical frozen
    snapshot_schema_version/evidence_profile/canonicalization_profile fields
    that atlas_ai_analysis._supported_snapshot() checks, so a mismatched
    snapshot never survives EvidenceClient.fetch() to reach project_input()'s
    RefusedAnalysis(snapshot_schema_unsupported) path - it fails upstream in
    atlas_snapshot itself. This is a deliberate, documented consequence of
    composing the two frozen SDKs, verified structurally below rather than
    asserted through the orchestrator (there is nothing to feed it)."""
    plain = json.loads(_sealed_bytes("complete-current-candidate.canonical.json"))
    plain["evidence_profile"] = "unsupported.v99"

    with pytest.raises(atlas_snapshot.SnapshotValidationError):
        atlas_snapshot.serialize(plain)


def test_tampered_evidence_content_is_refused_with_recomputed_not_declared_digest():
    sealed = _sealed_snapshot("complete-current-candidate.canonical.json")
    plain = json.loads(atlas_snapshot.serialize(sealed))
    stale_declared_digest = plain["integrity"]["evidence_digest"]
    plain["evidence"]["identity"]["product"] = "NQ"
    tampered_bytes = atlas_snapshot.serialize(plain)
    true_digest_of_tampered_evidence = atlas_snapshot.digest(atlas_snapshot.parse(tampered_bytes))

    outcome = _orchestrator({"snap-1": tampered_bytes}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, RefusedAnalysis)
    assert outcome.reason == "snapshot_integrity_failed"
    assert outcome.evidence_digest == true_digest_of_tampered_evidence
    assert outcome.evidence_digest != stale_declared_digest


def test_declared_digest_lie_is_refused_with_the_true_recomputed_digest():
    sealed = _sealed_snapshot("complete-current-candidate.canonical.json")
    true_digest = atlas_snapshot.digest(sealed)
    plain = json.loads(atlas_snapshot.serialize(sealed))
    fake_digest = ("1" if true_digest[0] == "0" else "0") + true_digest[1:]
    plain["integrity"]["evidence_digest"] = fake_digest
    lying_bytes = atlas_snapshot.serialize(plain)

    outcome = _orchestrator({"snap-1": lying_bytes}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, RefusedAnalysis)
    assert outcome.reason == "snapshot_integrity_failed"
    assert outcome.evidence_digest == true_digest
    assert outcome.evidence_digest != fake_digest


def test_oversized_evidence_is_a_service_failure_before_parsing():
    payload = _sealed_bytes("complete-current-candidate.canonical.json")
    outcome = _orchestrator({"snap-1": payload}, max_bytes=10).evaluate(
        "snap-1", PURPOSE, IDENTITY
    )

    assert isinstance(outcome, ServiceFailure)
    assert outcome.reason == "internal_unavailable"
    assert outcome.requested_snapshot_id == "snap-1"


def test_malformed_json_is_a_service_failure():
    outcome = _orchestrator({"snap-1": b"{not json"}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, ServiceFailure)


def test_utf8_bom_is_a_service_failure():
    payload = _sealed_bytes("complete-current-candidate.canonical.json")
    outcome = _orchestrator({"snap-1": b"\xef\xbb\xbf" + payload}).evaluate(
        "snap-1", PURPOSE, IDENTITY
    )

    assert isinstance(outcome, ServiceFailure)


def test_duplicate_json_object_keys_is_a_service_failure():
    duplicate = b'{"snapshot_schema_version":"x","snapshot_schema_version":"y"}'
    outcome = _orchestrator({"snap-1": duplicate}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, ServiceFailure)


def test_noncanonical_formatting_is_a_service_failure():
    payload = _sealed_bytes("complete-current-candidate.canonical.json")
    reformatted = json.dumps(json.loads(payload), indent=2).encode("utf-8")
    outcome = _orchestrator({"snap-1": reformatted}).evaluate("snap-1", PURPOSE, IDENTITY)

    assert isinstance(outcome, ServiceFailure)


def test_transport_exception_is_a_service_failure():
    outcome = _orchestrator({"snap-1": ConnectionError("boom")}).evaluate(
        "missing-snapshot", PURPOSE, IDENTITY
    )

    assert isinstance(outcome, ServiceFailure)
    assert outcome.requested_snapshot_id == "missing-snapshot"
