"""Environment-owned production assembly for the private Snapshot API."""

from __future__ import annotations

import os

from atlas_snapshot_capture import (
    CaptureServiceConfig,
    HttpTraderNowClient,
    SnapshotCaptureService,
)
from atlas_snapshot_store import PostgresSnapshotRepository
from atlas.ai_persistence_runtime import build_ai_persistence_runtime
from atlas.config import Settings
from atlas.shadow_ai_runtime import build_shadow_analysis_runtime
from psycopg_pool import AsyncConnectionPool

from .app import create_snapshot_app
from .auth import SnapshotAuthConfig
from .conninfo import build_reader_conninfo


def _required(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _enabled() -> bool:
    value = os.getenv("SNAPSHOT_CAPTURE_ENABLED", "false")
    if value not in {"true", "false"}:
        raise RuntimeError("SNAPSHOT_CAPTURE_ENABLED must be true or false")
    return value == "true"


writer_pool = AsyncConnectionPool(
    _required("SNAPSHOT_WRITER_DATABASE_URL"),
    min_size=1,
    max_size=4,
    open=False,
)
reader_pool = AsyncConnectionPool(
    build_reader_conninfo(_required("SNAPSHOT_READER_DATABASE_URL")),
    min_size=1,
    max_size=4,
    open=False,
)
writer_repository = PostgresSnapshotRepository(writer_pool)
reader_repository = PostgresSnapshotRepository(reader_pool)
atlas_settings = Settings()
ai_persistence_runtime = None
shadow_analysis_runtime = None
if atlas_settings.atlas_ai_shadow_enabled == "true":
    ai_persistence_runtime = build_ai_persistence_runtime(atlas_settings)
    shadow_analysis_runtime = build_shadow_analysis_runtime(
        atlas_settings,
        persistence_runtime=ai_persistence_runtime,
    )
capture_config = CaptureServiceConfig(
    trader_now_base_url=_required("TRADER_NOW_BASE_URL"),
    trader_now_api_key=_required("TRADER_NOW_API_KEY"),
    enabled=_enabled(),
)
capture_service = SnapshotCaptureService(
    config=capture_config,
    client=HttpTraderNowClient(capture_config),
    repository=writer_repository,
    completed_observer=shadow_analysis_runtime,
)


async def _open_writer() -> None:
    await writer_pool.open(wait=True)


async def _open_reader() -> None:
    await reader_pool.open(wait=True)


async def _start_shadow_runtime() -> None:
    """Lifecycle marker for the already-composed default-disabled runtime."""


async def _close_shadow_runtime() -> None:
    if shadow_analysis_runtime is not None:
        shadow_analysis_runtime.close()
    if ai_persistence_runtime is not None:
        ai_persistence_runtime.close()


app = create_snapshot_app(
    capture_service=capture_service,
    reader_repository=reader_repository,
    auth=SnapshotAuthConfig(
        reader_token=_required("SNAPSHOT_READER_API_TOKEN"),
        operator_token=_required("SNAPSHOT_OPERATOR_API_TOKEN"),
    ),
    startup_callbacks=(_open_writer, _open_reader, _start_shadow_runtime),
    shutdown_callbacks=(
        writer_pool.close,
        reader_pool.close,
        _close_shadow_runtime,
    ),
)
