"""Psycopg adapter for the append-only snapshot repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from atlas_snapshot import (
    SnapshotIntegrityError,
    SnapshotValidationError,
    extract_metadata,
    parse,
)

from .errors import (
    SnapshotConflictError,
    SnapshotCorruptionError,
    SnapshotIdempotencyConflictError,
    SnapshotNotFoundError,
    SnapshotStoreError,
    UnsupportedStoredSnapshotError,
)
from .models import AppendResult, SnapshotListCursor, SnapshotPage

_SELECT_COLUMNS = """
    snapshot_id::text AS snapshot_id,
    snapshot_schema_version,
    evidence_profile,
    canonicalization_profile,
    evidence_digest,
    idempotency_key,
    canonical_payload,
    created_at,
    evaluated_at,
    latest_closed_at,
    economic_instrument,
    market_data_provider,
    market_data_series_symbol,
    market_data_series_type,
    timeframe,
    strategy_id,
    strategy_version,
    trust_status,
    supersedes_snapshot_id::text AS supersedes_snapshot_id
"""


class PostgresSnapshotRepository:
    """Insert-only runtime adapter; retrieval verifies canonical evidence."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def append(self, canonical_payload: bytes) -> AppendResult:
        snapshot, metadata = self._decode_payload(canonical_payload)
        values = (
            metadata.snapshot_id,
            snapshot["snapshot_schema_version"],
            snapshot["evidence_profile"],
            snapshot["canonicalization_profile"],
            metadata.evidence_digest,
            snapshot["idempotency_key"],
            canonical_payload,
            self._timestamp(metadata.created_at, "created_at"),
            self._optional_timestamp(metadata.evaluated_at, "evaluated_at"),
            self._optional_timestamp(metadata.latest_closed_at, "latest_closed_at"),
            metadata.economic_instrument,
            metadata.market_data_provider,
            metadata.market_data_series_symbol,
            metadata.market_data_series_type,
            metadata.timeframe,
            metadata.strategy_id,
            metadata.strategy_version,
            metadata.trust_status,
            metadata.supersedes_snapshot_id,
        )
        try:
            async with self._pool.connection() as connection:
                cursor = await connection.execute(
                    """
                    INSERT INTO atlas_snapshot.snapshots (
                        snapshot_id,
                        snapshot_schema_version,
                        evidence_profile,
                        canonicalization_profile,
                        evidence_digest,
                        idempotency_key,
                        canonical_payload,
                        created_at,
                        evaluated_at,
                        latest_closed_at,
                        economic_instrument,
                        market_data_provider,
                        market_data_series_symbol,
                        market_data_series_type,
                        timeframe,
                        strategy_id,
                        strategy_version,
                        trust_status,
                        supersedes_snapshot_id
                    )
                    VALUES (
                        %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING snapshot_id
                    """,
                    values,
                )
                inserted = await cursor.fetchone()
                if inserted is not None:
                    return AppendResult(metadata=metadata, created=True)

                async with connection.cursor(row_factory=dict_row) as conflict_cursor:
                    await conflict_cursor.execute(
                        f"""
                        SELECT {_SELECT_COLUMNS}
                        FROM atlas_snapshot.snapshots
                        WHERE snapshot_id = %s::uuid
                           OR idempotency_key = %s
                           OR evidence_digest = %s
                        ORDER BY
                            (idempotency_key = %s) DESC,
                            (snapshot_id = %s::uuid) DESC
                        LIMIT 1
                        """,
                        (
                            metadata.snapshot_id,
                            snapshot["idempotency_key"],
                            metadata.evidence_digest,
                            snapshot["idempotency_key"],
                            metadata.snapshot_id,
                        ),
                    )
                    row = await conflict_cursor.fetchone()
                if row is None:
                    raise SnapshotConflictError(
                        "snapshot insert conflicted without a visible row"
                    )
                if bytes(row["canonical_payload"]) == canonical_payload:
                    verified = self._verify_row(row)
                    return AppendResult(metadata=verified, created=False)
                if row["idempotency_key"] == snapshot["idempotency_key"]:
                    raise SnapshotIdempotencyConflictError(
                        "idempotency key already exists with different evidence"
                    )
                raise SnapshotConflictError(
                    "snapshot identity or digest already exists with different bytes"
                )
        except SnapshotStoreError:
            raise
        except Exception as error:
            raise SnapshotStoreError("snapshot append transaction failed") from error

    async def get_by_snapshot_id(self, snapshot_id: str) -> Mapping[str, Any]:
        return await self._get_one("snapshot_id = %s::uuid", (snapshot_id,))

    async def get_by_evidence_digest(
        self, evidence_digest: str
    ) -> Mapping[str, Any]:
        return await self._get_one("evidence_digest = %s", (evidence_digest,))

    async def _get_one(
        self, predicate: str, parameters: Sequence[Any]
    ) -> Mapping[str, Any]:
        try:
            async with (
                self._pool.connection() as connection,
                connection.cursor(row_factory=dict_row) as cursor,
            ):
                await cursor.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM atlas_snapshot.snapshots
                    WHERE {predicate}
                    """,
                    parameters,
                )
                row = await cursor.fetchone()
            if row is None:
                raise SnapshotNotFoundError("snapshot not found")
            snapshot, _ = self._decode_payload(bytes(row["canonical_payload"]))
            self._verify_row(row)
            return snapshot
        except SnapshotStoreError:
            raise
        except Exception as error:
            raise SnapshotStoreError("snapshot retrieval failed") from error

    async def list_metadata(
        self,
        *,
        limit: int,
        cursor: SnapshotListCursor | None = None,
    ) -> SnapshotPage:
        if isinstance(limit, bool) or limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        parameters: list[Any] = []
        predicate = ""
        if cursor is not None:
            predicate = (
                "WHERE (created_at, snapshot_id) < (%s, %s::uuid)"
            )
            parameters.extend((cursor.created_at, cursor.snapshot_id))
        parameters.append(limit + 1)
        try:
            async with (
                self._pool.connection() as connection,
                connection.cursor(row_factory=dict_row) as result,
            ):
                await result.execute(
                    f"""
                    SELECT {_SELECT_COLUMNS}
                    FROM atlas_snapshot.snapshots
                    {predicate}
                    ORDER BY created_at DESC, snapshot_id DESC
                    LIMIT %s
                    """,
                    parameters,
                )
                rows = await result.fetchall()
            verified = tuple(self._verify_row(row) for row in rows[:limit])
            next_cursor = None
            if len(rows) > limit and verified:
                last = rows[limit - 1]
                next_cursor = SnapshotListCursor(
                    created_at=self._as_utc(last["created_at"]),
                    snapshot_id=last["snapshot_id"],
                )
            return SnapshotPage(items=verified, next_cursor=next_cursor)
        except SnapshotStoreError:
            raise
        except Exception as error:
            raise SnapshotStoreError("snapshot metadata listing failed") from error

    @staticmethod
    def _decode_payload(payload: bytes):
        try:
            snapshot = parse(payload)
            metadata = extract_metadata(snapshot)
            return snapshot, metadata
        except SnapshotIntegrityError as error:
            raise SnapshotCorruptionError(
                "canonical payload failed digest verification"
            ) from error
        except SnapshotValidationError as error:
            raise SnapshotCorruptionError(
                "canonical payload failed schema or canonical validation"
            ) from error

    def _verify_row(self, row: Mapping[str, Any]):
        if row["snapshot_schema_version"] != "trader_now_snapshot.v1":
            raise UnsupportedStoredSnapshotError(
                "stored snapshot schema is unsupported"
            )
        _, metadata = self._decode_payload(bytes(row["canonical_payload"]))
        expected = {
            "snapshot_id": metadata.snapshot_id,
            "evidence_digest": metadata.evidence_digest,
            "created_at": self._timestamp(metadata.created_at, "created_at"),
            "evaluated_at": self._optional_timestamp(
                metadata.evaluated_at, "evaluated_at"
            ),
            "latest_closed_at": self._optional_timestamp(
                metadata.latest_closed_at, "latest_closed_at"
            ),
            "economic_instrument": metadata.economic_instrument,
            "market_data_provider": metadata.market_data_provider,
            "market_data_series_symbol": metadata.market_data_series_symbol,
            "market_data_series_type": metadata.market_data_series_type,
            "timeframe": metadata.timeframe,
            "strategy_id": metadata.strategy_id,
            "strategy_version": metadata.strategy_version,
            "trust_status": metadata.trust_status,
            "supersedes_snapshot_id": metadata.supersedes_snapshot_id,
        }
        for key, value in expected.items():
            stored = row[key]
            if isinstance(value, datetime):
                stored = self._as_utc(stored)
            if stored != value:
                raise SnapshotCorruptionError(
                    f"derived metadata disagrees with canonical payload: {key}"
                )
        if row["evidence_profile"] != "trader_now_complete.v1":
            raise SnapshotCorruptionError("stored evidence profile disagrees")
        if row["canonicalization_profile"] != "atlas-jcs.v1":
            raise SnapshotCorruptionError(
                "stored canonicalization profile disagrees"
            )
        return metadata

    @staticmethod
    def _timestamp(value: str, label: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SnapshotCorruptionError(f"invalid {label}") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise SnapshotCorruptionError(f"invalid {label}")
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _optional_timestamp(
        cls, value: str | None, label: str
    ) -> datetime | None:
        return None if value is None else cls._timestamp(value, label)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise SnapshotCorruptionError("stored timestamp is timezone-naive")
        return value.astimezone(timezone.utc)
