"""PostgreSQL idempotency and sanitized reads for Shadow AI analysis."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ContextManager

import psycopg


@dataclass(frozen=True, slots=True)
class ShadowAnalysisRecord:
    snapshot_id: str
    outcome: str
    recorded_at: str
    summary: str | None
    citations: tuple[str, ...]
    limitations: tuple[str, ...]
    reason: str | None
    analysis_audit_id: str
    analysis_output_id: str | None


class PostgresShadowAnalysisStore:
    """Owns only the claim and allowlisted read side of the existing ledger."""

    def __init__(
        self,
        connection_factory: Callable[[], ContextManager[psycopg.Connection[Any]]],
    ) -> None:
        self._connection_factory = connection_factory

    def claim_snapshot(self, snapshot_id: str) -> bool:
        with self._connection_factory() as connection, connection.transaction():
            row = connection.execute(
                """
                INSERT INTO atlas_ai_persistence.shadow_analysis_claims (snapshot_id)
                VALUES (%s::uuid)
                ON CONFLICT DO NOTHING
                RETURNING snapshot_id
                """,
                (snapshot_id,),
            ).fetchone()
            return row is not None

    def latest(self) -> ShadowAnalysisRecord | None:
        records = self.history(limit=1)
        return records[0] if records else None

    def history(self, *, limit: int = 20) -> tuple[ShadowAnalysisRecord, ...]:
        bounded = max(1, min(int(limit), 100))
        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT analysis_audit_id::text, analysis_output_id::text, outcome,
                       snapshot_id::text, audit_recorded_at, audit_payload, output_payload
                FROM atlas_ai_persistence.persistence_records
                ORDER BY audit_recorded_at DESC, analysis_audit_id DESC
                LIMIT %s
                """,
                (bounded,),
            ).fetchall()
        return tuple(self._project(row) for row in rows)

    @staticmethod
    def _project(row: tuple[Any, ...]) -> ShadowAnalysisRecord:
        (
            audit_id,
            output_id,
            outcome,
            snapshot_id,
            recorded_at,
            audit_raw,
            output_raw,
        ) = row
        audit = json.loads(bytes(audit_raw))
        output = json.loads(bytes(output_raw)) if output_raw is not None else None
        claims = output.get("claims", []) if isinstance(output, dict) else []
        citations = tuple(
            citation
            for claim in claims
            if isinstance(claim, dict)
            for citation in claim.get("citations", [])
            if isinstance(citation, str)
        )
        timestamp = (
            recorded_at.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
            if isinstance(recorded_at, datetime)
            else str(recorded_at)
        )
        return ShadowAnalysisRecord(
            snapshot_id=str(snapshot_id),
            outcome=str(outcome),
            recorded_at=timestamp,
            summary=(output.get("summary") if isinstance(output, dict) else None),
            citations=citations,
            limitations=tuple(output.get("limitations", ()))
            if isinstance(output, dict)
            else (),
            reason=audit.get("reason_code") if isinstance(audit, dict) else None,
            analysis_audit_id=str(audit_id),
            analysis_output_id=str(output_id) if output_id is not None else None,
        )
