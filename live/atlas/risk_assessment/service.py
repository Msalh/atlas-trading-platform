"""Pure deterministic V1 candidate risk assessment."""

from decimal import Decimal, ROUND_FLOOR

from atlas.risk_assessment.models import (
    REASON_VOCABULARY_VERSION,
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
    RiskPolicy,
    RiskReason,
    SizingMode,
    SnapshotFreshnessPolicy,
)
from atlas.strategy_engine.models import (
    StrategyDirection,
    StrategyDisposition,
)

_ORDERED_REASONS = (
    RiskReason.IDENTITY_MISMATCH,
    RiskReason.TIMESTAMP_MISMATCH,
    RiskReason.SESSION_MISMATCH,
    RiskReason.ACCOUNT_MISSING,
    RiskReason.ACCOUNT_STALE,
    RiskReason.ACCOUNT_INVALID,
    RiskReason.ACCOUNT_UNRECONCILED,
    RiskReason.POSITION_MISSING,
    RiskReason.POSITION_STALE,
    RiskReason.POSITION_UNRECONCILED,
    RiskReason.INSTRUMENT_MISSING,
    RiskReason.POLICY_MISSING,
    RiskReason.ACCOUNT_KILL_SWITCH_ACTIVE,
    RiskReason.DAILY_LOSS_BREACHED,
    RiskReason.TRAILING_DRAWDOWN_BREACHED,
    RiskReason.CANDIDATE_NOT_APPLICABLE,
    RiskReason.CANDIDATE_UNSUPPORTED_DIRECTION,
    RiskReason.CANDIDATE_ENTRY_MISSING,
    RiskReason.CANDIDATE_STOP_MISSING,
    RiskReason.CANDIDATE_TARGET_MISSING,
    RiskReason.CANDIDATE_LEVEL_MISMATCH,
    RiskReason.CANDIDATE_INVALID_STOP_GEOMETRY,
    RiskReason.CANDIDATE_ZERO_STOP_DISTANCE,
    RiskReason.CANDIDATE_EXPIRED,
    RiskReason.MAXIMUM_EXPOSURE_EXCEEDED,
    RiskReason.CONCURRENT_POSITION_LIMIT,
    RiskReason.WORKING_ORDER_LIMIT,
    RiskReason.OPPOSITE_POSITION,
    RiskReason.INSUFFICIENT_REMAINING_RISK,
    RiskReason.MAXIMUM_QUANTITY_EXCEEDED,
    RiskReason.ZERO_APPROVED_QUANTITY,
    RiskReason.MARGIN_UNKNOWN,
    RiskReason.MARGIN_INSUFFICIENT,
    RiskReason.SESSION_INELIGIBLE,
)
_REASON_ORDER = {reason: index for index, reason in enumerate(_ORDERED_REASONS)}


