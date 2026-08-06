"""Part 4A authenticated read-only TraderNow route tests."""

from dataclasses import replace

import pytest
from atlas.api.deps import get_trader_now_application
from atlas.api.security import require_api_key
from atlas.api.v1.trader_now import get_manual_ai_explanation_service
from atlas.application import InvalidCompositionTimeError
from atlas.config import settings
from atlas.main import app
from atlas.manual_ai_advisory import ManualAIExplanation
from atlas.trader_now.errors import RiskCompositionAlignmentError
from atlas.trader_now.models import Availability, AvailabilityStatus
from fastapi.testclient import TestClient

from tests.test_trader_now_response import legacy_trader_now

PATH = (
    "/api/v1/trader-now?symbol=MNQ&timeframe=5m&strategy_id=displacement_volume_context"
)
MANUAL_PATH = "/api/v1/trader-now/manual-advisory"
MANUAL_BODY = {
    "symbol": "MNQ",
    "timeframe": "5m",
    "strategy_id": "displacement_volume_context",
}


class FakeApplication:
    def __init__(self, *, result=None, error=None):
        self.result = result or legacy_trader_now()
        self.error = error
        self.calls = []

    async def compose_latest(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def route_client():
    fake = FakeApplication()
    app.dependency_overrides[get_trader_now_application] = lambda: fake
    app.dependency_overrides[require_api_key] = lambda: None
    try:
        yield TestClient(app), fake
    finally:
        app.dependency_overrides.pop(get_trader_now_application, None)
        app.dependency_overrides.pop(require_api_key, None)


def test_authenticated_success_calls_facade_once_with_exact_query_values(route_client):
    client, fake = route_client

    response = client.get(PATH)

    assert response.status_code == 200
    assert fake.calls == [
        {
            "symbol": "MNQ",
            "timeframe": "5m",
            "strategy_id": "displacement_volume_context",
        }
    ]
    assert response.json()["schema_version"] == "trader_now_response.v2"
    assert response.json()["domain_schema_version"] == "trader_now.v2"


def test_manual_advisory_is_one_composition_and_default_ai_is_unavailable(route_client):
    client, fake = route_client
    response = client.post(MANUAL_PATH, json=MANUAL_BODY)
    assert response.status_code == 200
    assert fake.calls == [MANUAL_BODY]
    assert response.json()["schema_version"] == "manual_advisory_response.v1"
    assert response.json()["trader_now"]["schema_version"] == "trader_now_response.v2"
    assert response.json()["ai_explanation"] == {
        "status": "unavailable",
        "summary": None,
        "claims": [],
        "limitations": [],
        "reason": "analysis_unavailable",
    }


def test_manual_advisory_projects_only_sanitized_validated_explanation(route_client):
    client, _ = route_client

    class FakeAI:
        def explain(self, _response):
            return ManualAIExplanation(
                status="available",
                summary="Grounded summary.",
                claims=({"claim_id": "claim-1", "kind": "explanation", "text": "Grounded claim.", "citations": ("/evidence/trust",)},),
                limitations=("advisory_only",),
            )

    app.dependency_overrides[get_manual_ai_explanation_service] = lambda: FakeAI()
    try:
        response = client.post(MANUAL_PATH, json=MANUAL_BODY)
    finally:
        app.dependency_overrides.pop(get_manual_ai_explanation_service, None)
    assert response.status_code == 200
    assert response.json()["ai_explanation"]["summary"] == "Grounded summary."
    assert "credential" not in response.text.lower()


@pytest.mark.parametrize(
    "body",
    [
        {**MANUAL_BODY, "symbol": "ES"},
        {**MANUAL_BODY, "timeframe": "1m"},
        {**MANUAL_BODY, "strategy_id": "other"},
        {**MANUAL_BODY, "prompt": "override"},
    ],
)
def test_manual_advisory_rejects_non_allowlisted_identity_or_fields(route_client, body):
    client, fake = route_client
    response = client.post(MANUAL_PATH, json=body)
    assert response.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-key"])
def test_missing_or_invalid_credentials_are_rejected(monkeypatch, authorization):
    fake = FakeApplication()
    monkeypatch.setattr(settings, "api_key", "route-secret")
    app.dependency_overrides[get_trader_now_application] = lambda: fake
    headers = {"Authorization": authorization} if authorization else {}
    try:
        response = TestClient(app).get(PATH, headers=headers)
    finally:
        app.dependency_overrides.pop(get_trader_now_application, None)

    assert response.status_code == 401
    assert "route-secret" not in response.text
    assert fake.calls == []


def test_valid_existing_bearer_credential_executes_route(monkeypatch):
    fake = FakeApplication()
    monkeypatch.setattr(settings, "api_key", "route-secret")
    app.dependency_overrides[get_trader_now_application] = lambda: fake
    try:
        response = TestClient(app).get(
            PATH,
            headers={"Authorization": "Bearer route-secret"},
        )
    finally:
        app.dependency_overrides.pop(get_trader_now_application, None)

    assert response.status_code == 200
    assert len(fake.calls) == 1


@pytest.mark.parametrize("missing", ["symbol", "timeframe", "strategy_id"])
def test_required_query_parameters_have_no_defaults(route_client, missing):
    client, fake = route_client
    params = {
        "symbol": "MNQ",
        "timeframe": "5m",
        "strategy_id": "displacement_volume_context",
    }
    params.pop(missing)

    response = client.get("/api/v1/trader-now", params=params)

    assert response.status_code == 422
    assert fake.calls == []


def test_unsupported_identity_maps_to_safe_422(route_client):
    client, fake = route_client
    from atlas.trader_now.errors import UnsupportedTraderNowIdentityError

    fake.error = UnsupportedTraderNowIdentityError(
        "strategy_id", "unknown", "displacement_volume_context"
    )

    response = client.get(PATH.replace("displacement_volume_context", "unknown"))

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "unsupported_trader_now_identity",
            "field": "strategy_id",
            "supplied": "unknown",
            "supported": "displacement_volume_context",
        }
    }


