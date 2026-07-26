"""Read-only structural ports for future authoritative risk inputs."""

from datetime import datetime
from typing import Protocol

from atlas.risk_assessment.models import (
    AccountSnapshot,
    InstrumentSpecification,
    PositionSnapshot,
    RiskPolicy,
)
from atlas.trader_now.models import EconomicInstrument, ListedInstrument

from .models import AuthoritativeValue


class AccountStatePort(Protocol):
    def get_account_state(
        self, *, account_id: str, evaluated_at: datetime
    ) -> AuthoritativeValue[AccountSnapshot]: ...


class PositionStatePort(Protocol):
    def get_position_state(
        self,
        *,
        account_id: str,
        listed_instrument: ListedInstrument,
        evaluated_at: datetime,
    ) -> AuthoritativeValue[tuple[PositionSnapshot, ...]]: ...


class InstrumentSpecificationProvider(Protocol):
    def get_instrument_specification(
        self, *, listed_instrument: ListedInstrument, evaluated_at: datetime
    ) -> AuthoritativeValue[InstrumentSpecification]: ...


class RiskPolicyProvider(Protocol):
    def get_risk_policy(
        self,
        *,
        account_profile_id: str,
        economic_instrument: EconomicInstrument,
        evaluated_at: datetime,
    ) -> AuthoritativeValue[RiskPolicy]: ...
