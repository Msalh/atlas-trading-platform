"""Wires bounded evidence retrieval into the frozen Phase 18A/18B contract.
Owns the state machine down to ELIGIBLE / REFUSED / (local) ServiceFailure.
Everything past eligibility - prompt assembly, provider calls, persistence -
is a later Phase 18 subphase and out of scope here."""

from __future__ import annotations

from collections.abc import Sequence

from atlas_ai_analysis import AnalysisInputIdentity, SnapshotVerification, project_input

from .errors import EvidenceFetchError
from .evidence_client import EvidenceClient
from .models import EvaluationOutcome, ServiceFailure


class AIServiceOrchestrator:
    def __init__(self, evidence_client: EvidenceClient) -> None:
        self._evidence_client = evidence_client

    def evaluate(
        self,
        snapshot_id: str,
        purpose: str,
        identity: AnalysisInputIdentity,
        *,
        evidence_paths: Sequence[str] | None = None,
    ) -> EvaluationOutcome:
        try:
            fetched = self._evidence_client.fetch(snapshot_id)
        except EvidenceFetchError:
            return ServiceFailure(
                requested_snapshot_id=snapshot_id,
                reason="internal_unavailable",
                detail="evidence_unavailable",
            )

        verification = SnapshotVerification(
            snapshot_id=fetched.snapshot.get("snapshot_id"),
            evidence_digest=fetched.recomputed_digest,
            status="verified" if fetched.verified else "corrupted",
        )
        return project_input(
            fetched.snapshot,
            verification,
            identity,
            purpose,
            evidence_paths=evidence_paths,
        )
