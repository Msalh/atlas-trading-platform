"""Classification-only private-network probe for Phase 17E certification.

This module is operational tooling, not application code. It never prints
credentials, connection strings, SQL text, response bodies, or evidence.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
import psycopg

from atlas_snapshot_api.conninfo import build_reader_conninfo


@dataclass(frozen=True, slots=True)
class ReaderAssertions:
    current_user: bool
    session_user: bool
    transaction_read_only: bool
    default_transaction_read_only: bool
    schema_usage: bool
    schema_create_denied: bool
    table_select: bool
    table_insert_denied: bool
    table_update_denied: bool
    table_delete_denied: bool
    table_truncate_denied: bool
    mutation_rejected: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.current_user,
                self.session_user,
                self.transaction_read_only,
                self.default_transaction_read_only,
                self.schema_usage,
                self.schema_create_denied,
                self.table_select,
                self.table_insert_denied,
                self.table_update_denied,
                self.table_delete_denied,
                self.table_truncate_denied,
                self.mutation_rejected,
            )
        )


def classify_reader(
    *,
    current_user: str,
    session_user: str,
    transaction_read_only: str,
    default_transaction_read_only: str,
    schema_usage: bool,
    schema_create: bool,
    table_select: bool,
    table_insert: bool,
    table_update: bool,
    table_delete: bool,
    table_truncate: bool,
    mutation_rejected: bool,
) -> ReaderAssertions:
    return ReaderAssertions(
        current_user=current_user == "atlas_snapshot_reader",
        session_user=session_user != current_user,
        transaction_read_only=transaction_read_only == "on",
        default_transaction_read_only=default_transaction_read_only == "on",
        schema_usage=schema_usage is True,
        schema_create_denied=schema_create is False,
        table_select=table_select is True,
        table_insert_denied=table_insert is False,
        table_update_denied=table_update is False,
        table_delete_denied=table_delete is False,
        table_truncate_denied=table_truncate is False,
        mutation_rejected=mutation_rejected,
    )


def emit(name: str, passed: bool, detail: str = "") -> None:
    suffix = f" {detail}" if detail else ""
    print(f"{name}={'PASS' if passed else 'FAIL'}{suffix}", flush=True)


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing_configuration:{name}")
    return value


def response_object(response: httpx.Response) -> dict[str, Any] | None:
    try:
        value = response.json()
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def certify_reader() -> ReaderAssertions:
    with psycopg.connect(
        build_reader_conninfo(required("SNAPSHOT_READER_DATABASE_URL")),
        connect_timeout=10,
    ) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_user, session_user,
                   current_setting('transaction_read_only'),
                   current_setting('default_transaction_read_only'),
                   has_schema_privilege(
                     current_user, 'atlas_snapshot', 'USAGE'),
                   has_schema_privilege(
                     current_user, 'atlas_snapshot', 'CREATE'),
                   has_table_privilege(
                     current_user, 'atlas_snapshot.snapshots', 'SELECT'),
                   has_table_privilege(
                     current_user, 'atlas_snapshot.snapshots', 'INSERT'),
                   has_table_privilege(
                     current_user, 'atlas_snapshot.snapshots', 'UPDATE'),
                   has_table_privilege(
                     current_user, 'atlas_snapshot.snapshots', 'DELETE'),
                   has_table_privilege(
                     current_user, 'atlas_snapshot.snapshots', 'TRUNCATE')
            """
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("reader_privilege_query_empty")
        rejected = False
        try:
            cursor.execute(
                "CREATE TABLE atlas_snapshot.phase17e_forbidden(id integer)"
            )
        except psycopg.Error:
            rejected = True
            connection.rollback()
    assertions = classify_reader(
        current_user=row[0],
        session_user=row[1],
        transaction_read_only=row[2],
        default_transaction_read_only=row[3],
        schema_usage=row[4],
        schema_create=row[5],
        table_select=row[6],
        table_insert=row[7],
        table_update=row[8],
        table_delete=row[9],
        table_truncate=row[10],
        mutation_rejected=rejected,
    )
    for name in ReaderAssertions.__dataclass_fields__:
        emit(f"reader_{name}", getattr(assertions, name))
    return assertions


async def call(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    correlation_id: str,
    token: str | None = None,
    payload: dict[str, str] | None = None,
) -> tuple[httpx.Response, float]:
    headers = {"X-Correlation-ID": correlation_id}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.monotonic()
    response = await client.request(method, path, headers=headers, json=payload)
    return response, (time.monotonic() - started) * 1000


