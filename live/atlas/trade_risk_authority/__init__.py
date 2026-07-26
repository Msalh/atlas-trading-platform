"""Product P2A proposed-trade and risk-input authority contracts."""

from .alignment import (
    to_candidate_trade_input,
    validate_proposal,
    validate_risk_input_alignment,
)
from .models import (
    AUTHORITY_METADATA_SCHEMA_VERSION,
    PROPOSED_TRADE_SCHEMA_VERSION,
    AlignmentReason,
    AlignmentResult,
    AuthoritativeValue,
    AuthorityMetadata,
    ProposedTrade,
    QuantityResolution,
    SourceAuthority,
    StrategyCandidateIdentity,
)
from .ports import (
    AccountStatePort,
    InstrumentSpecificationProvider,
    PositionStatePort,
    RiskPolicyProvider,
)
from .serialization import serialize_proposed_trade

__all__ = [
    "AUTHORITY_METADATA_SCHEMA_VERSION",
    "PROPOSED_TRADE_SCHEMA_VERSION",
    "AccountStatePort",
    "AlignmentReason",
    "AlignmentResult",
    "AuthoritativeValue",
    "AuthorityMetadata",
    "InstrumentSpecificationProvider",
    "PositionStatePort",
    "ProposedTrade",
    "QuantityResolution",
    "RiskPolicyProvider",
    "SourceAuthority",
    "StrategyCandidateIdentity",
    "serialize_proposed_trade",
    "to_candidate_trade_input",
    "validate_proposal",
    "validate_risk_input_alignment",
]
