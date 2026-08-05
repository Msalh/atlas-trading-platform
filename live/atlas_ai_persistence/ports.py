"""Injected technology-neutral port for one logical atomic persistence action."""

from __future__ import annotations

from typing import Protocol

from .models import PersistenceReceipt, PersistenceRecord


class AtomicPersistencePort(Protocol):
    """Commit the complete record or make none of it externally visible."""

    def store_atomic(self, record: PersistenceRecord) -> PersistenceReceipt: ...
