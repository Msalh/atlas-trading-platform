"""Phase 18C: pure, offline evidence retrieval and orchestration for the
frozen AI Analysis Contract v1. No network, provider, or database access -
evidence is fetched exclusively through an injected EvidenceTransport port,
and digest verification is always derived from atlas_snapshot.digest()/
verify(), never from a snapshot's own declared integrity field."""

from .errors import AIServiceError, EvidenceFetchError, EvidenceOversizeError
from .evidence_client import DEFAULT_MAX_EVIDENCE_BYTES, EvidenceClient
from .models import EvaluationOutcome, FetchedEvidence, ServiceFailure, ServiceFailureReason
from .orchestrator import AIServiceOrchestrator
from .ports import EvidenceTransport

__all__ = [
    "DEFAULT_MAX_EVIDENCE_BYTES",
    "AIServiceError",
    "AIServiceOrchestrator",
    "EvaluationOutcome",
    "EvidenceClient",
    "EvidenceFetchError",
    "EvidenceOversizeError",
    "EvidenceTransport",
    "FetchedEvidence",
    "ServiceFailure",
    "ServiceFailureReason",
]
