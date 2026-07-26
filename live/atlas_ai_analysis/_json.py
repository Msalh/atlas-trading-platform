"""Pure deterministic JSON helpers for AI contract documents."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from .errors import AIAnalysisValidationError


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            plain(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AIAnalysisValidationError(
            "contract contains a non-JSON value"
        ) from error


def parse_json(payload: bytes | str) -> Any:
    if isinstance(payload, bytes):
        if payload.startswith(b"\xef\xbb\xbf"):
            raise AIAnalysisValidationError("UTF-8 BOM is forbidden")
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise AIAnalysisValidationError("payload must be valid UTF-8") from error
    elif isinstance(payload, str):
        text = payload
    else:
        raise AIAnalysisValidationError("payload must be bytes or text")
    try:
        return json.loads(
            text,
            parse_float=Decimal,
            parse_constant=_reject_non_finite,
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        raise AIAnalysisValidationError("payload is not valid JSON") from error


def _reject_non_finite(token: str) -> None:
    raise AIAnalysisValidationError(f"non-finite number is forbidden: {token}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AIAnalysisValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
