from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from atlas.core.primitives import Price
from atlas.risk_assessment.models import (
    ACCOUNT_SNAPSHOT_SCHEMA_VERSION,
    ASSESSMENT_SCHEMA_VERSION,
    CANDIDATE_SCHEMA_VERSION,
    FRESHNESS_POLICY_SCHEMA_VERSION,
    INSTRUMENT_SCHEMA_VERSION,
    POSITION_SNAPSHOT_SCHEMA_VERSION,
    REASON_VOCABULARY_VERSION,
    RISK_INPUT_SCHEMA_VERSION,
    RISK_POLICY_SCHEMA_VERSION,
    AccountSnapshot,
    AssessmentIdentity,
    AssessmentStatus,
    CandidateTradeInput,
    FreshnessStatus,
    InstrumentSpecification,
    KillSwitchStatus,
    PositionSide,
    PositionSnapshot,
    ReconciliationStatus,
    RiskAssessment,
    RiskAssessmentInput,
    RiskAuthority,
    RiskPolicy,
    RiskReason,
    SizingMode,
    SnapshotFreshnessPolicy,
    SourceProvenance,
)
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)

NOW = datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc)
PRICE = Price(20_000.0, 0.25)
STOP = Price(19_990.0, 0.25)
PROVENANCE = SourceProvenance("broker", "v1", "object-1", "42")


def account() -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="account-snapshot-1",
        account_id="account-1",
        provider_id="provider-1",
        observed_at=NOW,
        received_at=NOW,
        effective_session_id="session-1",
        currency="USD",
        net_liquidation=Decimal("50000.00"),
        daily_realized_pnl=Decimal("0.00"),
        account_status="active",
        kill_switch_status=KillSwitchStatus.INACTIVE,
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=PROVENANCE,
    )


def position(
    *,
    snapshot_id: str = "position-1",
    contract_symbol: str = "MNQU6",
) -> PositionSnapshot:
    return PositionSnapshot(
        snapshot_id=snapshot_id,
        account_id="account-1",
        product="MNQ",
        contract_symbol=contract_symbol,
        side=PositionSide.FLAT,
        net_quantity=0,
        observed_at=NOW,
        received_at=NOW,
        broker_position_status="flat",
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=PROVENANCE,
    )


def instrument() -> InstrumentSpecification:
    return InstrumentSpecification(
        specification_id="instrument-1",
        product="MNQ",
        contract_symbol="MNQU6",
        asset_class="future",
        exchange="CME",
        currency="USD",
        tick_size=Decimal("0.25"),
        tick_value=Decimal("0.50"),
        point_value=Decimal("2.00"),
        contract_multiplier=Decimal("2.00"),
        minimum_quantity=1,
        quantity_increment=1,
        price_precision=2,
        session_calendar_id="cme-rth-v1",
        provenance=PROVENANCE,
    )


def freshness_policy() -> SnapshotFreshnessPolicy:
    return SnapshotFreshnessPolicy(
        policy_id="freshness-1",
        policy_version="1.0.0",
        account_max_age_seconds=Decimal("30"),
        position_max_age_seconds=Decimal("30"),
        candidate_max_age_seconds=Decimal("30"),
        max_source_receive_delay_seconds=Decimal("5"),
        allowed_future_skew_seconds=Decimal("2"),
        require_same_session=True,
        provenance=PROVENANCE,
    )


def risk_policy() -> RiskPolicy:
    return RiskPolicy(
        policy_id="risk-1",
        policy_version="1.0.0",
        account_profile_id="account-profile-1",
        authority=RiskAuthority.ADVISORY,
        sizing_mode=SizingMode.FIXED,
        freshness_policy_id="freshness-1",
        maximum_quantity=5,
        maximum_open_position_quantity=5,
        maximum_working_order_quantity=5,
        maximum_concurrent_positions=1,
        minimum_remaining_daily_risk=Decimal("100"),
        daily_loss_limit=Decimal("1000"),
        trailing_drawdown_limit=Decimal("2000"),
        block_same_direction_additions=True,
        block_opposite_positions=True,
        working_orders_count_as_exposure=True,
        require_target=False,
        enforce_margin=False,
        no_trade_account_statuses=("restricted",),
        eligible_session_ids=("session-1",),
        provenance=PROVENANCE,
        maximum_risk_per_trade=Decimal("200"),
    )


