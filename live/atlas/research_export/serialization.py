"""
UI v2. One generic, deterministic, recursive converter from the frozen
RE-1/RE-2 dataclasses to plain JSON-able Python objects - no bespoke
per-dataclass function, and no analytics: every value that comes out was
already computed by RE-1/RE-2 (or scripts/certify_historical_dataset.py),
this module only changes its Python representation.

Ordering rule (a correction from the original architecture sketch, made
precise here): a `tuple`'s existing order is ALREADY deterministic (every
producing function in RE-1/RE-2 is pure, so the same input always yields
the same tuple order) and is frequently meaningful - e.g.
SetupProfile.entries is in registry order, ActivationEvent.activated_setups
is already sorted for display determinism at construction time.
Re-sorting a tuple here would silently scramble that meaning. Only
`frozenset`, which has no meaningful order at all, is explicitly sorted.
`Mapping`/`MappingProxyType` keys are always sorted, since dict key order
is an implementation detail this module should never depend on for
reproducibility.
"""
import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Pure, recursive. Handles every shape actually present in RE-1/RE-2's
    frozen dataclasses (dataclass, Enum, tuple, frozenset, Mapping,
    str/int/float/bool/None) plus datetime/date for robustness, even though
    none of RE-1/RE-2's own fields currently hold a raw datetime - every
    timestamp field in those packages is already an ISO-8601 string."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, frozenset):
        return sorted(to_jsonable(v) for v in value)
    if isinstance(value, (tuple, list)):
        return [to_jsonable(v) for v in value]
    raise TypeError(f"to_jsonable: no conversion rule for {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Stable, whitespace-free, sorted-key JSON text - the exact input the
    content checksum (below) is computed over, and reused for the
    pretty-printed on-disk form (with indent=2 added back at the call
    site) so the checked-in file and the checksum are always derived from
    the same canonical structure."""
    return json.dumps(to_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_checksum(payload: Any) -> str:
    """SHA-256 hex digest over canonical_json(payload) - the deterministic
    payload ONLY. Never computed over anything containing exported_at or
    any other dynamic export-metadata field; callers must pass the
    payload, not the full envelope+payload snapshot."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def pretty_json(value: Any) -> str:
    """The on-disk form written to research/snapshots/*.json - sorted
    keys (same canonical ordering as the checksum input) but
    human-reviewable, so a git diff of a regenerated snapshot is
    meaningful."""
    return json.dumps(to_jsonable(value), sort_keys=True, indent=2, ensure_ascii=True)
