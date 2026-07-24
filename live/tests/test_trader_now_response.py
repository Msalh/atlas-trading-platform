"""Transport-contract tests for the allowlisted TraderNow response."""

from dataclasses import FrozenInstanceError, is_dataclass, replace
from decimal import Decimal

import pytest

from atlas.api_models import (
    TRADER_NOW_RESPONSE_SCHEMA_VERSION,
    project_trader_now_response,
    trader_now_response_to_dict,
    trader_now_response_to_json,
)
from atlas.risk_assessment.models import (
    AssessmentStatus,
    FreshnessStatus,
    ReconciliationStatus,
    RiskReason,
    SizingMode,
)
from atlas.risk_projection.models import (
    RISK_PROJECTION_SCHEMA_VERSION,
    RiskProjection,
)
from atlas.trader_now.models import (
    Availability,
    AvailabilityStatus,
    DecisionNotImplemented,
    TraderNow,
    TraderNowIdentity,
    Trust,
    TrustStatus,
)
from tests.test_trader_now_application import NOW, application


async def composed():
    service, _, _, _ = application()
    return await service.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )


def legacy_trader_now() -> TraderNow:
    return TraderNow(
        snapshot=None,
        identity=TraderNowIdentity(
            product="MNQ",
            symbol="MNQ",
            timeframe="5m",
            strategy_id="displacement_volume_context",
            strategy_version="1.0.0",
        ),
        trust=Trust(TrustStatus.UNAVAILABLE, "freshness.v1", ("no_data",)),
        availability={
            "market": Availability(AvailabilityStatus.NO_DATA, ("no_data",)),
            "rules": Availability(AvailabilityStatus.UNAVAILABLE, ("no_data",)),
            "setups": Availability(AvailabilityStatus.UNAVAILABLE, ("no_data",)),
            "context": Availability(AvailabilityStatus.UNAVAILABLE, ("no_data",)),
            "interpretations": Availability(
                AvailabilityStatus.UNAVAILABLE, ("no_data",)
            ),
            "strategy": Availability(AvailabilityStatus.UNAVAILABLE, ("no_data",)),
        },
        decision=DecisionNotImplemented(),
    )


def risk_projection() -> RiskProjection:
    return RiskProjection(
        schema_version=RISK_PROJECTION_SCHEMA_VERSION,
        assessment_id="assessment-public",
        policy_id="policy-1",
        policy_version="1.0",
        assessed_at=NOW,
        candidate_at=NOW,
        status=AssessmentStatus.APPROVED,
        primary_reason=None,
        contributing_reasons=(RiskReason.MARGIN_UNKNOWN,),
        sizing_mode=SizingMode.RISK_BASED,
        requested_quantity=2,
        maximum_approved_quantity=3,
        approved_quantity=2,
        risk_ticks=16,
        risk_dollars_per_contract=Decimal("12.340"),
        approved_total_candidate_risk=Decimal("24.680"),
        remaining_daily_risk_capacity=Decimal("975.320"),
        remaining_drawdown_capacity=Decimal("1975.320"),
        exposure_before=0,
        exposure_after=2,
        account_freshness=FreshnessStatus.CURRENT,
        position_freshness=FreshnessStatus.CURRENT,
        candidate_freshness=FreshnessStatus.CURRENT,
        reconciliation_status=ReconciliationStatus.RECONCILED,
        has_delayed_data=False,
        source_summary=("internal-account-snapshot",),
    )


@pytest.mark.asyncio
async def test_complete_composition_projects_every_public_analysis_section():
    response = project_trader_now_response(await composed())

    assert response.schema_version == "trader_now_response.v2"
    assert response.domain_schema_version == "trader_now.v2"
    assert response.market.economic_instrument.symbol == "MNQ"
    assert response.market.market_data_series.symbol == "MNQ1!"
    assert response.market.market_data_series.provider == "tradingview"
    assert response.market.market_data_series.series_type == "continuous"
    assert response.market.listed_instrument is None
    assert response.market.latest_bar is not None
    assert response.source_trust is not None
    assert response.rules.facts
    assert response.setups.setups
    assert response.context.data is not None
    assert response.interpretations.interpretations
    assert response.strategy.decisions
    assert response.decision.availability == "not_implemented"
    assert response.decision.state is None


