"""Production-entrypoint regressions for disabled Phase 18 Snapshot startup."""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo


class _Pool:
    instances = []

    def __init__(self, *_args, **_kwargs):
        self.open_calls = 0
        self.close_calls = 0
        self.__class__.instances.append(self)

    async def open(self, *, wait):
        assert wait is True
        self.open_calls += 1

    async def close(self):
        self.close_calls += 1


@pytest.mark.parametrize("explicit", [False, True])
def test_snapshot_starts_without_phase18_composition(monkeypatch, explicit):
    values = {
        "RAILWAY_SERVICE_NAME": "snapshot-private-api",
        "SNAPSHOT_WRITER_DATABASE_URL": make_conninfo(
            host="synthetic.invalid", dbname="snapshot", user="writer", password="local"
        ),
        "SNAPSHOT_READER_DATABASE_URL": make_conninfo(
            host="synthetic.invalid",
            dbname="snapshot",
            user="reader",
            password="local",
            options="-c role=atlas_snapshot_reader",
        ),
        "TRADER_NOW_BASE_URL": "http://trader-now.synthetic.invalid",
        "TRADER_NOW_API_KEY": "synthetic-local-only",
        "SNAPSHOT_CAPTURE_ENABLED": "false",
        "SNAPSHOT_READER_API_TOKEN": "synthetic-reader",
        "SNAPSHOT_OPERATOR_API_TOKEN": "synthetic-operator",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in (
        "ATLAS_AI_SHADOW_ENABLED",
        "ATLAS_AI_PROVIDER_ENABLED",
        "ATLAS_AI_PERSISTENCE_MODE",
    ):
        if explicit:
            monkeypatch.setenv(
                name, "false" if name != "ATLAS_AI_PERSISTENCE_MODE" else "disabled"
            )
        else:
            monkeypatch.delenv(name, raising=False)

    import atlas.ai_persistence_runtime as persistence_module
    import atlas.shadow_ai_runtime as shadow_module
    import psycopg_pool

    calls = {"persistence": 0, "shadow": 0}

    def forbidden_persistence(*_args, **_kwargs):
        calls["persistence"] += 1
        raise AssertionError("AI persistence must not be composed")

    def forbidden_shadow(*_args, **_kwargs):
        calls["shadow"] += 1
        raise AssertionError("Shadow runtime must not be composed")

    monkeypatch.setattr(
        persistence_module, "build_ai_persistence_runtime", forbidden_persistence
    )
    monkeypatch.setattr(
        shadow_module, "build_shadow_analysis_runtime", forbidden_shadow
    )
    monkeypatch.setattr(psycopg_pool, "AsyncConnectionPool", _Pool)
    _Pool.instances.clear()
    sys.modules.pop("atlas_snapshot_api.runtime", None)
    sys.modules.pop("atlas.service_entrypoint", None)
    entrypoint = importlib.import_module("atlas.service_entrypoint")
    try:
        with TestClient(entrypoint.app) as client:
            assert client.get("/health").json() == {
                "ok": True,
                "service": "atlas-snapshot-private-api",
                "code": None,
            }
        assert calls == {"persistence": 0, "shadow": 0}
        assert len(_Pool.instances) == 2
        assert all(pool.open_calls == 1 for pool in _Pool.instances)
        assert all(pool.close_calls == 1 for pool in _Pool.instances)
    finally:
        sys.modules.pop("atlas_snapshot_api.runtime", None)
        sys.modules.pop("atlas.service_entrypoint", None)


def test_railway_start_command_uses_service_entrypoint():
    from pathlib import Path

    expected = "uvicorn atlas.service_entrypoint:app --host 0.0.0.0 --port $PORT"
    assert expected in Path("railway.json").read_text(encoding="utf-8")
    assert Path("Procfile").read_text(encoding="utf-8").strip() == f"web: {expected}"