async def certify_api() -> list[bool]:
    checks: list[bool] = []
    reader = required("SNAPSHOT_READER_API_TOKEN")
    operator = required("SNAPSHOT_OPERATOR_API_TOKEN")
    async with httpx.AsyncClient(
        base_url=required("SNAPSHOT_API_BASE_URL").rstrip("/"),
        timeout=httpx.Timeout(20, connect=10),
        follow_redirects=False,
    ) as client:
        health, elapsed = await call(client, "GET", "/health", "p17e-health")
        checks.append(health.status_code == 200)
        emit("health", checks[-1], f"status={health.status_code} ms={elapsed:.1f}")

        readiness, elapsed = await call(
            client, "GET", "/readiness", "p17e-readiness", reader
        )
        checks.append(
            readiness.status_code == 200
            and readiness.headers.get("X-Correlation-ID") == "p17e-readiness"
        )
        emit(
            "readiness",
            checks[-1],
            f"status={readiness.status_code} ms={elapsed:.1f}",
        )

        missing, _ = await call(client, "GET", "/readiness", "p17e-missing")
        invalid, _ = await call(
            client, "GET", "/readiness", "p17e-invalid", "synthetic-invalid"
        )
        checks.append(missing.status_code == 401 and invalid.status_code == 401)
        emit(
            "authentication",
            checks[-1],
            f"missing={missing.status_code} invalid={invalid.status_code}",
        )

        forbidden, _ = await call(
            client,
            "POST",
            "/api/v1/snapshots/capture",
            "p17e-forbidden",
            reader,
            {
                "symbol": "MNQ",
                "timeframe": "5m",
                "strategy_id": "displacement_volume_context",
            },
        )
        checks.append(forbidden.status_code == 403)
        emit("authorization", checks[-1], f"status={forbidden.status_code}")

        captured, elapsed = await call(
            client,
            "POST",
            "/api/v1/snapshots/capture",
            "p17e-capture",
            operator,
            {
                "symbol": "MNQ",
                "timeframe": "5m",
                "strategy_id": "displacement_volume_context",
            },
        )
        captured_body = response_object(captured)
        capture_ok = (
            captured.status_code == 201
            and captured_body is not None
            and captured_body.get("schema_version") == "snapshot_private_api.v1"
            and captured_body.get("correlation_id") == "p17e-capture"
            and isinstance(captured_body.get("snapshot_id"), str)
            and isinstance(captured_body.get("evidence_digest"), str)
        )
        checks.append(capture_ok)
        emit("capture", capture_ok, f"status={captured.status_code} ms={elapsed:.1f}")
        if not capture_ok or captured_body is None:
            return checks

        snapshot_id = captured_body["snapshot_id"]
        digest = captured_body["evidence_digest"]
        routes = (
            ("retrieval", f"/api/v1/snapshots/{snapshot_id}"),
            ("metadata", f"/api/v1/snapshots/{snapshot_id}/metadata"),
            ("integrity", f"/api/v1/snapshots/{snapshot_id}/integrity"),
        )
        for name, path in routes:
            response, route_elapsed = await call(
                client, "GET", path, f"p17e-{name}", reader
            )
            value = response_object(response)
            passed = response.status_code == 200 and value is not None
            if name in {"metadata", "integrity"} and value is not None:
                passed = (
                    passed
                    and value.get("snapshot_id") == snapshot_id
                    and value.get("evidence_digest") == digest
                )
            if name == "integrity" and value is not None:
                passed = passed and value.get("valid") is True
            checks.append(passed)
            emit(
                name,
                passed,
                f"status={response.status_code} ms={route_elapsed:.1f}",
            )
    return checks


async def main() -> int:
    try:
        reader = certify_reader()
        if os.environ.get("PHASE17E_READER_SESSION_ONLY") == "true":
            emit("probe_execution", reader.passed, "mode=reader_session_only")
            return 0 if reader.passed else 1
        api_checks = await certify_api()
        passed = reader.passed and all(api_checks)
    # A certification process must fail closed without rendering arbitrary
    # dependency exception strings, which may contain private connection data.
    except Exception:  # noqa: BLE001
        emit("probe_execution", False, "category=certification_failure")
        await asyncio.sleep(300)
        return 1
    emit("probe_execution", passed, f"api_checks={len(api_checks)}")
    if not passed:
        await asyncio.sleep(300)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
