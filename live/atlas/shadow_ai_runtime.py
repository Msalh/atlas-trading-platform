"""Default-disabled, non-blocking Phase 18 Shadow analysis composition."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Protocol

from atlas.manual_ai_runtime import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_DEADLINE_SECONDS,
    MAX_INPUT_TOKENS,
    MODEL_ID,
    PRICING_REFERENCE_ID,
    READ_TIMEOUT_SECONDS,
    ManualAIProviderConfig,
    _RuntimeCostPolicy,
    _approved_pricing,
    _estimate_input_tokens,
    _timestamp,
)
from atlas_ai_analysis import AnalysisInputIdentity, GeneratorIdentity
from atlas_ai_orchestration import DeterministicPromptBuilder, ProviderOrchestrator
from atlas_ai_orchestration.openai_adapter import (
    OpenAIAdapterPolicy,
    OpenAIProviderAdapter,
)
from atlas_ai_persistence import PersistenceCoordinator
from atlas_ai_service import AIServiceOrchestrator, EvidenceClient
from atlas_snapshot import parse, serialize
from atlas_snapshot_capture import generate_uuid7


class ShadowAnalysisStore(Protocol):
    def claim_snapshot(self, snapshot_id: str) -> bool: ...


class _SnapshotTransport:
    def __init__(self, snapshot_id: str, payload: bytes) -> None:
        self._snapshot_id = snapshot_id
        self._payload = payload

    def fetch_snapshot(self, snapshot_id: str) -> bytes:
        if snapshot_id != self._snapshot_id:
            raise LookupError
        return self._payload


class ShadowAnalysisRuntime:
    """Schedules one isolated analysis task for each newly claimed Snapshot."""

    def __init__(
        self,
        *,
        enabled: bool,
        provider_orchestrator: ProviderOrchestrator | None = None,
        persistence: PersistenceCoordinator | None = None,
        store: ShadowAnalysisStore | None = None,
        identity_factory: Callable[[], str] | None = None,
        clock: Callable[[], str] | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.enabled = enabled
        self._provider_orchestrator = provider_orchestrator
        self._persistence = persistence
        self._store = store
        self._identity_factory = identity_factory or (
            lambda: generate_uuid7(now=lambda: datetime.now(timezone.utc))
        )
        self._clock = clock or (
            lambda: (
                datetime.now(timezone.utc)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
        )
        self._executor = (
            executor
            or ThreadPoolExecutor(max_workers=1, thread_name_prefix="atlas-shadow-ai")
            if enabled
            else None
        )
        self._futures: set[Future[None]] = set()

    def submit(self, snapshot: Mapping[str, Any]) -> None:
        """Return immediately; all failures are contained in the worker."""
        if not self.enabled or self._executor is None:
            return
        try:
            future = self._executor.submit(self._process_snapshot, snapshot)
        except Exception:
            return
        self._futures.add(future)
        future.add_done_callback(self._futures.discard)

    def process_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        """Synchronous test/worker entry with the same fail-closed behavior."""
        if not self.enabled:
            return
        try:
            self._process_snapshot(snapshot)
        except Exception:
            return

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)

    def _process_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        try:
            self._process_payload(serialize(snapshot))
        except Exception:
            return

    def _process_payload(self, payload: bytes) -> None:
        try:
            snapshot = parse(payload)
            snapshot_id = snapshot["snapshot_id"]
            if (
                not isinstance(snapshot_id, str)
                or self._store is None
                or self._provider_orchestrator is None
                or self._persistence is None
            ):
                return
            if not self._store.claim_snapshot(snapshot_id):
                return
            evaluation = AIServiceOrchestrator(
                EvidenceClient(_SnapshotTransport(snapshot_id, payload))
            ).evaluate(
                snapshot_id,
                "strategy_explanation",
                AnalysisInputIdentity(self._identity_factory(), self._clock()),
            )
            outcome = self._provider_orchestrator.run(evaluation)
            self._persistence.persist(outcome)
        except Exception:
            return


def build_shadow_analysis_runtime(
    settings: Any,
    *,
    persistence_runtime: Any,
    adapter_factory: Any = OpenAIProviderAdapter,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ShadowAnalysisRuntime:
    """Compose existing 18C-18F pieces only after every gate is explicit."""
    if getattr(settings, "atlas_ai_shadow_enabled", "false") != "true":
        return ShadowAnalysisRuntime(enabled=False)
    if getattr(persistence_runtime, "state", None) != "ready":
        return ShadowAnalysisRuntime(enabled=False)
    persistence = getattr(persistence_runtime, "coordinator", None)
    store = getattr(persistence_runtime, "shadow_store", None)
    if persistence is None or store is None:
        return ShadowAnalysisRuntime(enabled=False)
    try:
        config = ManualAIProviderConfig.from_settings(settings, allow_production=True)
        if config is None or not _approved_pricing(
            clock(), config.max_estimated_cost_usd
        ):
            return ShadowAnalysisRuntime(enabled=False)
        credential = config.api_key
        provider = adapter_factory(
            credential_provider=lambda: credential,
            input_token_estimator=_estimate_input_tokens,
            utc_now=clock,
            policy=OpenAIAdapterPolicy(
                enabled=True,
                model_id=config.model_id,
                approved_model_ids=frozenset({MODEL_ID}),
                pricing_reference_id=PRICING_REFERENCE_ID,
                max_request_bytes=config.max_request_bytes,
                max_response_bytes=config.max_response_bytes,
                max_input_tokens=MAX_INPUT_TOKENS,
                max_output_tokens=config.max_output_tokens,
                connect_timeout_seconds=min(
                    CONNECT_TIMEOUT_SECONDS, config.deadline_seconds
                ),
                read_timeout_seconds=min(READ_TIMEOUT_SECONDS, config.deadline_seconds),
                deadline_seconds=min(MAX_DEADLINE_SECONDS, config.deadline_seconds),
                max_estimated_cost_usd=config.max_estimated_cost_usd,
            ),
        )

        def identifier() -> str:
            return generate_uuid7(now=clock)

        orchestrator = ProviderOrchestrator(
            prompt_builder=DeterministicPromptBuilder(identifier),
            provider=provider,
            cost_policy=_RuntimeCostPolicy(),
            audit_id_factory=identifier,
            clock=lambda: _timestamp(clock),
            generator=GeneratorIdentity("openai", MODEL_ID),
        )
        return ShadowAnalysisRuntime(
            enabled=True,
            provider_orchestrator=orchestrator,
            persistence=persistence,
            store=store,
            identity_factory=identifier,
            clock=lambda: _timestamp(clock),
        )
    except Exception:
        return ShadowAnalysisRuntime(enabled=False)
