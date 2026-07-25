"""Pure atlas-jcs.v1 normalization and canonical JSON operations."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from .errors import SnapshotValidationError

I_JSON_INTEGER_LIMIT = 9_007_199_254_740_991


def decimal_text(value: Decimal | float) -> str:
    """Return the frozen atlas-jcs.v1 fixed decimal representation."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SnapshotValidationError("non-finite numbers are forbidden")
        value = Decimal(str(value))
    if not value.is_finite():
        raise SnapshotValidationError("non-finite numbers are forbidden")
    if value == 0:
        return "0"
    try:
        text = format(value, "f")
    except InvalidOperation as error:
        raise SnapshotValidationError("invalid decimal value") from error
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text


def normalize(value: Any) -> Any:
    """Convert supported transport values into deterministic JSON values."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > I_JSON_INTEGER_LIMIT:
            raise SnapshotValidationError("integer exceeds the I-JSON safe range")
        return value
    if isinstance(value, (float, Decimal)):
        return decimal_text(value)
    if isinstance(value, Enum):
        return normalize(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise SnapshotValidationError("timestamps must be timezone-aware")
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if isinstance(value, UUID):
        return str(value).lower()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: normalize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SnapshotValidationError("mapping keys must be strings")
            if key in result:
                raise SnapshotValidationError("duplicate mapping key")
            result[key] = normalize(item)
        return result
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    raise SnapshotValidationError(
        f"unsupported canonical value type: {type(value).__name__}"
    )


def to_plain(value: Any) -> Any:
    """Copy an immutable JSON tree into ordinary JSON containers."""
    if isinstance(value, Mapping):
        return {key: to_plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [to_plain(item) for item in value]
    return value


def freeze(value: Any) -> Any:
    """Recursively freeze an already-normalized JSON tree."""
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def canonical_bytes(value: Any) -> bytes:
    """Serialize normalized JSON using the atlas-jcs.v1 byte profile."""
    return json.dumps(
        to_plain(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
