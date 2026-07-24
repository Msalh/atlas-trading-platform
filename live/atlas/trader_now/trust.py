"""Deterministic raw-source trust projection; no market interpretation."""

from atlas.trader_now.models import (
    AvailabilityStatus,
    Freshness,
    FreshnessStatus,
    MarketInputWindow,
    RawSourceTrust,
    StructuralValidityStatus,
    TrustStatus,
)


def project_raw_source_trust(
    *,
    market_input: MarketInputWindow,
    freshness: Freshness,
) -> RawSourceTrust:
    availability = market_input.availability.status
    if availability == AvailabilityStatus.INVALID:
        structural = StructuralValidityStatus.INVALID
    elif availability == AvailabilityStatus.AVAILABLE:
        structural = StructuralValidityStatus.VALID
    else:
        structural = StructuralValidityStatus.UNAVAILABLE

    reasons = tuple(reason.value for reason in market_input.availability.reason_codes)
    freshness_reasons = tuple(reason.value for reason in freshness.reason_codes)

    if structural == StructuralValidityStatus.INVALID:
        return RawSourceTrust(
            freshness,
            availability,
            structural,
            TrustStatus.UNAVAILABLE,
            reasons or ("structural_input_invalid",),
        )
    if availability != AvailabilityStatus.AVAILABLE:
        return RawSourceTrust(
            freshness,
            availability,
            structural,
            TrustStatus.UNAVAILABLE,
            reasons or ("raw_market_unavailable",),
        )
    if freshness.status == FreshnessStatus.CURRENT:
        return RawSourceTrust(
            freshness,
            availability,
            structural,
            TrustStatus.TRUSTED,
        )
    if freshness.status == FreshnessStatus.DELAYED:
        return RawSourceTrust(
            freshness,
            availability,
            structural,
            TrustStatus.DEGRADED,
            freshness_reasons,
        )
    return RawSourceTrust(
        freshness,
        availability,
        structural,
        TrustStatus.UNAVAILABLE,
        freshness_reasons or ("freshness_unavailable",),
    )
