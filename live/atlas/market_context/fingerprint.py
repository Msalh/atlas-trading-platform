"""
Local canonical serialization and fingerprinting - Phase N1, Sprint 1. No
import from atlas.research_export or anywhere under atlas.research: this
package's own dependency graph stays fully self-contained rather than
resting on a judgment call about whether research_export counts as
"adjacent to" the frozen RE-1/RE-2 packages. The pattern this module
follows (a generic recursive-to-jsonable converter, feeding a
sort_keys=True json.dumps, feeding a truncated SHA-256 hex digest) mirrors
atlas.research_export.serialization's own canonical_json/content_checksum
in spirit - a well-understood, already-proven-in-this-codebase shape - but
is a completely independent, from-scratch implementation, not a shared
import.

Two-layer audit model this module exists to support (service.py, not part
of Sprint 1, will be the caller): classifier_version/calendar_version are
the human-facing declared identity; context_fingerprint is the
machine-verifiable proof underneath - if a definition's params are ever
hand-edited without bumping its version string, the fingerprint changes
even though the version label didn't. For that guarantee to hold, the
fingerprint's input must include the definitions' actual serialized
parameter values, never only their version strings - this module's
dataclass support (below) is what lets a future caller pass a whole
SessionCalendarDefinition/RegimeClassifierDefinition straight in and get
its params walked automatically, rather than having to remember to flatten
them by hand at every call site.

One deliberate divergence from research_export's own to_jsonable(): lists
and tuples here preserve their original order. research_export sorts
tuple/frozenset contents (a choice suited to its own frozenset-provenance
data); order is semantically meaningful data in this package's context and
must never be silently reordered.
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
        # dataclasses.fields() order is a class-definition-time constant -
        # already deterministic - but the final json.dumps(sort_keys=True)
        # below re-orders every dict's keys alphabetically by field name
        # regardless, which is the literal reading of "deterministic
        # field-name order": ordered BY the name, not by declaration
        # position.
        return {field.name: to_canonical(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_canonical(val) for key, val in value.items()}
    if isinstance(value, Enum):
        return to_canonical(value.value)
    if isinstance(value, datetime):
        # ISO-8601, deterministic regardless of naive/aware or which UTC
        # offset was attached - the same value always produces the same
        # string, never locale- or platform-dependent.
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [to_canonical(item) for item in value]  # order preserved, never sorted
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"market_context.fingerprint cannot canonicalize {type(value)!r}")


def canonical_json(value: Any) -> str:
    """Stable, whitespace-free, alphabetical-key JSON text - the exact
    input compute_fingerprint() hashes. sort_keys=True is what makes a
    Mapping's insertion order (and a dataclass's field declaration order)
    irrelevant to the output."""
    return json.dumps(to_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_fingerprint(value: Any) -> str:
    """SHA-256 hex digest of canonical_json(value), truncated to the first
    16 lowercase hex characters - the same length/format
    atlas.live_view.cache.py's own registry fingerprint already
    established, reused here as a convention, not a shared import. Not the
    same guarantee as atlas.research_export.serialization.content_checksum
    (a full, untruncated 64-character digest over a different kind of
    payload) - deliberately not named to imply the two are interchangeable."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_HEX_LENGTH]