def test_explicit_unavailable_result_is_http_200(route_client):
    client, _ = route_client

    response = client.get(PATH)
    body = response.json()

    assert response.status_code == 200
    assert body["market"]["availability"]["status"] == "no_data"
    assert body["rules"]["availability"]["status"] == "unavailable"
    assert body["strategy"]["decisions"] == []
    assert body["risk"] is None


def test_insufficient_data_result_is_http_200(route_client):
    client, fake = route_client
    fake.result = replace(
        legacy_trader_now(),
        availability={
            "market": Availability(AvailabilityStatus.AVAILABLE),
            "market_history": Availability(
                AvailabilityStatus.INSUFFICIENT_DATA,
                ("insufficient_history",),
            ),
            "rules": Availability(
                AvailabilityStatus.INSUFFICIENT_DATA,
                ("insufficient_history",),
            ),
            "setups": Availability(
                AvailabilityStatus.INSUFFICIENT_DATA,
                ("insufficient_history",),
            ),
            "context": Availability(
                AvailabilityStatus.INSUFFICIENT_DATA,
                ("insufficient_history",),
            ),
            "interpretations": Availability(
                AvailabilityStatus.UNAVAILABLE,
                ("dependency_unavailable",),
            ),
            "strategy": Availability(
                AvailabilityStatus.UNAVAILABLE,
                ("dependency_unavailable",),
            ),
        },
    )

    response = client.get(PATH)

    assert response.status_code == 200
    assert response.json()["availability"]["market_history"]["status"] == (
        "insufficient_data"
    )
    assert response.json()["context"]["data"] is None


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            InvalidCompositionTimeError("secret clock detail"),
            "trader_now_composition_invalid",
        ),
        (
            RiskCompositionAlignmentError(0),
            "trader_now_composition_failed",
        ),
        (ValueError("secret transport detail"), "trader_now_projection_failed"),
    ],
)
def test_known_structural_errors_map_safely(route_client, error, code):
    client, fake = route_client
    fake.error = error

    response = client.get(PATH)

    assert response.status_code == 500
    assert response.json() == {"detail": {"code": code}}
    assert "secret" not in response.text
    assert type(error).__name__ not in response.text


def test_unexpected_error_does_not_leak_internal_details(route_client):
    client, fake = route_client
    fake.error = RuntimeError(
        "postgresql://user:secret@internal/repository C:\\private\\file.py"
    )

    response = client.get(PATH)

    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "internal_server_error"}}
    assert "secret" not in response.text
    assert "postgresql" not in response.text
    assert "private" not in response.text


def test_response_contains_only_transport_data_not_domain_objects(route_client):
    client, _ = route_client

    body = client.get(PATH).json()

    assert isinstance(body, dict)
    assert "TraderNow(" not in str(body)
    assert "MappingProxyType" not in str(body)
    assert "states" not in body["market"]
    assert "source_events" not in body["market"]


def test_openapi_uses_the_single_part3_response_contract():
    app.openapi_schema = None
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/trader-now"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TraderNowResponse"
    }
    response_schema = schema["components"]["schemas"]["TraderNowResponse"]
    assert response_schema["properties"]["schema_version"]["type"] == "string"
    availability_schema = response_schema["properties"]["availability"]
    assert availability_schema["type"] == "object"


def test_route_module_has_no_write_or_side_effect_dependencies():
    source = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "atlas"
        / "api"
        / "v1"
        / "trader_now.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "PickMyTrade",
        "anthropic",
        "webhook",
        "BackgroundTasks",
        "Postgres",
        "assess_candidate_risk",
        "RuleComposer",
        "SetupComposer",
        "StrategyComposer",
    ):
        assert forbidden not in source
