"""
Phase N4 Sprint 1. Local canonical serialization and fingerprinting for the
Research Engine's own entities - self-contained, no import from
atlas.setup_interpretation.fingerprint or atlas.market_context.fingerprint,
the same "well-understood, already-proven shape, reused as a pattern, not a
shared import" posture both of those modules already took relative to each
other. A third, independent, from-scratch implementation of the identical
shape is the deliberate choice here - a shared import would create a
dependency Research Engine's own boundary (the standard library only, for
this module) does not permit, and would make this package's fingerprints
silently dependent on another package's own implementation choices.

Exists for the same reason it exists everywhere else in this codebase: an
entity's declared identity (a `*_version`/`kind`/`status` field) can be
edited without a human remembering to signal that the edit happened. The
fingerprint is the machine-verifiable proof underneath the label - the same
two-layer audit model (declared version + fingerprint) Market Context
established first and Setup Interpretation later reused independently.

Sprint 1 scope: this module is a pure, generic, stateless utility - not a
service. It computes nothing about what a Research Engine entity MEANS; it
only turns one into a stable digest. The functions that decide WHEN to call
compute_fingerprint() for a given Hypothesis/Experiment/Realization (as
opposed to leaving that field None, still valid on the two backward-
compatible types - see models.py's own docstring) belong to later sprints
(Experiment Builder, Sprint 5; Promotion, Sprint 9), not here.

--- Never hash an entity that carries its own fingerprint field ---

Unlike SETUP_INTERPRETATION_V1 (hashed by atlas.setup_interpretation's own
fingerprint module) or the {session_calendar, regime_classifier} dict
Market Context hashes, every new Research Engine entity (Feature, Finding,
Realization, Evidence, ValidationResult, LeaderboardSnapshot,
PromotionRecord, and Experiment's semantic_fingerprint/
execution_fingerprint pair) carries its OWN fingerprint field(s) ON ITSELF,
not on a separate downstream type. Calling compute_fingerprint() directly
on one of these - `compute_fingerprint(some_feature)` - would be a bug:
the hash would depend on whatever value the object's own fingerprint
field already held, making two objects with identical semantic content
hash differently purely because one had `fingerprint=None` and the other
already had a value set.

This was originally handled as a documentation-only discipline. Following
the same "enforce mechanically, not by convention alone" posture this
codebase already applies to dependency boundaries (see
docs/research-engine-design-principles.md Principle VIII.3), to_canonical()
below now REFUSES - raises SelfReferentialFingerprintError - the moment it
is asked to canonicalize a dataclass INSTANCE that itself declares a field
literally named `fingerprint` or ending in `_fingerprint`, at any depth.
Every future sprint that computes one of these entities' real fingerprint
value(s) MUST build an explicit, deliberately curated projection first - a
plain dict of only the fields that define the entity's semantic identity,
excluding every id, timestamp, lifecycle-status, provenance field, and
every fingerprint field itself - and hash that projection, never the
entity.

The guard applies only to dataclass instances, not to plain dict/Mapping
inputs - deliberately. A Mapping the caller hand-builds has no "self" to
reference; unlike an entity, it was never going to have its own
fingerprint field retroactively populated. This distinction is load-
bearing for Experiment's semantic_fingerprint/execution_fingerprint pair
(see models.py): execution_fingerprint is deliberately COMPUTED FROM a
projection that nests the already-computed semantic_fingerprint value
alongside code_version/seed - `compute_fingerprint({"semantic_fingerprint":
semantic, "code_version": code_version, ...})` - which is compositional
(execution_fingerprint depends on semantic_fingerprint), not self-
referential (it never depends on its own eventual value). A Mapping guard
would make this required, legitimate pattern impossible to express. What
the guard cannot catch is a caller manually converting an entity to a dict
first (e.g. `dataclasses.asdict(some_feature)`) before hashing - that
remains a documented discipline, same as before, on the (unusual, no
current call site does it) path that routes around the type check
entirely. See test_research_fingerprint.py's own
test_hashing_a_self_referencing_object_raises_instead_of_producing_an_unstable_hash
and test_the_correct_pattern_excludes_the_fingerprint_field_before_hashing
for a concrete, executable demonstration of both the guard and the fix.
"""
import dataclasses
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any

FINGERPRINT_HEX_LENGTH = 16


class SelfReferentialFingerprintError(ValueError):
    """Raised by to_canonical()/compute_fingerprint() when asked to hash a
    dataclass or Mapping that itself carries a field/key named `fingerprint`
    (or ending in `_fingerprint`) - hashing it would make the result depend
    on its own prior value. Build an explicit projection excluding that
    field/key first, and hash the projection instead."""


def _is_fingerprint_name(name: str) -> bool:
    return name == "fingerprint" or name.endswith("_fingerprint")


def to_canonical(value: Any) -> Any:
    """Recursively converts value into a structure of plain
    dict/list/str/int/float/bool/None only - the sole input canonical_json()
    ever serializes. Never depends on Python object identity (id(), default
    hash/set ordering) - every ordering decision below is made explicitly,
    on values, not on however a container happened to be built."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            if _is_fingerprint_name(f.name):
                raise SelfReferentialFingerprintError(
                    f"refusing to compute a fingerprint over {type(value).__name__!r}, which has its own "
                    f"{f.name!r} field - hashing the entity directly would make the result depend on its own "
                    f"prior value. Build an explicit projection of only the semantically-defining fields, "
                    f"excluding {f.name!r}, and hash that projection instead."
                )
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
    raise TypeError(f"atlas.research.fingerprint cannot canonicalize {type(value)!r}")


def canonical_json(value: Any) -> str:
    """Stable, whitespace-free, alphabetical-key JSON text - the exact
    input compute_fingerprint() hashes. sort_keys=True is what makes a
    Mapping's insertion order (and a dataclass's field declaration order)
    irrelevant to the output."""
    return json.dumps(to_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_fingerprint(value: Any) -> str:
    """SHA-256 hex digest of canonical_json(value), truncated to the first
    16 lowercase hex characters - the same length/format
    atlas.market_context.fingerprint and atlas.setup_interpretation.fingerprint
    both already established as this codebase's convention, reused here
    independently, not via a shared import."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_HEX_LENGTH]
