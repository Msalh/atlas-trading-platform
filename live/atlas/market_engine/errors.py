"""
market_engine's own domain errors - distinct from atlas.core.errors because these
are rules specific to what a market-state event is (a legal event_type, a
non-blank schema_version), not general domain primitives. Both subclass
AtlasDomainError so callers can catch "any domain violation, anywhere in this
system" at the core level, or "specifically a market_engine violation" here.
"""
from atlas.core.errors import AtlasDomainError


class MarketEngineValidationError(AtlasDomainError):
    """Raised when a MarketState (or the payload translating into one) violates
    a market_engine-specific rule - an illegal event_type, a blank
    schema_version. Price/Symbol/timestamp rules are enforced by atlas.core and
    raise atlas.core's own error types instead; this type is only for rules that
    belong to market_engine specifically."""
