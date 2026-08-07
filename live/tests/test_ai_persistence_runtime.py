"""Offline qualification of the Phase 18H-1 composition boundary."""

from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from atlas.ai_persistence_runtime import (
    AIPersistenceRuntimeConfig,
    AIPersistenceStartupError,
    _verify_pool,
    build_ai_persistence_runtime,
)
from atlas.config import Settings


def _settings(**overrides):
    values = {
        "atlas_ai_persistence_mode": "disabled",
        "atlas_ai_persistence_database_url": "",
        "atlas_ai_persistence_connect_timeout_seconds": "5",
        "atlas_ai_persistence_pool_min_size": "1",
        "atlas_ai_persistence_pool_max_size": "4",
        "atlas_ai_persistence_pool_acquisition_timeout_seconds": "5",
        "atlas_ai_persistence_local_disposable_test": "false",
        "environment": "development",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeConnection:
    def execute(self, _statement):
        return self

    def fetchone(self):
        return (1,)


class _FakePool:
    instances: ClassVar[list[_FakePool]] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.open_calls = 0
        self.close_calls = 0
        self.connection_calls = 0
        self.__class__.instances.append(self)

    def open(self, *, wait, timeout):
        assert wait is True
        assert timeout > 0
        self.open_calls += 1

    def close(self):
        self.close_calls += 1

    def connection(self, *, timeout):
        assert timeout > 0
        self.connection_calls += 1
        return nullcontext(_FakeConnection())


@pytest.fixture(autouse=True)
def _clear_fake_pools():
    _FakePool.instances.clear()


def _required_settings(**overrides):
    values = {
        "atlas_ai_persistence_mode": "required",
        "atlas_ai_persistence_database_url": (
            "postgresql://phase18h_writer:synthetic@127.0.0.1:55432/phase18h"
        ),
        "atlas_ai_persistence_local_disposable_test": "true",
    }
    values.update(overrides)
    return _settings(**values)


def test_disabled_mode_does_not_construct_pool_or_coordinator() -> None:
    runtime = build_ai_persistence_runtime(
        _settings(), pool_factory=lambda **_kwargs: pytest.fail("pool constructed")
    )
    assert runtime.public_state() == {"status": "disabled", "required": False}
    assert runtime.coordinator is None
    runtime.close()
    runtime.close()
    assert runtime.state == "shutdown"


def test_required_mode_never_falls_back_to_existing_application_database() -> None:
    settings = _required_settings(atlas_ai_persistence_database_url="")
    settings.database_url = (
        "postgresql://application:must-not-be-used@application.example/application"
    )
    with pytest.raises(AIPersistenceStartupError) as caught:
        build_ai_persistence_runtime(settings, pool_factory=_FakePool)
    assert caught.value.classification == "configuration_invalid"
    assert not _FakePool.instances


def test_settings_does_not_read_secret_dsn_while_disabled(monkeypatch) -> None:
    import atlas.config as config_module

    class TrackingEnvironment(dict):
        def __init__(self):
            super().__init__({"ATLAS_AI_PERSISTENCE_MODE": "disabled"})
            self.reads = []

        def get(self, key, default=None):
            self.reads.append(key)
            return super().get(key, default)

    environment = TrackingEnvironment()
    monkeypatch.setattr(config_module.os, "environ", environment)
    settings = Settings()
    assert settings.atlas_ai_persistence_database_url == ""
    assert "ATLAS_AI_PERSISTENCE_DATABASE_URL" not in environment.reads


@pytest.mark.parametrize(
    "overrides",
    [
        {"atlas_ai_persistence_mode": "unknown"},
        {
            "atlas_ai_persistence_mode": "required",
            "atlas_ai_persistence_database_url": "",
        },
        {"atlas_ai_persistence_connect_timeout_seconds": "0"},
        {"atlas_ai_persistence_connect_timeout_seconds": "nan"},
        {"atlas_ai_persistence_pool_min_size": "0"},
        {"atlas_ai_persistence_pool_min_size": "5"},
        {"atlas_ai_persistence_pool_max_size": "0"},
        {"atlas_ai_persistence_pool_acquisition_timeout_seconds": "31"},
        {"atlas_ai_persistence_local_disposable_test": "yes"},
        {"environment": "production"},
    ],
)
def test_invalid_configuration_is_sanitized_and_opens_no_pool(overrides) -> None:
    settings = _required_settings(**overrides)
    with pytest.raises(AIPersistenceStartupError) as caught:
        build_ai_persistence_runtime(settings, pool_factory=_FakePool)
    assert caught.value.classification == "configuration_invalid"
    assert caught.value.__cause__ is caught.value.__context__ is None
    assert not _FakePool.instances
    assert "synthetic" not in repr(caught.value)


def test_production_style_configuration_requires_verify_full_tls() -> None:
    base = _required_settings(
        atlas_ai_persistence_database_url=(
            "postgresql://runtime_writer:synthetic@db.example/atlas_ai"
        ),
        atlas_ai_persistence_local_disposable_test="false",
        environment="production",
    )
    with pytest.raises(AIPersistenceStartupError):
        build_ai_persistence_runtime(base, pool_factory=_FakePool)
    valid = _required_settings(
        atlas_ai_persistence_database_url=(
            "postgresql://runtime_writer:synthetic@db.example/atlas_ai?sslmode=verify-full"
        ),
        atlas_ai_persistence_local_disposable_test="false",
        environment="production",
    )
    runtime = build_ai_persistence_runtime(
        valid, pool_factory=_FakePool, verifier=lambda *_args: "ready"
    )
    assert runtime.state == "ready"
    runtime.close()


def test_production_style_configuration_rejects_privileged_or_disposable_identity() -> None:
    for identity in ("postgres", "migration_user", "atlas_test_writer"):
        settings = _required_settings(
            atlas_ai_persistence_database_url=(
                f"postgresql://{identity}:synthetic@db.example/atlas_ai?sslmode=verify-full"
            ),
            atlas_ai_persistence_local_disposable_test="false",
            environment="production",
        )
        with pytest.raises(AIPersistenceStartupError):
            build_ai_persistence_runtime(settings, pool_factory=_FakePool)


def test_required_composition_constructs_one_pool_and_closes_once() -> None:
    runtime = build_ai_persistence_runtime(
        _required_settings(),
        pool_factory=_FakePool,
        verifier=lambda *_args: "ready",
    )
    assert len(_FakePool.instances) == 1
    pool = _FakePool.instances[0]
    assert pool.open_calls == 1
    assert pool.kwargs["reconnect_timeout"] == 0.0
    assert runtime.coordinator is not None
    assert runtime.public_state() == {"status": "ready", "required": True}
    runtime.close()
    runtime.close()
    assert pool.close_calls == 1
    assert runtime.coordinator is None


@pytest.mark.parametrize(
    "failure", ["unavailable", "schema_mismatch", "privilege_invalid"]
)
def test_partial_startup_failure_closes_pool_without_retry(failure) -> None:
    verifier_calls = 0

    def verifier(*_args):
        nonlocal verifier_calls
        verifier_calls += 1
        return failure

    with pytest.raises(AIPersistenceStartupError) as caught:
        build_ai_persistence_runtime(
            _required_settings(), pool_factory=_FakePool, verifier=verifier
        )
    assert caught.value.classification == failure
    assert caught.value.__cause__ is caught.value.__context__ is None
    assert len(_FakePool.instances) == 1
    assert _FakePool.instances[0].open_calls == 1
    assert _FakePool.instances[0].close_calls == 1
    assert verifier_calls == 1


@pytest.mark.parametrize(
    "migration_rows",
    [[], [("9999_unapproved.sql", "9" * 64)]],
)
def test_real_verifier_rejects_missing_or_unexpected_migration_metadata(
    migration_rows,
) -> None:
    class Result:
        def __init__(self, *, row=None, rows=None):
            self.row = row
            self.rows = rows

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows

    class Connection:
        def execute(self, statement):
            if "SELECT filename, sha256" in statement:
                return Result(rows=migration_rows)
            if "has_database_privilege" in statement:
                return Result(
                    row=(True, True, False, True, True, *([False] * 3), True, True, *([False] * 11))
                )
            return Result(row=(1,))

    class Pool:
        def connection(self, *, timeout):
            assert timeout > 0
            return nullcontext(Connection())

    config = AIPersistenceRuntimeConfig.from_settings(_required_settings())
    assert _verify_pool(Pool(), config) == "schema_mismatch"


def test_readiness_changes_truthfully_without_persistence_or_retry() -> None:
    outcomes = iter(["ready", "unavailable", "ready"])
    runtime = build_ai_persistence_runtime(
        _required_settings(),
        pool_factory=_FakePool,
        verifier=lambda *_args: next(outcomes),
    )
    assert runtime.state == "ready"
    assert runtime.refresh_readiness() == "unavailable"
    assert runtime.refresh_readiness() == "ready"
    pool = _FakePool.instances[0]
    assert pool.open_calls == 1
    assert runtime.coordinator is not None
    runtime.close()


def test_runtime_package_adds_no_provider_route_worker_or_background_invocation() -> None:
    root = Path(__file__).parents[1]
    source = (root / "atlas" / "ai_persistence_runtime.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any("openai" in name or "atlas_ai_orchestration" in name for name in imports)
    for prohibited in (
        "ProviderOrchestrator",
        "OpenAIProviderAdapter",
        "BackgroundTasks",
        "APIRouter",
        "create_task",
        ".persist(",
        "run_ai_persistence_migrations",
        "retry",
    ):
        assert prohibited not in source


def test_config_object_never_exposes_database_url_in_public_state() -> None:
    config = AIPersistenceRuntimeConfig.from_settings(_required_settings())
    runtime = build_ai_persistence_runtime(
        _required_settings(),
        pool_factory=_FakePool,
        verifier=lambda *_args: "ready",
    )
    rendered = repr(runtime.public_state())
    assert config.database_url not in rendered
    assert "127.0.0.1" not in rendered
    assert "synthetic" not in rendered
    runtime.close()