def assess_candidate_risk(input: RiskAssessmentInput) -> RiskAssessment:
    """Assess one candidate using only the supplied immutable input."""
    strategy = input.strategy_decision
    candidate = input.candidate

    if strategy.disposition != StrategyDisposition.CANDIDATE:
        return _result(
            input,
            AssessmentStatus.NOT_APPLICABLE,
            (RiskReason.CANDIDATE_NOT_APPLICABLE,),
            account_freshness=_account_freshness(input),
            position_freshness=_position_freshness(input),
            candidate_freshness=_candidate_freshness(input),
        )

    account_freshness = _account_freshness(input)
    position_freshness = _position_freshness(input)
    candidate_freshness = _candidate_freshness(input)
    unassessable = _unassessable_reasons(
        input,
        account_freshness,
        position_freshness,
        candidate_freshness,
    )

    price_ticks: tuple[int, int] | None = None
    if input.instrument is not None:
        price_ticks, price_reasons = _price_ticks(candidate, input.instrument)
        unassessable.extend(price_reasons)

    ordered_unassessable = _ordered_reasons(unassessable)
    if ordered_unassessable:
        return _result(
            input,
            AssessmentStatus.UNASSESSABLE,
            ordered_unassessable,
            account_freshness=account_freshness,
            position_freshness=position_freshness,
            candidate_freshness=candidate_freshness,
        )

    assert input.account is not None
    assert input.instrument is not None
    assert input.policy is not None
    assert price_ticks is not None

    entry_ticks, stop_ticks = price_ticks
    risk_ticks = abs(entry_ticks - stop_ticks)
    risk_points = Decimal(risk_ticks) * input.instrument.tick_size
    risk_per_contract = Decimal(risk_ticks) * input.instrument.tick_value

    remaining_daily, remaining_drawdown = _remaining_capacities(
        input.account, input.policy
    )
    blocked = _blocked_reasons(input, remaining_daily, remaining_drawdown)

    maximum_quantity = _maximum_approved_quantity(
        input,
        risk_per_contract,
        remaining_daily,
        remaining_drawdown,
    )
    if (
        input.policy.enforce_margin
        and input.account.available_margin is not None
        and input.instrument.margin_per_contract is not None
        and input.account.available_margin < input.instrument.margin_per_contract
    ):
        blocked.append(RiskReason.MARGIN_INSUFFICIENT)
    requested_quantity = candidate.requested_quantity

    if input.policy.sizing_mode == SizingMode.FIXED:
        if requested_quantity is None or requested_quantity == 0:
            blocked.append(RiskReason.ZERO_APPROVED_QUANTITY)
        elif requested_quantity > maximum_quantity:
            blocked.append(RiskReason.MAXIMUM_QUANTITY_EXCEEDED)
        calculated_quantity = requested_quantity or 0
    else:
        calculated_quantity = maximum_quantity

    if maximum_quantity == 0:
        blocked.append(RiskReason.ZERO_APPROVED_QUANTITY)

    ordered_blocked = _ordered_reasons(blocked)
    status = AssessmentStatus.BLOCKED if ordered_blocked else AssessmentStatus.APPROVED
    approved_quantity = 0 if ordered_blocked else calculated_quantity
    total_candidate_risk = risk_per_contract * Decimal(approved_quantity)

    exposure_before = _exposure_before(input.positions, input.policy)
    return _result(
        input,
        status,
        ordered_blocked,
        account_freshness=account_freshness,
        position_freshness=position_freshness,
        candidate_freshness=candidate_freshness,
        requested_quantity=requested_quantity,
        maximum_approved_quantity=maximum_quantity,
        approved_quantity=approved_quantity,
        risk_points=risk_points,
        risk_ticks=risk_ticks,
        risk_per_contract=risk_per_contract,
        total_candidate_risk=total_candidate_risk,
        remaining_daily_risk=remaining_daily,
        remaining_drawdown=remaining_drawdown,
        exposure_before=exposure_before,
        exposure_after=exposure_before + approved_quantity,
    )


def _classify_freshness(
    *,
    observed_at,
    received_at,
    evaluated_at,
    maximum_age_seconds: Decimal,
    policy: SnapshotFreshnessPolicy,
) -> FreshnessStatus:
    future_skew = Decimal(str((observed_at - evaluated_at).total_seconds()))
    if future_skew > policy.allowed_future_skew_seconds:
        return FreshnessStatus.INVALID
    age = Decimal(str((evaluated_at - observed_at).total_seconds()))
    if age > maximum_age_seconds:
        return FreshnessStatus.STALE
    source_delay = Decimal(str((received_at - observed_at).total_seconds()))
    if source_delay > policy.max_source_receive_delay_seconds:
        return FreshnessStatus.DELAYED
    return FreshnessStatus.CURRENT


def _account_freshness(input: RiskAssessmentInput) -> FreshnessStatus:
    if input.account is None:
        return FreshnessStatus.UNAVAILABLE
    return _classify_freshness(
        observed_at=input.account.observed_at,
        received_at=input.account.received_at,
        evaluated_at=input.evaluated_at,
        maximum_age_seconds=input.freshness_policy.account_max_age_seconds,
        policy=input.freshness_policy,
    )


