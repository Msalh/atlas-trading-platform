"""Unit tests for the Sprint 12B Part 1 TraderNow contract skeleton."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from atlas.trader_now.models import (
    SCHEMA_VERSION,
    Availability,
    AvailabilityStatus,
    DecisionNotImplemented,
    EconomicInstrument,
    ListedInstrument,
    MarketDataProvider,
    MarketDataSeries,
    MarketDataSeriesType,
    SnapshotIdentity,
    TraderNow,
    TraderNowIdentity,
    Trust,
    TrustStatus,
)


def _identity() -> TraderNowIdentity:
    return TraderNowIdentity(
        product="MNQ",
        symbol="MNQ",
        timeframe="5m",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
    )


def test_schema_version_reflects_the_identity_contract_correction():
    assert SCHEMA_VERSION == "trader_now.v2"


def test_market_data_series_is_independent_from_listed_instrument():
    economic = EconomicInstrument("MNQ")
    series = MarketDataSeries(
        economic_instrument=economic,
        provider=MarketDataProvider.TRADINGVIEW,
        symbol="MNQ1!",
        series_type=MarketDataSeriesType.CONTINUOUS,
        resolved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        resolution_version="tradingview-mnq1.v1",
        resolution_owner="operations",
    )
    listed = ListedInstrument(economic, "CME", "MNQU6", "2026-09")

    assert series.symbol == "MNQ1!"
    assert listed.contract_symbol == "MNQU6"
    assert series.symbol != listed.contract_symbol


@pytest.mark.parametrize("value", ["", " ", "\t"])
def test_snapshot_identity_rejects_blank_values(value):
    with pytest.raises(ValueError, match="snapshot identity"):
        SnapshotIdentity(value)


@pytest.mark.parametrize(
    "field",
    ["product", "symbol", "timeframe", "strategy_id", "strategy_version"],
)
def test_trader_now_identity_rejects_blank_fields(field):
    values = {
        "product": "MNQ",
        "symbol": "MNQ",
        "timeframe": "5m",
        "strategy_id": "displacement_volume_context",
        "strategy_version": "1.0.0",
    }
    values[field] = " "
    with pytest.raises(ValueError, match=field):
        TraderNowIdentity(**values)


def test_available_has_no_reason_codes():
    with pytest.raises(ValueError, match="available data"):
        Availability(AvailabilityStatus.AVAILABLE, ("unexpected_reason",))


def test_availability_rejects_blank_reason_codes():
    with pytest.raises(ValueError, match="reason_codes"):
        Availability(AvailabilityStatus.UNAVAILABLE, ("",))


def test_trusted_has_no_degradation_reason_codes():
    with pytest.raises(ValueError, match="trusted data"):
        Trust(TrustStatus.TRUSTED, "freshness.v1", ("delayed",))


def test_trust_requires_a_policy_version():
    with pytest.raises(ValueError, match="policy_version"):
        Trust(TrustStatus.UNAVAILABLE, " ")


def test_decision_is_exactly_not_implemented_with_no_state():
    decision = DecisionNotImplemented()
    assert decision.availability == AvailabilityStatus.NOT_IMPLEMENTED
    assert decision.state is None


def test_decision_rejects_every_other_availability():
    with pytest.raises(ValueError, match="not_implemented"):
        DecisionNotImplemented(availability=AvailabilityStatus.AVAILABLE)


def test_top_level_contract_is_immutable_and_freezes_availability_mapping():
    availability = {"market": Availability(AvailabilityStatus.NOT_IMPLEMENTED)}
    model = TraderNow(
        snapshot=SnapshotIdentity("snapshot-1"),
        identity=_identity(),
        trust=Trust(
            TrustStatus.UNAVAILABLE,
            "freshness.not_implemented",
            ("composition_not_implemented",),
        ),
        availability=availability,
        decision=DecisionNotImplemented(),
    )
    availability["risk"] = Availability(AvailabilityStatus.NOT_IMPLEMENTED)

    assert model.schema_version == SCHEMA_VERSION
    assert tuple(model.availability) == ("market",)
    with pytest.raises(TypeError):
        model.availability["risk"] = Availability(AvailabilityStatus.NOT_IMPLEMENTED)
    with pytest.raises(FrozenInstanceError):
        model.identity = _identity()


def test_final_snapshot_identity_may_remain_unavailable_before_hashing():
    model = TraderNow(
        snapshot=None,
        identity=_identity(),
        trust=Trust(
            TrustStatus.UNAVAILABLE,
            "freshness.not_implemented",
            ("composition_not_implemented",),
        ),
        availability={"market": Availability(AvailabilityStatus.NOT_IMPLEMENTED)},
        decision=DecisionNotImplemented(),
    )
    assert model.snapshot is None


def test_optional_composition_sections_remain_backward_compatible():
    model = TraderNow(
        snapshot=None,
        identity=_identity(),
        trust=Trust(
            TrustStatus.UNAVAILABLE,
            "freshness.not_implemented",
            ("composition_not_implemented",),
        ),
        availability={"market": Availability(AvailabilityStatus.NOT_IMPLEMENTED)},
        decision=DecisionNotImplemented(),
    )

    assert model.schema_version == "trader_now.v2"
    assert model.market is None
    assert model.source_trust is None
    assert model.rules is None
    assert model.setups is None
    assert model.context is None
    assert model.interpretations is None
    assert model.strategy is None


def test_top_level_contract_rejects_wrong_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        TraderNow(
            snapshot=SnapshotIdentity("snapshot-1"),
            identity=_identity(),
            trust=Trust(TrustStatus.UNAVAILABLE, "freshness.not_implemented"),
            availability={"market": Availability(AvailabilityStatus.NOT_IMPLEMENTED)},
            decision=DecisionNotImplemented(),
            schema_version="trader_now.v999",
        )


def test_top_level_contract_requires_explicit_availability():
    with pytest.raises(ValueError, match="availability must not be empty"):
        TraderNow(
            snapshot=SnapshotIdentity("snapshot-1"),
            identity=_identity(),
            trust=Trust(TrustStatus.UNAVAILABLE, "freshness.not_implemented"),
            availability={},
            decision=DecisionNotImplemented(),
        )
