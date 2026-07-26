"""Deterministic canonical serialization and identity for trade-plan contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from atlas.core.primitives import Price, Symbol, Timeframe


def project(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Price):
        return {
            "tick_size": format(Decimal(str(value.tick_size)), "f"),
            "value": format(Decimal(str(value.value)), "f"),
        }
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Symbol):
        return value.ticker
    if isinstance(value, Timeframe):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: project(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): project(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [project(item) for item in value]
    return value


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        project(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_identity(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
