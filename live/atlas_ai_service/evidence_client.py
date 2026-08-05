"""Bounded evidence retrieval: fetches raw snapshot bytes through an injected
transport port, enforces a byte-size cap before any parsing is attempted, and
never trusts a payload's own declared digest. The digest returned here is
always recomputed by atlas_snapshot.digest() - callers must not fall back to
reading the snapshot's own declared integrity digest field themselves (that
is the one prohibited shortcut - "client_side_digest_verification" - the
frozen Phase 18A policy calls out by name)."""

from __future__ import annotations

import atlas_snapshot

from .errors import EvidenceFetchError, EvidenceOversizeError
from .models import FetchedEvidence
from .ports import EvidenceTransport

DEFAULT_MAX_EVIDENCE_BYTES = 5 * 1024 * 1024


class EvidenceClient:
    def __init__(
        self,
        transport: EvidenceTransport,
        *,
        max_bytes: int = DEFAULT_MAX_EVIDENCE_BYTES,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._transport = transport
        self._max_bytes = max_bytes

    def fetch(self, snapshot_id: str) -> FetchedEvidence:
        transport_failed = False
        try:
            raw = self._transport.fetch_snapshot(snapshot_id)
        except Exception:
            transport_failed = True
        if transport_failed:
            raise EvidenceFetchError("evidence transport unavailable")

        if not isinstance(raw, (bytes, bytearray, str)):
            raise EvidenceFetchError("evidence payload type invalid")
        size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
        if size > self._max_bytes:
            raise EvidenceOversizeError("evidence payload exceeds configured limit")

        parse_failed = False
        try:
            parsed = atlas_snapshot.parse(raw)
        except atlas_snapshot.SnapshotValidationError:
            parse_failed = True
        if parse_failed:
            raise EvidenceFetchError("evidence payload invalid")

        recomputed_digest = atlas_snapshot.digest(parsed)
        try:
            atlas_snapshot.verify(parsed)
            verified = True
        except atlas_snapshot.SnapshotIntegrityError:
            verified = False

        return FetchedEvidence(
            snapshot=parsed, recomputed_digest=recomputed_digest, verified=verified
        )