def strategy_decision() -> StrategyDecision:
    return StrategyDecision(
        occurred_at=NOW,
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        disposition=StrategyDisposition.CANDIDATE,
        direction=StrategyDirection.LONG,
        setup_ids=("setup-1",),
        reason_codes=(),
        context_fingerprint="context-1",
    )


def candidate() -> CandidateTradeInput:
    return CandidateTradeInput(
        candidate_id="candidate-1",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        context_fingerprint="context-1",
        product="MNQ",
        contract_symbol="MNQU6",
        candidate_at=NOW,
        direction="long",
        entry_type="market",
        entry=PRICE,
        stop=STOP,
        provenance=PROVENANCE,
        requested_quantity=1,
    )


def assessment_input(
    positions: tuple[PositionSnapshot, ...] = (),
) -> RiskAssessmentInput:
    return RiskAssessmentInput(
        input_id="input-1",
        snapshot_id="market-snapshot-1",
        strategy_decision=strategy_decision(),
        candidate=candidate(),
        freshness_policy=freshness_policy(),
        evaluated_at=NOW,
        effective_session_id="session-1",
        latest_closed_at=NOW,
        account=account(),
        positions=positions,
        instrument=instrument(),
        policy=risk_policy(),
    )


def assessment() -> RiskAssessment:
    return RiskAssessment(
        identity=AssessmentIdentity(
            assessment_id="assessment-1",
            input_id="input-1",
            snapshot_id="market-snapshot-1",
            candidate_id="candidate-1",
            account_snapshot_id="account-snapshot-1",
            policy_id="risk-1",
            policy_version="1.0.0",
        ),
        assessed_at=NOW,
        candidate_at=NOW,
        status=AssessmentStatus.APPROVED,
        primary_reason=None,
        contributing_reasons=(),
        summaries=(),
        direction="long",
        entry=PRICE,
        stop=STOP,
        sizing_mode=SizingMode.FIXED,
        requested_quantity=1,
        maximum_approved_quantity=1,
        approved_quantity=1,
        risk_points=Decimal("10"),
        risk_ticks=40,
        risk_per_contract=Decimal("20"),
        total_candidate_risk=Decimal("20"),
        remaining_daily_risk=Decimal("980"),
        remaining_drawdown=Decimal("1980"),
        exposure_before=0,
        exposure_after=1,
        account_freshness=FreshnessStatus.CURRENT,
        position_freshness=FreshnessStatus.CURRENT,
        candidate_freshness=FreshnessStatus.CURRENT,
        reconciliation_status=ReconciliationStatus.RECONCILED,
        source_identities=("account-snapshot-1", "market-snapshot-1"),
    )


def test_public_models_are_frozen_hashable_value_objects():
    values = (
        PROVENANCE,
        account(),
        position(),
        instrument(),
        freshness_policy(),
        risk_policy(),
        candidate(),
        assessment_input(),
        assessment().identity,
        assessment(),
    )

    for value in values:
        hash(value)
        with pytest.raises(FrozenInstanceError):
            value.schema_version = "changed"  # type: ignore[attr-defined]


def test_collections_are_tuples_and_preserve_identity_and_provenance():
    model = assessment_input((position(),))

    assert isinstance(model.positions, tuple)
    assert model.positions[0].provenance is PROVENANCE
    assert model.account is not None
    assert model.account.snapshot_id == "account-snapshot-1"
    assert model.candidate.candidate_id == "candidate-1"


def test_schema_and_reason_versions_are_stable():
    assert account().schema_version == ACCOUNT_SNAPSHOT_SCHEMA_VERSION
    assert position().schema_version == POSITION_SNAPSHOT_SCHEMA_VERSION
    assert instrument().schema_version == INSTRUMENT_SCHEMA_VERSION
    assert freshness_policy().schema_version == FRESHNESS_POLICY_SCHEMA_VERSION
    assert risk_policy().schema_version == RISK_POLICY_SCHEMA_VERSION
    assert candidate().schema_version == CANDIDATE_SCHEMA_VERSION
    assert assessment_input().schema_version == RISK_INPUT_SCHEMA_VERSION
    assert assessment().schema_version == ASSESSMENT_SCHEMA_VERSION
    assert assessment().reason_vocabulary_version == REASON_VOCABULARY_VERSION


