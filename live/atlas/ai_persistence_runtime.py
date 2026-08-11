"""Fail-closed runtime composition for the disabled Phase 18 persistence boundary."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any, Final, Literal, NoReturn, Protocol

import psycopg
from psycopg import errors
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import ConnectionPool

from ai_persistence_migrations import expected_ai_persistence_migrations
from atlas_ai_persistence import PersistenceCoordinator
from atlas_ai_persistence_postgres import (
    PostgresAtomicPersistenceAdapter,
    PostgresShadowAnalysisStore,
)

if TYPE_CHECKING:
    from atlas.config import Settings

PersistenceState = Literal[
    "disabled",
    "starting",
    "ready",
    "unavailable",
    "configuration_invalid",
    "schema_mismatch",
    "privilege_invalid",
    "shutdown",
]

APPLICATION_NAME: Final = "atlas-ai-persistence"
_LOCAL_HOSTS: Final = frozenset({"127.0.0.1", "::1", "localhost"})
_PRIVILEGED_IDENTITY_TERMS: Final = (
    "admin",
    "migration",
    "owner",
    "postgres",
    "superuser",
)
_DISPOSABLE_TERMS: Final = ("disposable", "local", "test")


class _Pool(Protocol):
    def open(self, *, wait: bool, timeout: float) -> None: ...

    def close(self) -> None: ...

    def connection(self, *, timeout: float): ...


@dataclass(frozen=True, slots=True)
class AIPersistenceRuntimeConfig:
    mode: Literal["disabled", "required"]
    database_url: str = field(repr=False)
    connect_timeout_seconds: float
    pool_min_size: int
    pool_max_size: int
    pool_acquisition_timeout_seconds: float
    local_disposable_test: bool

    @classmethod
    def from_settings(cls, settings: Settings) -> AIPersistenceRuntimeConfig:
        mode = settings.atlas_ai_persistence_mode
        if mode not in {"disabled", "required"}:
            raise ValueError
        local = _closed_bool(settings.atlas_ai_persistence_local_disposable_test)
        if local and settings.environment != "development":
            raise ValueError
        connect_timeout = _bounded_float(
            settings.atlas_ai_persistence_connect_timeout_seconds, maximum=30.0
        )
        acquisition_timeout = _bounded_float(
            settings.atlas_ai_persistence_pool_acquisition_timeout_seconds,
            maximum=30.0,
        )
        minimum = _bounded_int(settings.atlas_ai_persistence_pool_min_size, maximum=20)
        maximum = _bounded_int(settings.atlas_ai_persistence_pool_max_size, maximum=20)
        if minimum > maximum:
            raise ValueError
        database_url = settings.atlas_ai_persistence_database_url
        if mode == "disabled":
            if local:
                raise ValueError
            database_url = ""
        else:
            _validate_database_url(database_url, local_disposable_test=local)
        return cls(
            mode=mode,
            database_url=database_url,
            connect_timeout_seconds=connect_timeout,
            pool_min_size=minimum,
            pool_max_size=maximum,
            pool_acquisition_timeout_seconds=acquisition_timeout,
            local_disposable_test=local,
        )


class AIPersistenceStartupError(RuntimeError):
    """A fixed, sanitized startup classification with no retained diagnostics."""

    def __init__(self, classification: PersistenceState) -> None:
        self.classification = classification
        super().__init__(classification)


class AIPersistenceRuntime:
    """Own the pool and Phase 18F coordinator without invoking either workflow."""

    def __init__(
        self,
        *,
        config: AIPersistenceRuntimeConfig,
        pool: _Pool | None,
        coordinator: PersistenceCoordinator | None,
        shadow_store: PostgresShadowAnalysisStore | None = None,
        state: PersistenceState,
        verifier: Callable[[_Pool, AIPersistenceRuntimeConfig], PersistenceState]
        | None = None,
    ) -> None:
        self.config = config
        self._pool = pool
        self.coordinator = coordinator
        self.shadow_store = shadow_store
        self._state = state
        self._verifier = verifier or _verify_pool
        self._closed = False
        self._lock = Lock()

    @property
    def state(self) -> PersistenceState:
        with self._lock:
            return self._state

    @property
    def required(self) -> bool:
        return self.config.mode == "required"

    def public_state(self) -> dict[str, object]:
        return {"status": self.state, "required": self.required}

    def refresh_readiness(self) -> PersistenceState:
        with self._lock:
            if self._closed:
                return "shutdown"
            if not self.required:
                return "disabled"
            pool = self._pool
        if pool is None:
            next_state: PersistenceState = "unavailable"
        else:
            next_state = self._verifier(pool, self.config)
        with self._lock:
            if not self._closed:
                self._state = next_state
            return self._state

    def close(self) -> None:
        pool: _Pool | None = None
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._state = "shutdown"
            pool = self._pool
            self._pool = None
            self.coordinator = None
            self.shadow_store = None
        if pool is not None:
            try:
                pool.close()
            except Exception:  # noqa: BLE001,S110 - shutdown never discloses diagnostics
                pass


def build_ai_persistence_runtime(
    settings: Settings,
    *,
    pool_factory: Any = ConnectionPool,
    verifier: Callable[[_Pool, AIPersistenceRuntimeConfig], PersistenceState]
    | None = None,
) -> AIPersistenceRuntime:
    verifier = verifier or _verify_pool
    config: AIPersistenceRuntimeConfig | None = None
    failure: PersistenceState | None = None
    try:
        config = AIPersistenceRuntimeConfig.from_settings(settings)
    except Exception:  # noqa: BLE001 - configuration values must not reach errors
        failure = "configuration_invalid"
    if failure is not None or config is None:
        _raise_clean(failure or "configuration_invalid")
    if config.mode == "disabled":
        return AIPersistenceRuntime(
            config=config, pool=None, coordinator=None, state="disabled"
        )

    pool: _Pool | None = None
    try:
        pool = pool_factory(
            conninfo=config.database_url,
            min_size=config.pool_min_size,
            max_size=config.pool_max_size,
            timeout=config.pool_acquisition_timeout_seconds,
            reconnect_timeout=0.0,
            open=False,
            name=APPLICATION_NAME,
            kwargs={
                "application_name": APPLICATION_NAME,
                "connect_timeout": math.ceil(config.connect_timeout_seconds),
            },
        )
        pool.open(wait=True, timeout=config.connect_timeout_seconds)
        failure = verifier(pool, config)
        if failure == "ready":

            def connection_factory():
                return pool.connection(timeout=config.pool_acquisition_timeout_seconds)

            adapter = PostgresAtomicPersistenceAdapter(connection_factory)
            return AIPersistenceRuntime(
                config=config,
                pool=pool,
                coordinator=PersistenceCoordinator(adapter),
                shadow_store=PostgresShadowAnalysisStore(connection_factory),
                state="ready",
                verifier=verifier,
            )
    except Exception:  # noqa: BLE001 - pool/driver diagnostics are untrusted
        failure = "unavailable"

    if pool is not None:
        try:
            pool.close()
        except Exception:  # noqa: BLE001,S110 - preserve sanitized startup result
            pass
    _raise_clean(failure or "unavailable")


def _verify_pool(pool: _Pool, config: AIPersistenceRuntimeConfig) -> PersistenceState:
    try:
        with pool.connection(
            timeout=config.pool_acquisition_timeout_seconds
        ) as connection:
            privileges = connection.execute(
                """
                SELECT
                    has_database_privilege(current_user, current_database(), 'CONNECT'),
                    has_schema_privilege(current_user, 'atlas_ai_persistence', 'USAGE'),
                    has_schema_privilege(current_user, 'atlas_ai_persistence', 'CREATE'),
                    has_table_privilege(current_user, 'atlas_ai_persistence.persistence_records', 'SELECT'),
                    has_table_privilege(current_user, 'atlas_ai_persistence.persistence_records', 'INSERT'),
                    has_table_privilege(current_user, 'atlas_ai_persistence.persistence_records', 'UPDATE'),
                    has_table_privilege(current_user, 'atlas_ai_persistence.persistence_records', 'DELETE'),
                    has_table_privilege(current_user, 'atlas_ai_persistence.persistence_records', 'TRUNCATE'),
                    has_column_privilege(current_user, 'public.atlas_ai_persistence_schema_migrations', 'filename', 'SELECT'),
                    has_column_privilege(current_user, 'public.atlas_ai_persistence_schema_migrations', 'sha256', 'SELECT'),
                    has_table_privilege(current_user, 'public.atlas_ai_persistence_schema_migrations', 'INSERT'),
                    has_table_privilege(current_user, 'public.atlas_ai_persistence_schema_migrations', 'UPDATE'),
                    has_table_privilege(current_user, 'public.atlas_ai_persistence_schema_migrations', 'DELETE'),
                    role.rolsuper, role.rolcreatedb, role.rolcreaterole,
                    role.rolreplication, role.rolbypassrls,
                    database.datdba = role.oid,
                    namespace.nspowner = role.oid,
                    pg_has_role(current_user, 'atlas_ai_persistence_owner', 'MEMBER')
                FROM pg_roles AS role
                JOIN pg_database AS database ON database.datname = current_database()
                JOIN pg_namespace AS namespace ON namespace.nspname = 'atlas_ai_persistence'
                WHERE role.rolname = current_user
                """
            ).fetchone()
            if privileges is None or tuple(bool(item) for item in privileges) != (
                True,
                True,
                False,
                True,
                True,
                False,
                False,
                False,
                True,
                True,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
            ):
                return "privilege_invalid"
            actual = dict(
                connection.execute(
                    "SELECT filename, sha256 FROM public.atlas_ai_persistence_schema_migrations ORDER BY filename"
                ).fetchall()
            )
            if actual != expected_ai_persistence_migrations():
                return "schema_mismatch"
            connection.execute("SELECT 1").fetchone()
    except errors.InsufficientPrivilege:
        return "privilege_invalid"
    except (psycopg.Error, OSError, TimeoutError):
        return "unavailable"
    except Exception:  # noqa: BLE001 - never expose metadata/driver diagnostics
        return "unavailable"
    return "ready"


def _validate_database_url(value: str, *, local_disposable_test: bool) -> None:
    if type(value) is not str or not value:
        raise ValueError
    parsed = conninfo_to_dict(value)
    host = parsed.get("host", "")
    user = parsed.get("user", "")
    database = parsed.get("dbname", "")
    password = parsed.get("password", "")
    sslmode = parsed.get("sslmode", "")
    if not all(type(item) is str and item for item in (host, user, database, password)):
        raise ValueError
    lowered_identity = f"{user} {database}".lower()
    if local_disposable_test:
        if host.lower() not in _LOCAL_HOSTS:
            raise ValueError
    else:
        if host.lower() in _LOCAL_HOSTS or sslmode != "verify-full":
            raise ValueError
        if any(term in lowered_identity for term in _PRIVILEGED_IDENTITY_TERMS):
            raise ValueError
        if any(term in lowered_identity for term in _DISPOSABLE_TERMS):
            raise ValueError


def _closed_bool(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError


def _bounded_float(value: str, *, maximum: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 < parsed <= maximum:
        raise ValueError
    return parsed


def _bounded_int(value: str, *, maximum: int) -> int:
    if not value.isascii() or not value.isdigit():
        raise ValueError
    parsed = int(value)
    if not 1 <= parsed <= maximum:
        raise ValueError
    return parsed


def _raise_clean(classification: PersistenceState) -> NoReturn:
    error = AIPersistenceStartupError(classification)
    error.__cause__ = None
    error.__context__ = None
    raise error from None