def _position_freshness(input: RiskAssessmentInput) -> FreshnessStatus:
    if not input.positions:
        return FreshnessStatus.UNAVAILABLE
    statuses = tuple(
        _classify_freshness(
            observed_at=position.observed_at,
            received_at=position.received_at,
            evaluated_at=input.evaluated_at,
            maximum_age_seconds=input.freshness_policy.position_max_age_seconds,
            policy=input.freshness_policy,
        )
        for position in input.positions
    )
    precedence = (
        FreshnessStatus.INVALID,
        FreshnessStatus.STALE,
        FreshnessStatus.DELAYED,
        FreshnessStatus.CURRENT,
    )
    return next(status for status in precedence if status in statuses)


def _candidate_freshness(input: RiskAssessmentInput) -> FreshnessStatus:
    candidate = input.candidate
    future_skew = Decimal(
        str((candidate.candidate_at - input.evaluated_at).total_seconds())
    )
    if future_skew > input.freshness_policy.allowed_future_skew_seconds:
        return FreshnessStatus.INVALID
    age = Decimal(str((input.evaluated_at - candidate.candidate_at).total_seconds()))
    if age > input.freshness_policy.candidate_max_age_seconds:
        return FreshnessStatus.STALE
    return FreshnessStatus.CURRENT


def _unassessable_reasons(
    input: RiskAssessmentInput,
    account_freshness: FreshnessStatus,
    position_freshness: FreshnessStatus,
    candidate_freshness: FreshnessStatus,
) -> list[RiskReason]:
    reasons: list[RiskReason] = []
    strategy = input.strategy_decision
    candidate = input.candidate

    if candidate.direction not in (
        StrategyDirection.LONG.value,
        StrategyDirection.SHORT.value,
    ):
        reasons.append(RiskReason.CANDIDATE_UNSUPPORTED_DIRECTION)
    if (
        strategy.strategy_id != candidate.strategy_id
        or strategy.strategy_version != candidate.strategy_version
        or strategy.context_fingerprint != candidate.context_fingerprint
        or strategy.direction.value != candidate.direction
    ):
        reasons.append(RiskReason.IDENTITY_MISMATCH)
    if (
        strategy.occurred_at != candidate.candidate_at
        or input.latest_closed_at != strategy.occurred_at
    ):
        reasons.append(RiskReason.TIMESTAMP_MISMATCH)

    if input.account is None:
        reasons.append(RiskReason.ACCOUNT_MISSING)
    else:
        if input.account.effective_session_id != input.effective_session_id:
            reasons.append(RiskReason.SESSION_MISMATCH)
        if account_freshness == FreshnessStatus.STALE:
            reasons.append(RiskReason.ACCOUNT_STALE)
        elif account_freshness == FreshnessStatus.INVALID:
            reasons.append(RiskReason.ACCOUNT_INVALID)
        if input.account.reconciliation_status == ReconciliationStatus.UNRECONCILED:
            reasons.append(RiskReason.ACCOUNT_UNRECONCILED)

    if not input.positions:
        reasons.append(RiskReason.POSITION_MISSING)
    else:
        if position_freshness in (FreshnessStatus.STALE, FreshnessStatus.INVALID):
            reasons.append(RiskReason.POSITION_STALE)
        if any(
            position.reconciliation_status == ReconciliationStatus.UNRECONCILED
            for position in input.positions
        ):
            reasons.append(RiskReason.POSITION_UNRECONCILED)

    if input.instrument is None:
        reasons.append(RiskReason.INSTRUMENT_MISSING)
    else:
        if (
            input.instrument.product != candidate.product
            or input.instrument.contract_symbol != candidate.contract_symbol
        ):
            reasons.append(RiskReason.IDENTITY_MISMATCH)

    if input.policy is None:
        reasons.append(RiskReason.POLICY_MISSING)
    else:
        if input.policy.freshness_policy_id != input.freshness_policy.policy_id:
            reasons.append(RiskReason.IDENTITY_MISMATCH)
        if input.policy.require_target and candidate.target is None:
            reasons.append(RiskReason.CANDIDATE_TARGET_MISSING)
        if (
            input.policy.sizing_mode == SizingMode.RISK_BASED
            and input.policy.maximum_risk_per_trade is None
            and input.policy.maximum_risk_fraction is None
        ):
            reasons.append(RiskReason.POLICY_MISSING)
        if (
            input.policy.trailing_drawdown_limit is not None
            and input.account is not None
            and input.account.high_water_mark is None
        ):
            reasons.append(RiskReason.ACCOUNT_INVALID)
        if input.policy.enforce_margin and (
            input.account is None
            or input.account.available_margin is None
            or input.instrument is None
            or input.instrument.margin_per_contract is None
        ):
            reasons.append(RiskReason.MARGIN_UNKNOWN)

    if candidate_freshness in (FreshnessStatus.STALE, FreshnessStatus.INVALID):
        reasons.append(RiskReason.CANDIDATE_EXPIRED)

    for position in input.positions:
        if (
            input.account is not None
            and position.account_id != input.account.account_id
        ):
            reasons.append(RiskReason.IDENTITY_MISMATCH)
        if (
            position.product != candidate.product
            or position.contract_symbol != candidate.contract_symbol
        ):
            reasons.append(RiskReason.IDENTITY_MISMATCH)

    return reasons


