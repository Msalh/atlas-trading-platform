"""Typed errors raised by the TraderNow application boundary."""


class TraderNowError(Exception):
    """Base error for TraderNow failures."""


class UnsupportedTraderNowIdentityError(TraderNowError):
    """Raised when a request falls outside Sprint 12B's approved identity."""

    def __init__(self, field: str, supplied: str, supported: str) -> None:
        self.field = field
        self.supplied = supplied
        self.supported = supported
        super().__init__(
            f"unsupported TraderNow {field} {supplied!r}; "
            f"only {supported!r} is supported"
        )


class MarketDataSeriesResolutionError(TraderNowError):
    """Raised when a product has no configured persisted analysis series."""


class RiskCompositionAlignmentError(TraderNowError):
    """Raised when explicit risk input lacks one canonical strategy match."""

    def __init__(self, match_count: int) -> None:
        self.match_count = match_count
        super().__init__(
            "risk assessment input must align with exactly one canonical "
            f"StrategyDecision; found {match_count}"
        )