def test_approved_enum_values_are_stable():
    assert tuple(status.value for status in AssessmentStatus) == (
        "approved",
        "blocked",
        "unassessable",
        "not_applicable",
    )
    assert tuple(status.value for status in FreshnessStatus) == (
        "current",
        "delayed",
        "stale",
        "invalid",
        "unavailable",
        "not_applicable",
    )
    assert tuple(status.value for status in ReconciliationStatus) == (
        "reconciled",
        "unreconciled",
    )
    assert RiskReason.ACCOUNT_MISSING.value == "risk.account.missing"
    assert RiskReason.ZERO_APPROVED_QUANTITY.value == "risk.quantity.zero_approved"


@pytest.mark.parametrize("field", ["source_id", "source_version", "source_object_id"])
def test_provenance_rejects_blank_required_identity(field):
    values = {
        "source_id": "source",
        "source_version": "v1",
        "source_object_id": "object",
    }
    values[field] = " "
    with pytest.raises(ValueError, match=field):
        SourceProvenance(**values)


def test_snapshot_rejects_naive_or_reversed_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        AccountSnapshot(
            **{
                **account().__dict__,
                "observed_at": NOW.replace(tzinfo=None),
            }
        )

    with pytest.raises(ValueError, match="must not precede"):
        AccountSnapshot(
            **{
                **account().__dict__,
                "received_at": NOW - timedelta(seconds=1),
            }
        )


def test_flat_and_non_flat_position_shapes_are_enforced():
    with pytest.raises(ValueError, match="flat position"):
        PositionSnapshot(
            **{
                **position().__dict__,
                "net_quantity": 1,
            }
        )

    with pytest.raises(ValueError, match="non-flat position"):
        PositionSnapshot(
            **{
                **position().__dict__,
                "side": PositionSide.LONG,
                "net_quantity": 1,
            }
        )

    long_position = PositionSnapshot(
        **{
            **position().__dict__,
            "side": PositionSide.LONG,
            "net_quantity": 1,
            "average_entry_price": PRICE,
        }
    )
    assert long_position.side == PositionSide.LONG


def test_negative_quantities_are_structurally_rejected():
    with pytest.raises(ValueError, match="net_quantity"):
        PositionSnapshot(**{**position().__dict__, "net_quantity": -1})
    with pytest.raises(ValueError, match="requested_quantity"):
        CandidateTradeInput(**{**candidate().__dict__, "requested_quantity": -1})


def test_duplicate_position_identities_are_rejected():
    first = position()
    duplicate_snapshot = position(contract_symbol="MNQZ6")
    with pytest.raises(ValueError, match="snapshot identities"):
        assessment_input((first, duplicate_snapshot))

    duplicate_key = position(snapshot_id="position-2")
    with pytest.raises(ValueError, match="account/contract"):
        assessment_input((first, duplicate_key))


def test_policy_tuple_duplicates_are_rejected():
    with pytest.raises(ValueError, match="eligible_session_ids"):
        RiskPolicy(
            **{
                **risk_policy().__dict__,
                "eligible_session_ids": ("session-1", "session-1"),
            }
        )


def test_assessment_reason_and_source_duplicates_are_rejected():
    with pytest.raises(ValueError, match="primary_reason"):
        RiskAssessment(
            **{
                **assessment().__dict__,
                "primary_reason": RiskReason.ACCOUNT_STALE,
                "contributing_reasons": (RiskReason.ACCOUNT_STALE,),
            }
        )

    with pytest.raises(ValueError, match="source_identities"):
        RiskAssessment(
            **{
                **assessment().__dict__,
                "source_identities": ("same", "same"),
            }
        )


def test_models_store_values_without_evaluating_business_rules():
    model = RiskAssessment(
        **{
            **assessment().__dict__,
            "status": AssessmentStatus.BLOCKED,
            "primary_reason": RiskReason.DAILY_LOSS_BREACHED,
            "approved_quantity": 1,
        }
    )

    assert model.status == AssessmentStatus.BLOCKED
    assert model.approved_quantity == 1