def _price_ticks(
    candidate: CandidateTradeInput,
    instrument: InstrumentSpecification,
) -> tuple[tuple[int, int] | None, list[RiskReason]]:
    entry = Decimal(str(candidate.entry.value))
    stop = Decimal(str(candidate.stop.value))
    tick_size = instrument.tick_size
    entry_ratio = entry / tick_size
    stop_ratio = stop / tick_size
    if (
        entry_ratio != entry_ratio.to_integral_value()
        or stop_ratio != stop_ratio.to_integral_value()
    ):
        return None, [RiskReason.CANDIDATE_LEVEL_MISMATCH]

    entry_ticks = int(entry_ratio)
    stop_ticks = int(stop_ratio)
    if entry_ticks == stop_ticks:
        return None, [RiskReason.CANDIDATE_ZERO_STOP_DISTANCE]
    if candidate.direction == StrategyDirection.LONG.value and stop_ticks > entry_ticks:
        return None, [RiskReason.CANDIDATE_INVALID_STOP_GEOMETRY]
    if (
        candidate.direction == StrategyDirection.SHORT.value
        and stop_ticks < entry_ticks
    ):
        return None, [RiskReason.CANDIDATE_INVALID_STOP_GEOMETRY]
    return (entry_ticks, stop_ticks), []


def _remaining_capacities(
    account: AccountSnapshot,
    policy: RiskPolicy,
) -> tuple[Decimal, Decimal | None]:
    daily_total_pnl = account.daily_realized_pnl + (
        account.unrealized_pnl or Decimal(0)
    )
    daily_loss_used = max(-daily_total_pnl, Decimal(0))
    remaining_daily = (
        policy.daily_loss_limit - daily_loss_used - policy.minimum_remaining_daily_risk
    )

    remaining_drawdown = None
    if (
        policy.trailing_drawdown_limit is not None
        and account.high_water_mark is not None
    ):
        trailing_stop = account.high_water_mark - policy.trailing_drawdown_limit
        remaining_drawdown = account.net_liquidation - trailing_stop
    return remaining_daily, remaining_drawdown


