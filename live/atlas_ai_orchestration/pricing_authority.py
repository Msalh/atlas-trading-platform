"""Package-owned, fail-closed pricing authority for provider adapters."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class ProviderPricingRecord:
    reference_id: str
    catalog_version: str
    provider_id: str
    model_id: str
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float
    currency: str
    unit: str
    service_tier: str
    source_id: str
    source_version: str
    effective_at: datetime
    verified_at: datetime
    expires_at: datetime
    maximum_age_seconds: int


_OPERATIONAL_CATALOG_VERSION = "openai-pricing-catalog.v1"
_OPERATIONAL_RECORDS: tuple[ProviderPricingRecord, ...] = (
    ProviderPricingRecord(
        reference_id="openai-gpt-5.6-terra-default-2026-08-06",
        catalog_version=_OPERATIONAL_CATALOG_VERSION,
        provider_id="openai",
        model_id="gpt-5.6-terra",
        input_usd_per_million_tokens=2.0,
        output_usd_per_million_tokens=12.0,
        currency="USD",
        unit="per_million_tokens",
        service_tier="default",
        source_id="https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/",
        source_version="observed-2026-08-06",
        effective_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        verified_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        expires_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        maximum_age_seconds=2_592_000,
    ),
)
_OPERATIONAL_APPROVED_SOURCES: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/",
            "observed-2026-08-06",
        )
    }
)
_OPERATIONAL_CATALOG_SHA256 = (
    "d9f1b6ae02e4da9f1e06dc46afcc02084a0922a96f12180bac22fd29829cef9a"
)
_AUTHORITY_MAX_INPUT_TOKENS = 16_384
_AUTHORITY_MAX_OUTPUT_TOKENS = 4_096
_AUTHORITY_MAX_COST_USD = Decimal("0.12")
_AUTHORITY_MAX_RECORD_VALIDITY_SECONDS = 2_592_000
_TOKENS_PER_MILLION = Decimal(1_000_000)


def _catalog_bytes(records: tuple[ProviderPricingRecord, ...]) -> bytes:
    def encode(value: object) -> object:
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError

    return json.dumps(
        [asdict(record) for record in records],
        default=encode,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _catalog_digest(records: tuple[ProviderPricingRecord, ...]) -> str:
    return hashlib.sha256(_catalog_bytes(records)).hexdigest()


def _within_authority_cost_ceiling(record: ProviderPricingRecord) -> bool:
    try:
        input_rate = Decimal(str(record.input_usd_per_million_tokens))
        output_rate = Decimal(str(record.output_usd_per_million_tokens))
        cost = (
            Decimal(_AUTHORITY_MAX_INPUT_TOKENS) * input_rate
            + Decimal(_AUTHORITY_MAX_OUTPUT_TOKENS) * output_rate
        ) / _TOKENS_PER_MILLION
    except (InvalidOperation, ValueError):
        return False
    return cost <= _AUTHORITY_MAX_COST_USD


def _resolve_catalog(
    *,
    records: tuple[ProviderPricingRecord, ...],
    approved_sources: frozenset[tuple[str, str]],
    expected_catalog_version: str,
    expected_catalog_sha256: str,
    provider_id: str,
    model_id: str,
    service_tier: str,
    reference_id: str,
    now: datetime,
) -> ProviderPricingRecord | None:
    if not (
        type(records) is tuple
        and all(type(record) is ProviderPricingRecord for record in records)
        and type(approved_sources) is frozenset
        and all(
            type(item) is tuple
            and len(item) == 2
            and all(type(part) is str and bool(part) for part in item)
            for item in approved_sources
        )
        and type(expected_catalog_version) is str
        and bool(expected_catalog_version)
        and type(expected_catalog_sha256) is str
        and len(expected_catalog_sha256) == 64
        and _catalog_digest(records) == expected_catalog_sha256
        and all(
            type(value) is str and bool(value)
            for value in (provider_id, model_id, service_tier, reference_id)
        )
        and type(now) is datetime
        and now.tzinfo is not None
    ):
        return None
    reference_matches = tuple(
        record for record in records if record.reference_id == reference_id
    )
    identity_matches = tuple(
        record
        for record in records
        if record.provider_id == provider_id
        and record.model_id == model_id
        and record.service_tier == service_tier
    )
    if len(reference_matches) != 1 or len(identity_matches) != 1:
        return None
    record = reference_matches[0]
    rates = (
        record.input_usd_per_million_tokens,
        record.output_usd_per_million_tokens,
    )
    timestamps = (record.effective_at, record.verified_at, record.expires_at)
    if not (
        all(
            type(value) is str and bool(value)
            for value in (
                record.reference_id,
                record.catalog_version,
                record.provider_id,
                record.model_id,
                record.currency,
                record.unit,
                record.service_tier,
                record.source_id,
                record.source_version,
            )
        )
        and record.reference_id == reference_id
        and record.catalog_version == expected_catalog_version
        and record.provider_id == provider_id
        and record.model_id == model_id
        and record.service_tier == service_tier
        and (record.source_id, record.source_version) in approved_sources
        and record.currency == "USD"
        and record.unit == "per_million_tokens"
        and all(
            type(value) in {int, float} and math.isfinite(value) and value > 0
            for value in rates
        )
        and all(type(value) is datetime and value.tzinfo is not None for value in timestamps)
        and type(record.maximum_age_seconds) is int
        and 0
        < record.maximum_age_seconds
        <= _AUTHORITY_MAX_RECORD_VALIDITY_SECONDS
        and 0
        < (record.expires_at - record.verified_at).total_seconds()
        <= _AUTHORITY_MAX_RECORD_VALIDITY_SECONDS
        and record.effective_at <= record.verified_at <= now < record.expires_at
        and (now - record.verified_at).total_seconds() <= record.maximum_age_seconds
        and _within_authority_cost_ceiling(record)
    ):
        return None
    return record


def resolve_authoritative_pricing(
    *,
    provider_id: str,
    model_id: str,
    service_tier: str,
    reference_id: str,
    now: datetime,
) -> ProviderPricingRecord | None:
    """Resolve only the package-owned, dated operational pricing record."""

    return _resolve_catalog(
        records=_OPERATIONAL_RECORDS,
        approved_sources=_OPERATIONAL_APPROVED_SOURCES,
        expected_catalog_version=_OPERATIONAL_CATALOG_VERSION,
        expected_catalog_sha256=_OPERATIONAL_CATALOG_SHA256,
        provider_id=provider_id,
        model_id=model_id,
        service_tier=service_tier,
        reference_id=reference_id,
        now=now,
    )
