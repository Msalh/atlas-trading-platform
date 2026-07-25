"""Standalone deterministic SDK for immutable TraderNow evidence snapshots."""

from .errors import (
    SnapshotError,
    SnapshotIntegrityError,
    SnapshotProjectionError,
    SnapshotValidationError,
)
from .models import SnapshotMetadata, SnapshotRecordIdentity
from .sdk import (
    CANONICALIZATION_PROFILE,
    DIGEST_ALGORITHM,
    EVIDENCE_PROFILE,
    SNAPSHOT_SCHEMA_VERSION,
    SOURCE_DOMAIN_SCHEMA_VERSION,
    SOURCE_RESPONSE_SCHEMA_VERSION,
    derive_idempotency_key,
    digest,
    extract_metadata,
    parse,
    project,
    serialize,
    validate,
    verify,
)

__all__ = [
    "CANONICALIZATION_PROFILE",
    "DIGEST_ALGORITHM",
    "EVIDENCE_PROFILE",
    "SNAPSHOT_SCHEMA_VERSION",
    "SOURCE_DOMAIN_SCHEMA_VERSION",
    "SOURCE_RESPONSE_SCHEMA_VERSION",
    "SnapshotError",
    "SnapshotIntegrityError",
    "SnapshotMetadata",
    "SnapshotProjectionError",
    "SnapshotRecordIdentity",
    "SnapshotValidationError",
    "derive_idempotency_key",
    "digest",
    "extract_metadata",
    "parse",
    "project",
    "serialize",
    "validate",
    "verify",
]