def _blocked_reasons(
    input: RiskAssessmentInput,
    remaining_daily: Decimal,
    remaining_drawdown: Decimal | None,
) -> list[RiskReason]:
    assert input.account is not None
    assert input.policy is not None
    reasons: list[RiskReason] = []
    account = input.account
    policy = input.policy

    if account.kill_switch_status == KillSwitchStatus.ACTIVE:
        reasons.append(RiskReason.ACCOUNT_KILL_SWITCH_ACTIVE)
    daily_loss_used = max(
        -(account.daily_realized_pnl + (account.unrealized_pnl or Decimal(0))),
        Decimal(0),
    )
    if daily_loss_used >= policy.daily_loss_limit:
        reasons.append(RiskReason.DAILY_LOSS_BREACHED)
    if remaining_drawdown is not None and remaining_drawdown <= 0:
        reasons.append(RiskReason.TRAILING_DRAWDOWN_BREACHED)
    if remaining_daily <= 0 or (
        remaining_drawdown is not None and remaining_drawdown <= 0
    ):
        reasons.append(RiskReason.INSUFFICIENT_REMAINING_RISK)
    if account.account_status in policy.no_trade_account_statuses:
        reasons.append(RiskReason.ACCOUNT_KILL_SWITCH_ACTIVE)
    if input.effective_session_id not in policy.eligible_session_ids:
        reasons.append(RiskReason.SESSION_INELIGIBLE)

    nonflat = tuple(
        position for position in input.positions if position.side != PositionSide.FLAT
    )
    if len(nonflat) >= policy.maximum_concurrent_positions:
        reasons.append(RiskReason.CONCURRENT_POSITION_LIMIT)
    for position in nonflat:
        if position.side.value == input.candidate.direction:
            if policy.block_same_direction_additions:
                reasons.append(RiskReason.MAXIMUM_EXPOSURE_EXCEEDED)
        elif policy.block_opposite_positions:
            reasons.append(RiskReason.OPPOSITE_POSITION)

    working = sum(position.working_entry_quantity for position in input.positions)
    if (
        policy.working_orders_count_as_exposure
        and working >= policy.maximum_working_order_quantity
    ):
        reasons.append(RiskReason.WORKING_ORDER_LIMIT)
    return reasons


def _maximum_approved_quantity(
    input: RiskAssessmentInput,
    risk_per_contract: Decimal,
    remaining_daily: Decimal,
    remaining_drawdown: Decimal | None,
) -> int:
    assert input.account is not None
    assert input.instrument is not None
    assert input.policy is not None
    policy = input.policy
    instrument = input.instrument

    risk_budgets = [remaining_daily]
    if remaining_drawdown is not None:
        risk_budgets.append(remaining_drawdown)
    if policy.maximum_risk_per_trade is not None:
        risk_budgets.append(policy.maximum_risk_per_trade)
    if policy.maximum_risk_fraction is not None:
        risk_budgets.append(
            input.account.net_liquidation * policy.maximum_risk_fraction
        )
    risk_budget = min(risk_budgets)
    risk_quantity = (
        0
        if risk_budget <= 0
        else int(
            (risk_budget / risk_per_contract).to_integral_value(rounding=ROUND_FLOOR)
        )
    )

    open_quantity = sum(position.net_quantity for position in input.positions)
    working_quantity = (
        sum(position.working_entry_quantity for position in input.positions)
        if policy.working_orders_count_as_exposure
        else 0
    )
    caps = (
        policy.maximum_quantity,
        max(
            policy.maximum_open_position_quantity - open_quantity - working_quantity, 0
        ),
        risk_quantity,
    )
    maximum = min(caps)
    if policy.working_orders_count_as_exposure:
        maximum = min(
            maximum,
            max(policy.maximum_working_order_quantity - working_quantity, 0),
        )
    if instrument.maximum_platform_quantity is not None:
        maximum = min(maximum, instrument.maximum_platform_quantity)
    maximum = _floor_to_increment(maximum, instrument.quantity_increment)

    if policy.enforce_margin:
        assert input.account.available_margin is not None
        assert instrument.margin_per_contract is not None
        margin_quantity = int(
            (
                input.account.available_margin / instrument.margin_per_contract
            ).to_integral_value(rounding=ROUND_FLOOR)
        )
        maximum = min(
            maximum, _floor_to_increment(margin_quantity, instrument.quantity_increment)
        )
    return maximum if maximum >= instrument.minimum_quantity else 0


