"""
Local canonical serialization and fingerprinting - Setup Interpretation
Sprint 1. Self-contained: no import from atlas.market_context.fingerprint
or anywhere under atlas.market_context - this package's own dependency
graph stays fully independent, the same "well-understood, already-proven
shape, reused as a pattern, not a shared import" posture
atlas.market_context.fingerprint itself already took relative to
atlas.research_export.serialization one layer down. Two independent,
from-scratch implementations of the same shape are the deliberate choice
here, not an oversight - a shared import would create a dependency this
package's own boundary (atlas.core.primitives and the standard library
only) does not permit.

Exists to protect against a real risk that isn't about numeric params: a
maintainer editing which DirectionSource a setup's interpretation rule
maps to (definitions.py's own SETUP_INTERPRETATION_V1) without
remembering to bump SETUP_INTERPRETATION_V1's version string. The
fingerprint makes that edit detectable even when the version label
didn't change - the same two-layer audit model (declared version +
machine-verifiable fingerprint) atlas.market_context already established
for its own definitions.
"""
import dataclasses
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any

FINGERPRINT_HEX_LENGTH = 16


def to_canonical(value: Any) -> Any:
    """Recursively converts value into a structure of plain
    dict/list/str/int/float/bool/None only - the sole input canonical_json()
    ever serializes. Never depends on Python object identity (id(), default
    hash/set ordering) - every ordering decision below is made explicitly,
    on values, not on however a container happened to be built."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_canonical(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_canonical(val) for key, val in value.items()}
    if isinstance(value, Enum):
        return to_canonical(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [to_canonical(item) for item in value]  # order preserved, never sorted
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"setup_interpretation.fingerprint cannot canonicalize {type(value)!r}")


def canonical_json(value: Any) -> str:
    """Stable, whitespace-free, alphabetical-key JSON text - the exact
    input compute_fingerprint() hashes. sort_keys=True is what makes a
    Mapping's insertion order (and a dataclass's field declaration order)
    irrelevant to the output."""
    return json.dumps(to_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_fingerprint(value: Any) -> str:
    """SHA-256 hex digest of canonical_json(value), truncated to the first
    16 lowercase hex characters - the same length/format
    atlas.market_context.fingerprint (and, one layer further down,
    atlas.live_view.cache.py's own registry fingerprint) already
    established as this codebase's convention, reused here independently,
    not via a shared import."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_HEX_LENGTH]
