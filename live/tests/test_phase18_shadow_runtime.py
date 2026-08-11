"""Focused local-only tests for the Phase 18 Shadow runtime attachment."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from atlas.api.security import require_trader_now_results_api_key
from atlas.api.trader_now_deps import get_trader_now_application
from atlas.config import settings
from atlas.main import app
from atlas.manual_ai_runtime import MODEL_ID
from atlas.shadow_ai_runtime import ShadowAnalysisRuntime, build_shadow_analysis_runtime
from atlas.shadow_results import ProcessTelemetry
from atlas_ai_persistence_postgres import ShadowAnalysisRecord
from atlas_ai_analysis import GeneratorIdentity
from tests.test_trader_now_response import legacy_trader_now

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "specs" / "trader_now_snapshot" / "v1" / "golden"


def _snapshot():
    return json.loads(
        (GOLDEN / "complete-current-candidate.canonical.json").read_text(
            encoding="utf-8"
        )
    )


class _Store:
    def __init__(self) -> None:
        self.claims: set[str] = set()

    def claim_snapshot(self, snapshot_id: str) -> bool:
        if snapshot_id in self.claims:
            return False
        self.claims.add(snapshot_id)
        return True


class _Provider:
    def __init__(self, outcome=object(), failure: Exception | None = None) -> None:
        self.outcome = outcome
        self.failure = failure
        self.calls = 0

    def run(self, evaluation):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.outcome


class _Persistence:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.values = []

    def persist(self, outcome):
        self.values.append(outcome)
        if self.failure is not None:
            raise self.failure


def _runtime(*, enabled=True, provider=None, persistence=None, store=None):
    return ShadowAnalysisRuntime(
        enabled=enabled,
        provider_orchestrator=provider,
        persistence=persistence,
        store=store,
        identity_factory=lambda: "019c1234-0000-7000-8000-000000000001",
        clock=lambda: "2026-08-10T10:00:00.000000Z",
    )


def test_disabled_runtime_has_zero_provider_calls_and_persistence_writes():
    provider, persistence, store = _Provider(), _Persistence(), _Store()
    runtime = _runtime(
        enabled=False, provider=provider, persistence=persistence, store=store
    )
    runtime.process_snapshot(_snapshot())
    runtime.close()
    assert provider.calls == 0
    assert persistence.values == []
    assert store.claims == set()


def test_production_factory_is_default_disabled_and_composes_without_invoking_provider():
    disabled = build_shadow_analysis_runtime(
        SimpleNamespace(atlas_ai_shadow_enabled="false"),
        persistence_runtime=SimpleNamespace(state="disabled"),
    )
    assert disabled.enabled is False
    disabled.close()

    class Adapter:
        identity = GeneratorIdentity("openai", MODEL_ID)
        calls = 0

        def invoke(self, request):
            self.calls += 1
            raise AssertionError("factory must not invoke the provider")

    adapter = Adapter()
    settings_object = SimpleNamespace(
        atlas_ai_shadow_enabled="true",
        atlas_ai_provider_enabled="true",
        atlas_ai_provider_api_key="synthetic-local-only",
        atlas_ai_provider_model=MODEL_ID,
        atlas_ai_provider_timeout_seconds="30",
        atlas_ai_provider_max_request_bytes="65536",
        atlas_ai_provider_max_response_bytes="131072",
        atlas_ai_provider_max_output_tokens="4096",
        atlas_ai_provider_max_estimated_cost="0.12",
        environment="production",
    )
    runtime = build_shadow_analysis_runtime(
        settings_object,
        persistence_runtime=SimpleNamespace(
            state="ready", coordinator=_Persistence(), shadow_store=_Store()
        ),
        adapter_factory=lambda **kwargs: adapter,
        clock=lambda: datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
    )
    assert runtime.enabled is True
    assert adapter.calls == 0
    runtime.close()


def test_duplicate_snapshot_has_one_provider_attempt_and_one_persistence_write():
    provider, persistence, store = _Provider(), _Persistence(), _Store()
    runtime = _runtime(provider=provider, persistence=persistence, store=store)
    runtime.process_snapshot(_snapshot())
    runtime.process_snapshot(_snapshot())
    runtime.close()
    assert provider.calls == 1
    assert persistence.values == [provider.outcome]
    assert len(store.claims) == 1


@pytest.mark.parametrize("failure_at", ["provider", "persistence"])
def test_worker_failures_are_fully_contained(failure_at):
    provider = _Provider(
        failure=RuntimeError("provider detail") if failure_at == "provider" else None
    )
    persistence = _Persistence(
        failure=RuntimeError("database detail") if failure_at == "persistence" else None
    )
    runtime = _runtime(provider=provider, persistence=persistence, store=_Store())
    assert runtime.process_snapshot(_snapshot()) is None
    runtime.close()
    assert provider.calls == 1


def test_dedicated_shadow_results_authentication_is_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "trader_now_results_api_key", "results-key")
    require_trader_now_results_api_key(None, "Bearer results-key")
    with pytest.raises(HTTPException):
        require_trader_now_results_api_key(None, "Bearer broader-key")


def test_shadow_results_endpoint_preserves_frozen_v1_contract(client, monkeypatch):
    class Application:
        async def compose_latest(self, **kwargs):
            return legacy_trader_now()

    monkeypatch.setattr(settings, "trader_now_product", "MNQ")
    monkeypatch.setattr(settings, "trader_now_market_data_series_symbol", "MNQ1!")
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "")
    app.state.shadow_results_telemetry = ProcessTelemetry()
    app.state.ai_persistence_runtime = type(
        "Runtime", (), {"state": "disabled", "shadow_store": None}
    )()
    app.dependency_overrides[get_trader_now_application] = Application
    app.dependency_overrides[require_trader_now_results_api_key] = lambda: None

    response = client.get("/api/v1/trader-now/results")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "trader_now_results.v1"
    assert "phase_18_analysis" not in body
    assert body["execution_safety"]["execution_disabled"] is True


def test_phase18_read_endpoints_remain_sanitized_and_separate(client):
    record = ShadowAnalysisRecord(
        snapshot_id="019c1234-0000-7000-8000-000000000010",
        outcome="completed",
        recorded_at="2026-08-10T10:00:00.000000Z",
        summary="Bounded summary",
        citations=("snapshot:/evidence/risk",),
        limitations=("No prediction",),
        reason=None,
        analysis_audit_id="019c1234-0000-7000-8000-000000000011",
        analysis_output_id="019c1234-0000-7000-8000-000000000012",
    )

    class ReadStore:
        def latest(self):
            return record

        def history(self, *, limit):
            assert limit in {20, 100}
            return (record,)

    app.state.ai_persistence_runtime = SimpleNamespace(
        state="ready", shadow_store=ReadStore()
    )
    latest = client.get("/api/v1/ai-analysis/latest")
    history = client.get("/api/v1/ai-analysis/history?limit=100")

    assert latest.status_code == 200
    assert history.status_code == 200
    assert latest.json()["latest"]["summary"] == "Bounded summary"
    assert history.json()["history"][0]["state"] == "completed"
    serialized = latest.text + history.text
    assert "prompt" not in serialized
    assert "raw_provider_response" not in serialized