def _floor_to_increment(quantity: int, increment: int) -> int:
    return (quantity // increment) * increment


def _exposure_before(
    positions: tuple[PositionSnapshot, ...],
    policy: RiskPolicy,
) -> int:
    open_quantity = sum(position.net_quantity for position in positions)
    working_quantity = (
        sum(position.working_entry_quantity for position in positions)
        if policy.working_orders_count_as_exposure
        else 0
    )
    return open_quantity + working_quantity


def _ordered_reasons(reasons: list[RiskReason]) -> tuple[RiskReason, ...]:
    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


def _source_identities(input: RiskAssessmentInput) -> tuple[str, ...]:
    candidates = [
        input.snapshot_id,
        input.candidate.provenance.source_object_id,
        input.freshness_policy.policy_id,
    ]
    if input.account is not None:
        candidates.append(input.account.snapshot_id)
    candidates.extend(position.snapshot_id for position in input.positions)
    if input.instrument is not None:
        candidates.append(input.instrument.specification_id)
    if input.policy is not None:
        candidates.append(input.policy.policy_id)
    return tuple(dict.fromkeys(candidates))


def _result(
    input: RiskAssessmentInput,
    status: AssessmentStatus,
    reasons: tuple[RiskReason, ...],
    *,
    account_freshness: FreshnessStatus,
    position_freshness: FreshnessStatus,
    candidate_freshness: FreshnessStatus,
    requested_quantity: int | None = None,
    maximum_approved_quantity: int | None = None,
    approved_quantity: int | None = None,
    risk_points: Decimal | None = None,
    risk_ticks: int | None = None,
    risk_per_contract: Decimal | None = None,
    total_candidate_risk: Decimal | None = None,
    remaining_daily_risk: Decimal | None = None,
    remaining_drawdown: Decimal | None = None,
    exposure_before: int | None = None,
    exposure_after: int | None = None,
) -> RiskAssessment:
    policy = input.policy
    account = input.account
    candidate = input.candidate
    return RiskAssessment(
        identity=AssessmentIdentity(
            assessment_id=(
                f"risk:{input.input_id}:{candidate.candidate_id}:"
                f"{policy.policy_version if policy is not None else 'policy-unavailable'}"
            ),
            input_id=input.input_id,
            snapshot_id=input.snapshot_id,
            candidate_id=candidate.candidate_id,
            account_snapshot_id=account.snapshot_id if account is not None else None,
            policy_id=policy.policy_id if policy is not None else None,
            policy_version=policy.policy_version if policy is not None else None,
        ),
        assessed_at=input.evaluated_at,
        candidate_at=candidate.candidate_at,
        status=status,
        primary_reason=reasons[0] if reasons else None,
        contributing_reasons=reasons[1:],
        summaries=(),
        direction=candidate.direction,
        entry=candidate.entry,
        stop=candidate.stop,
        target=candidate.target,
        invalidation=candidate.invalidation,
        sizing_mode=policy.sizing_mode if policy is not None else None,
        requested_quantity=requested_quantity,
        maximum_approved_quantity=maximum_approved_quantity,
        approved_quantity=approved_quantity,
        risk_points=risk_points,
        risk_ticks=risk_ticks,
        risk_per_contract=risk_per_contract,
        total_candidate_risk=total_candidate_risk,
        remaining_daily_risk=remaining_daily_risk,
        remaining_drawdown=remaining_drawdown,
        exposure_before=exposure_before,
        exposure_after=exposure_after,
        account_freshness=account_freshness,
        position_freshness=position_freshness,
        candidate_freshness=candidate_freshness,
        reconciliation_status=(
            account.reconciliation_status if account is not None else None
        ),
        source_identities=_source_identities(input),
        reason_vocabulary_version=REASON_VOCABULARY_VERSION,
    )
