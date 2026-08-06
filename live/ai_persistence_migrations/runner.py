"""Narrow checksum-bound migration runner for the Phase 18G database."""

from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).parent
_LOCK_CLASS = 1807
_LOCK_ID = 18


def run_ai_persistence_migrations(database_url: str) -> None:
    if not database_url:
        raise RuntimeError("AI persistence database URL is required")
    paths = tuple(sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")))
    expected = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }
    with psycopg.connect(database_url) as connection, connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)", (_LOCK_CLASS, _LOCK_ID)
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS public.atlas_ai_persistence_schema_migrations (
                filename TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = dict(
            connection.execute(
                "SELECT filename, sha256 FROM public.atlas_ai_persistence_schema_migrations ORDER BY filename"
            ).fetchall()
        )
        if set(applied) - set(expected):
            raise RuntimeError("unsupported AI persistence migration state")
        for filename, checksum in applied.items():
            if expected[filename] != checksum:
                raise RuntimeError("AI persistence migration checksum mismatch")
        for path in paths:
            if path.name in applied:
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO public.atlas_ai_persistence_schema_migrations (filename, sha256) VALUES (%s, %s)",
                (path.name, expected[path.name]),
            )
