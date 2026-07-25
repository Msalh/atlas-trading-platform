"""Opaque, validated cursors for bounded snapshot listing."""

from __future__ import annotations

import base64
import json
from datetime import datetime

from atlas_snapshot_store import SnapshotListCursor


def encode_cursor(cursor: SnapshotListCursor | None) -> str | None:
    if cursor is None:
        return None
    raw = json.dumps(
        {
            "created_at": cursor.created_at.isoformat(),
            "snapshot_id": cursor.snapshot_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str | None) -> SnapshotListCursor | None:
    if value is None:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if set(payload) != {"created_at", "snapshot_id"}:
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        snapshot_id = payload["snapshot_id"]
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError
        return SnapshotListCursor(created_at=created_at, snapshot_id=snapshot_id)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ValueError("invalid cursor") from None
