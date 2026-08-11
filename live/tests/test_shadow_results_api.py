"""Contract and safety tests for GET /api/v1/trader-now/results."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from atlas.api.deps import (
    get_market_state_repository,
    get_repository,
    get_trader_now_application,
)
from atlas.api.security import require_trader_now_results_api_key
from atlas.api_models.trader_now import (
    AvailabilityResponse,
    StrategyDecisionResponse,
    StrategyResponse,
    project_trader_now_response,
)
from atlas.config import settings
from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.main import app
from atlas.market_engine.models import BarStatus, MarketState
from atlas.shadow_results import ProcessTelemetry
from atlas.shadow_results.service import build_shadow_results
from tests.test_trader_now_response import legacy_trader_now

PATH = "/api/v1/trader-now/results"
DEDICATED_KEY = "synthetic-results-only-key"
BROADER_API_KEY = "synthetic-broader-api-key"


class FakeApplication:
    def __init__(self):
        self.calls = []

    async def compose_latest(self, **kwargs):
        self.calls.append(kwargs)
        return legacy_trader_now()


@pytest.fixture
def results_client(client, monkeypatch):
    fake = FakeApplication()
    monkeypatch.setattr(settings, "trader_now_product", "MNQ")
    monkeypatch.setattr(settings, "trader_now_market_data_series_symbol", "MNQ1!")
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "")
    app.state.shadow_results_telemetry = ProcessTelemetry(
        reset_at=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
    )
    app.dependency_overrides[get_trader_now_application] = lambda: fake
    app.dependency_overrides[require_trader_now_results_api_key] = lambda: None
    try:
        yield client, fake
    finally:
        app.dependency_overrides.pop(get_trader_now_application, None)
        app.dependency_overrides.pop(require_trader_now_results_api_key, None)


@pytest.fixture
def authenticated_results_client(monkeypatch, repository, market_state_repository):
    fake = FakeApplication()
    monkeypatch.setattr(settings, "api_key", BROADER_API_KEY)
    monkeypatch.setattr(settings, "trader_now_results_api_key", DEDICATED_KEY)
    monkeypatch.setattr(settings, "trader_now_product", "MNQ")
    monkeypatch.setattr(settings, "trader_now_market_data_series_symbol", "MNQ1!")
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "")
    app.state.shadow_results_telemetry = ProcessTelemetry()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_market_state_repository] = lambda: (
        market_state_repository
    )
    app.dependency_overrides[get_trader_now_application] = lambda: fake
    try:
        yield TestClient(app), fake
    finally:
        app.dependency_overrides.clear()


def _market_state() -> MarketState:
    return MarketState(
        envelope=Event(
            event_type="bar_closed",
            source="tradingview",
            occurred_at=datetime(2026, 7, 27, 12, 5, tzinfo=timezone.utc),
            received_at=datetime(2026, 7, 27, 12, 5, 1, tzinfo=timezone.utc),
            event_id="mnq1:2026-07-27T12:05:00Z",
        ),
        schema_version="market_state.v1",
        symbol=Symbol("MNQ1!"),
        timeframe=Timeframe.M5,
        bar_status=BarStatus.CLOSED,
    )


async def _stored_signal(repository):
    async def forward():
        return True, 200, None

    await repository.claim_and_forward(
        "corr-public",
        {
            "correlation_id": "ignored",
            "direction": "long",
            "symbol": "MNQ",
        },
        '{"api_key":"must-not-leak","raw_payload":"private"}',
        forward,
    )
    await repository.update_pmt_diagnostics(
        "corr-public",
        {
            "url": "https://private.example",
            "response_body": "must-not-leak",
        },
    )
    await repository.add_ai_note(
        trade_correlation_id="corr-public",
        note_type="entry_score",
        model="secret-model-configuration",
        content="sensitive free-form AI content",
        error=None,
        score=73,
        score_label="watch",
    )


def test_empty_response_has_exact_allowlisted_schema_and_honest_states(
    results_client,
):
    response = results_client[0].get(PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "schema_version",
        "generated_at",
        "health",
        "shadow",
        "market_state",
        "stored_strategy_signals",
        "strategy",
        "risk",
        "decision",
        "ai_note",
        "telemetry",
        "execution_safety",
    }
    assert body["schema_version"] == "trader_now_results.v1"
    assert body["health"] == {
        "status": "healthy",
        "database_status": "healthy",
    }
    assert body["shadow"] == {
        "phase": "shadow_observation",
        "certification_status": "pending",
        "certification_basis": "not_recorded_by_runtime",
    }
    assert body["market_state"] == {"count": 0, "latest_timestamp": None}
    assert body["stored_strategy_signals"]["count"] == 0
    assert body["strategy"]["disposition"] is None
    assert body["strategy"]["direction"] is None
    assert body["strategy"]["semantic_label"] == (
        "opportunity_evaluation_not_recommendation"
    )
    assert body["risk"] == {"availability": "unavailable", "status": None}
    assert body["decision"] == {
        "availability": "not_implemented",
        "state": None,
    }
    assert body["ai_note"]["latest_status"] == "unavailable"
    assert body["ai_note"]["phase_18_ai_analysis"] == "not_integrated"
    assert body["execution_safety"]["pickmytrade_configured"] is False
    assert body["execution_safety"]["execution_disabled"] is True
    assert results_client[1].calls == [
        {
            "symbol": "MNQ",
            "timeframe": "5m",
            "strategy_id": "displacement_volume_context",
        }
    ]


def test_exact_database_counts_ai_allowlist_and_historical_execution_separation(
    results_client, repository, market_state_repository
):
    asyncio.run(_stored_signal(repository))
    asyncio.run(
        market_state_repository.ingest(
            _market_state(), raw_payload='{"secret":"market-raw"}'
        )
    )

    body = results_client[0].get(PATH).json()

    assert body["market_state"] == {
        "count": 1,
        "latest_timestamp": "2026-07-27T12:05:00Z",
    }
    assert body["stored_strategy_signals"] == {
        "count": 1,
        "latest_correlation_id": "corr-public",
        "latest_timestamp": body["stored_strategy_signals"]["latest_timestamp"],
    }
    assert body["ai_note"] == {
        "system": "legacy_claude_copilot",
        "phase_18_ai_analysis": "not_integrated",
        "stored_count": 1,
        "latest_status": "recorded",
        "latest_note_type": "entry_score",
        "latest_score": 73,
        "latest_score_label": "watch",
        "latest_correlation_id": "corr-public",
        "latest_timestamp": body["ai_note"]["latest_timestamp"],
        "free_text_exposed": False,
    }
    safety = body["execution_safety"]
    assert safety["historical_pickmytrade_forwarded_records"] == 1
    assert safety["historical_records_are_current_authority"] is False
    assert safety["pickmytrade_configured"] is False
    assert safety["execution_disabled"] is True
    serialized = response_text = results_client[0].get(PATH).text
    for forbidden in (
        "must-not-leak",
        "private.example",
        "secret-model-configuration",
        "sensitive free-form AI content",
        "market-raw",
        "api_key",
        "raw_payload",
        "pmt_relay_diagnostics",
    ):
        assert forbidden not in serialized
        assert forbidden not in response_text


def test_strategy_is_never_mislabeled_as_decision_or_recommendation(results_client):
    body = results_client[0].get(PATH).json()

    assert "recommendation" not in body["strategy"]
    assert "decision" not in body["strategy"]
    assert body["strategy"]["semantic_label"].endswith("not_recommendation")
    assert body["decision"]["availability"] == "not_implemented"
    assert "LONG" not in results_client[0].get(PATH).text
    assert "SHORT" not in results_client[0].get(PATH).text
    assert "NO TRADE" not in results_client[0].get(PATH).text


def test_candidate_remains_opportunity_evaluation_not_decision(
    repository, market_state_repository
):
    transport = project_trader_now_response(legacy_trader_now())
    candidate = StrategyDecisionResponse(
        occurred_at="2026-07-27T12:05:00Z",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        disposition="candidate",
        direction="long",
        setup_ids=("displacement",),
        reason_codes=("setup_evidence_aligned",),
        context_fingerprint="context-public",
        invalidation=None,
        stop=None,
        target=None,
        confidence=None,
    )
    transport = replace(
        transport,
        strategy=StrategyResponse(
            availability=AvailabilityResponse("available", ()),
            decisions=(candidate,),
        ),
    )

    result = asyncio.run(
        build_shadow_results(
            repository=repository,
            market_repository=market_state_repository,
            trader_now=transport,
            telemetry=ProcessTelemetry(),
            market_symbol="MNQ1!",
            market_timeframe="5m",
            pickmytrade_configured=False,
        )
    )

    assert result.strategy.disposition == "candidate"
    assert result.strategy.direction == "long"
    assert result.strategy.semantic_label == (
        "opportunity_evaluation_not_recommendation"
    )
    assert result.decision.availability == "not_implemented"
    assert result.decision.state is None


def test_process_counters_include_reset_metadata(results_client):
    telemetry = app.state.shadow_results_telemetry
    telemetry.observe_response(path="/api/v1/webhook", status_code=208)
    telemetry.observe_response(path="/api/v1/webhook", status_code=422)
    telemetry.observe_response(path="/api/v1/trades", status_code=401)
    telemetry.observe_response(path="/api/v1/trades", status_code=503)
    telemetry.observe_runtime_error()

    body = results_client[0].get(PATH).json()["telemetry"]

    assert body == {
        "scope": "current_process",
        "limitation": "resets_on_process_restart_or_deployment",
        "reset_at": "2026-07-27T12:00:00Z",
        "authentication_failures": 1,
        "http_5xx_responses": 1,
        "runtime_errors": 1,
        "ingestion": {
            "duplicate_webhooks": 1,
            "rejected_webhooks": 1,
        },
    }


def test_endpoint_requires_server_side_bearer_auth(
    monkeypatch, repository, market_state_repository
):
    fake = FakeApplication()
    monkeypatch.setattr(settings, "api_key", "server-only-secret")
    app.dependency_overrides[get_trader_now_application] = lambda: fake
    app.dependency_overrides[
        __import__("atlas.api.deps", fromlist=["get_repository"]).get_repository
    ] = lambda: repository
    app.dependency_overrides[
        __import__(
            "atlas.api.deps", fromlist=["get_market_state_repository"]
        ).get_market_state_repository
    ] = lambda: market_state_repository
    try:
        response = TestClient(app).get(PATH)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "server-only-secret" not in response.text
    assert fake.calls == []


def test_missing_dedicated_environment_variable_fails_closed(
    authenticated_results_client, monkeypatch
):
    monkeypatch.setattr(settings, "trader_now_results_api_key", "")

    response = authenticated_results_client[0].get(
        PATH, headers={"Authorization": f"Bearer {DEDICATED_KEY}"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "missing or invalid API key"}
    assert authenticated_results_client[1].calls == []


def test_missing_authorization_fails_closed(authenticated_results_client):
    response = authenticated_results_client[0].get(PATH)

    assert response.status_code == 401
    assert response.json() == {"detail": "missing or invalid API key"}
    assert authenticated_results_client[1].calls == []


def test_invalid_dedicated_credential_fails_closed(authenticated_results_client):
    response = authenticated_results_client[0].get(
        PATH, headers={"Authorization": "Bearer synthetic-invalid-key"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "missing or invalid API key"}
    assert authenticated_results_client[1].calls == []


def test_valid_dedicated_credential_is_accepted(authenticated_results_client):
    response = authenticated_results_client[0].get(
        PATH, headers={"Authorization": f"Bearer {DEDICATED_KEY}"}
    )

    assert response.status_code == 200
    assert authenticated_results_client[1].calls


def test_broader_api_key_cannot_access_results(authenticated_results_client):
    response = authenticated_results_client[0].get(
        PATH, headers={"Authorization": f"Bearer {BROADER_API_KEY}"}
    )

    assert response.status_code == 401
    assert authenticated_results_client[1].calls == []


def test_other_protected_routes_still_use_broader_api_key(authenticated_results_client):
    response = authenticated_results_client[0].get(
        "/api/v1/trades",
        headers={"Authorization": f"Bearer {BROADER_API_KEY}"},
    )

    assert response.status_code == 200


def test_auth_failure_does_not_leak_credentials(authenticated_results_client, caplog):
    presented = "synthetic-presented-secret"
    response = authenticated_results_client[0].get(
        PATH, headers={"Authorization": f"Bearer {presented}"}
    )

    assert response.status_code == 401
    assert presented not in response.text
    assert DEDICATED_KEY not in response.text
    assert BROADER_API_KEY not in response.text
    assert presented not in caplog.text
    assert DEDICATED_KEY not in caplog.text
    assert BROADER_API_KEY not in caplog.text


def test_openapi_exposes_only_the_shadow_results_contract():
    app.openapi_schema = None
    schema = app.openapi()
    operation = schema["paths"][PATH]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ShadowResultsResponse"
    }