@pytest.mark.asyncio
async def test_serialization_is_deterministic_and_schema_stable():
    domain = await composed()
    first = project_trader_now_response(domain)
    second = project_trader_now_response(domain)

    assert first == second
    assert trader_now_response_to_json(first) == trader_now_response_to_json(second)
    assert tuple(trader_now_response_to_dict(first)) == (
        "schema_version",
        "domain_schema_version",
        "snapshot_id",
        "evaluated_at",
        "input_snapshot_at",
        "identity",
        "trust",
        "availability",
        "market",
        "source_trust",
        "rules",
        "setups",
        "context",
        "interpretations",
        "strategy",
        "risk",
        "decision",
    )
    assert TRADER_NOW_RESPONSE_SCHEMA_VERSION == "trader_now_response.v2"


@pytest.mark.asyncio
async def test_datetime_enum_tuple_and_mapping_serialization_are_explicit():
    body = trader_now_response_to_dict(project_trader_now_response(await composed()))

    assert body["evaluated_at"] == "2026-07-24T18:00:00.000000Z"
    assert body["source_trust"]["freshness"]["status"] == "current"
    assert isinstance(body["strategy"]["decisions"], list)
    assert isinstance(body["availability"], dict)
    assert body["availability"]["strategy"]["status"] == "available"


@pytest.mark.asyncio
async def test_unavailable_sections_are_present_and_never_silently_omitted():
    service, _, _, _ = application(rows=[])
    domain = await service.compose_latest(
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        as_of=NOW,
    )
    body = trader_now_response_to_dict(project_trader_now_response(domain))

    assert body["market"]["availability"]["status"] == "no_data"
    assert body["market"]["latest_bar"] is None
    assert body["rules"]["availability"]["status"] == "unavailable"
    assert body["rules"]["facts"] == []
    assert body["setups"]["setups"] == []
    assert body["context"]["data"] is None
    assert body["interpretations"]["interpretations"] == []
    assert body["strategy"]["decisions"] == []
    assert "rules" in body and "strategy" in body


def test_minimal_domain_contract_projects_to_explicit_unavailable_sections():
    body = trader_now_response_to_dict(project_trader_now_response(legacy_trader_now()))

    assert body["schema_version"] == "trader_now_response.v2"
    assert body["domain_schema_version"] == "trader_now.v2"
    assert body["source_trust"] is None
    assert body["market"]["availability"]["status"] == "no_data"
    assert body["market"]["market_data_series"] is None
    assert body["market"]["listed_instrument"] is None
    assert "resolved_contract" not in body["market"]
    assert body["rules"]["facts"] == []
    assert body["strategy"]["decisions"] == []


@pytest.mark.asyncio
async def test_projection_is_deeply_immutable_and_uses_no_domain_objects():
    response = project_trader_now_response(await composed())

    with pytest.raises(FrozenInstanceError):
        response.schema_version = "changed"
    with pytest.raises(FrozenInstanceError):
        response.market.bar_count = 0
    assert isinstance(response.rules.facts, tuple)

    def visit(value):
        if is_dataclass(value):
            assert type(value).__module__ == "atlas.api_models.trader_now"
            for field_name in value.__dataclass_fields__:
                visit(getattr(value, field_name))
        elif isinstance(value, tuple):
            for item in value:
                visit(item)

    visit(response)


@pytest.mark.asyncio
async def test_allowlist_blocks_internal_and_sensitive_fields():
    body = trader_now_response_to_dict(project_trader_now_response(await composed()))
    serialized = trader_now_response_to_json(
        project_trader_now_response(await composed())
    )

    forbidden = {
        "states",
        "source_events",
        "resolution_owner",
        "repository",
        "dependencies",
        "account",
        "positions",
        "candidate",
        "risk_policy",
        "source_summary",
        "webhook",
        "broker",
    }

    def keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)

    assert forbidden.isdisjoint(keys(body))
    assert "internal-account-snapshot" not in serialized


@pytest.mark.asyncio
async def test_optional_risk_decimal_and_enum_serialization():
    domain = replace(await composed(), risk=risk_projection())
    body = trader_now_response_to_dict(project_trader_now_response(domain))

    assert body["risk"]["risk_dollars_per_contract"] == "12.340"
    assert body["risk"]["approved_total_candidate_risk"] == "24.680"
    assert body["risk"]["status"] == "approved"
    assert body["risk"]["contributing_reasons"] == ["risk.margin.unknown"]
    assert body["risk"]["reconciliation_status"] == "reconciled"
    assert "source_summary" not in body["risk"]
