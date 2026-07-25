"""Database migrations owned exclusively by the snapshot store."""

from .runner import run_snapshot_migrations

__all__ = ["run_snapshot_migrations"]
