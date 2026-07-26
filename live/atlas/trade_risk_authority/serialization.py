"""Deterministic public serialization for P2A contract fixtures."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from atlas.core.primitives import Price

from .models import ProposedTrade


def _project(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Price):
        return {"tick_size": str(value.tick_size), "value": str(value.value)}
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _project(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: _project(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_project(item) for item in value]
    return value


def serialize_proposed_trade(proposal: ProposedTrade) -> bytes:
    return json.dumps(
        _project(proposal),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
