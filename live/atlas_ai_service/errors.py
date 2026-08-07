"""Typed failures for the Phase 18C evidence-retrieval and orchestration layer."""

from __future__ import annotations


class AIServiceError(ValueError):
    """Base class for atlas_ai_service failures."""


class EvidenceFetchError(AIServiceError):
    """Evidence could not be retrieved or was not a well-formed, parseable
    snapshot. Distinct from a snapshot that parses but fails digest
    verification - that is a representable Phase 18A refusal
    (snapshot_integrity_failed), not a service failure."""


class EvidenceOversizeError(EvidenceFetchError):
    """Fetched evidence bytes exceeded the configured size cap."""
