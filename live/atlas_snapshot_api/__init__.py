"""Private authenticated transport boundary for Atlas snapshots."""

from .app import create_snapshot_app
from .auth import (
    SnapshotAuthConfig,
    SnapshotPrincipal,
    SnapshotRole,
)
from .models import API_SCHEMA_VERSION
from .rate_limit import FixedWindowRateLimiter

__all__ = [
    "API_SCHEMA_VERSION",
    "FixedWindowRateLimiter",
    "SnapshotAuthConfig",
    "SnapshotPrincipal",
    "SnapshotRole",
    "create_snapshot_app",
]
