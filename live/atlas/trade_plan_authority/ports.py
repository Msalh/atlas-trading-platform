"""Read-only structural ports for future P2B authority providers."""

from typing import Protocol

from atlas.trader_now.models import MarketInputWindow

from .models import (
    AuthoritySource,
    CanonicalMarketEvidenceResolution,
    ExchangeSessionAuthorityRequest,
    ExchangeSessionResolution,
    InstrumentSpecificationAuthorityRequest,
    InstrumentSpecificationResolution,
    ListedContractAuthorityRequest,
    ListedContractResolution,
    TradePlanPolicyAuthorityRequest,
    TradePlanPolicyResolution,
)


class ListedContractAuthority(Protocol):
    def resolve_listed_contract(
        self, request: ListedContractAuthorityRequest
    ) -> ListedContractResolution: ...


class InstrumentSpecificationAuthority(Protocol):
    def resolve_instrument_specification(
        self, request: InstrumentSpecificationAuthorityRequest
    ) -> InstrumentSpecificationResolution: ...


class ExchangeSessionAuthority(Protocol):
    def resolve_exchange_session(
        self, request: ExchangeSessionAuthorityRequest
    ) -> ExchangeSessionResolution: ...


class TradePlanPolicyAuthority(Protocol):
    def resolve_trade_plan_policy(
        self, request: TradePlanPolicyAuthorityRequest
    ) -> TradePlanPolicyResolution: ...


class CanonicalMarketEvidenceAuthority(Protocol):
    def adapt_market_input(
        self,
        *,
        market_input: MarketInputWindow,
        source: AuthoritySource,
    ) -> CanonicalMarketEvidenceResolution: ...
