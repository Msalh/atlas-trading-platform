"""Explicit migration runner for the isolated snapshot store."""

from __future__ import annotations

from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).parent


def run_snapshot_migrations(database_url: str) -> None:
    """Apply each immutable snapshot-store migration once."""
    if not database_url:
        raise RuntimeError("snapshot database URL is required")
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS public.atlas_snapshot_schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {
            row[0]
            for row in connection.execute(
                "SELECT filename FROM public.atlas_snapshot_schema_migrations"
            ).fetchall()
        }
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            with connection.transaction():
                connection.execute(path.read_text(encoding="utf-8"))
                connection.execute(
                    """
                    INSERT INTO public.atlas_snapshot_schema_migrations (filename)
                    VALUES (%s)
                    """,
                    (path.name,),
                )
