"""Checksum-bound migrations for the isolated Phase 18G database."""

from .runner import run_ai_persistence_migrations

__all__ = ["run_ai_persistence_migrations"]
