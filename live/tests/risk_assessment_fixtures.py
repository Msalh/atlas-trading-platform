"""Deterministic immutable fixtures shared by RiskAssessment certification tests."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal

from atlas.core.primitives import Price
from atlas.risk_assessment.models import (
    AccountSnapshot,
    CandidateTradeInput,
    InstrumentSpecification,
    KillSwitchStatus,
    PositionSide,
    PositionSnapshot,
    ReconciliationStatus,
    RiskAssessmentInput,
    RiskAuthority,
    RiskPolicy,
    SizingMode,
    SnapshotFreshnessPolicy,
    SourceProvenance,
)
from atlas.strategy_engine.models import (
    StrategyDecision,
    StrategyDirection,
    StrategyDisposition,
)

EVALUATED_AT = datetime(2026, 7, 24, 14, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RiskFixtureSet:
    provenance_kind: str
    account: AccountSnapshot
    position: PositionSnapshot
    instrument: InstrumentSpecification
    freshness_policy: SnapshotFreshnessPolicy
    risk_policy: RiskPolicy
    candidate: CandidateTradeInput
    strategy_decision: StrategyDecision
    assessment_input: RiskAssessmentInput


def provenance(kind: str, object_name: str) -> SourceProvenance:
    return SourceProvenance(
        source_id=f"{kind}_fixture",
        source_version="fixture.v1",
        source_object_id=f"{kind}:{object_name}",
        source_sequence="1",
    )


def account_snapshot(kind: str = "replay", **changes) -> AccountSnapshot:
    value = AccountSnapshot(
        snapshot_id="account-snapshot-1",
        account_id="account-1",
        provider_id="provider-1",
        observed_at=EVALUATED_AT,
        received_at=EVALUATED_AT,
        effective_session_id="session-1",
        currency="USD",
        net_liquidation=Decimal("50000"),
        daily_realized_pnl=Decimal("0"),
        account_status="active",
        kill_switch_status=KillSwitchStatus.INACTIVE,
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=provenance(kind, "account"),
        unrealized_pnl=Decimal("0"),
        high_water_mark=Decimal("50000"),
    )
    return replace(value, **changes)


def position_snapshot(kind: str = "replay", **changes) -> PositionSnapshot:
    value = PositionSnapshot(
        snapshot_id="position-snapshot-1",
        account_id="account-1",
        product="MNQ",
        contract_symbol="MNQU6",
        side=PositionSide.FLAT,
        net_quantity=0,
        observed_at=EVALUATED_AT,
        received_at=EVALUATED_AT,
        broker_position_status="flat",
        reconciliation_status=ReconciliationStatus.RECONCILED,
        provenance=provenance(kind, "position"),
    )
    return replace(value, **changes)


def instrument_specification(
    kind: str = "replay", **changes
) -> InstrumentSpecification:
    value = InstrumentSpecification(
        specification_id="instrument-specification-1",
        product="MNQ",
        contract_symbol="MNQU6",
        asset_class="future",
        exchange="CME",
        currency="USD",
        tick_size=Decimal("0.25"),
        tick_value=Decimal("0.50"),
        point_value=Decimal("2"),
        contract_multiplier=Decimal("2"),
        minimum_quantity=1,
        quantity_increment=1,
        price_precision=2,
        session_calendar_id="cme-rth-v1",
        provenance=provenance(kind, "instrument"),
    )
    return replace(value, **changes)


def freshness_policy(kind: str = "replay", **changes) -> SnapshotFreshnessPolicy:
    value = SnapshotFreshnessPolicy(
        policy_id="freshness-policy-1",
        policy_version="1.0.0",
        account_max_age_seconds=Decimal("30"),
        position_max_age_seconds=Decimal("30"),
        candidate_max_age_seconds=Decimal("30"),
        max_source_receive_delay_seconds=Decimal("5"),
        allowed_future_skew_seconds=Decimal("2"),
        require_same_session=True,
        provenance=provenance(kind, "freshness-policy"),
    )
    return replace(value, **changes)


def risk_policy(kind: str = "replay", **changes) -> RiskPolicy:
    value = RiskPolicy(
        policy_id="risk-policy-1",
        policy_version="1.0.0",
        account_profile_id="account-profile-1",
        authority=RiskAuthority.ADVISORY,
        sizing_mode=SizingMode.FIXED,
        freshness_policy_id="freshness-policy-1",
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
        provenance=provenance(kind, "risk-policy"),
        maximum_risk_per_trade=Decimal("200"),
    )
    return replace(value, **changes)


def candidate_trade_input(kind: str = "replay", **changes) -> CandidateTradeInput:
    value = CandidateTradeInput(
        candidate_id="candidate-1",
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        context_fingerprint="context-1",
        product="MNQ",
        contract_symbol="MNQU6",
        candidate_at=EVALUATED_AT,
        direction="long",
        entry_type="market",
        entry=Price(20_000, 0.25),
        stop=Price(19_990, 0.25),
        provenance=provenance(kind, "candidate"),
        requested_quantity=1,
    )
    return replace(value, **changes)


def strategy_decision(**changes) -> StrategyDecision:
    value = StrategyDecision(
        occurred_at=EVALUATED_AT,
        strategy_id="displacement_volume_context",
        strategy_version="1.0.0",
        disposition=StrategyDisposition.CANDIDATE,
        direction=StrategyDirection.LONG,
        setup_ids=("setup-1",),
        reason_codes=(),
        context_fingerprint="context-1",
    )
    return replace(value, **changes)


def assessment_input(kind: str = "replay", **changes) -> RiskAssessmentInput:
    value = RiskAssessmentInput(
        input_id="risk-input-1",
        snapshot_id="market-snapshot-1",
        strategy_decision=strategy_decision(),
        candidate=candidate_trade_input(kind),
        freshness_policy=freshness_policy(kind),
        evaluated_at=EVALUATED_AT,
        effective_session_id="session-1",
        latest_closed_at=EVALUATED_AT,
        account=account_snapshot(kind),
        positions=(position_snapshot(kind),),
        instrument=instrument_specification(kind),
        policy=risk_policy(kind),
    )
    return replace(value, **changes)


def fixture_set(kind: str = "replay") -> RiskFixtureSet:
    value = assessment_input(kind)
    assert value.account is not None
    assert value.instrument is not None
    assert value.policy is not None
    return RiskFixtureSet(
        provenance_kind=kind,
        account=value.account,
        position=value.positions[0],
        instrument=value.instrument,
        freshness_policy=value.freshness_policy,
        risk_policy=value.policy,
        candidate=value.candidate,
        strategy_decision=value.strategy_decision,
        assessment_input=value,
    )


def equivalent_input_pair() -> tuple[RiskAssessmentInput, RiskAssessmentInput]:
    return assessment_input("replay"), assessment_input("live")
