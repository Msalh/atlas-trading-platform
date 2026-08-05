"""Package-owned, fail-closed pricing authority for provider adapters."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime


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
_OPERATIONAL_RECORDS: tuple[ProviderPricingRecord, ...] = ()
_OPERATIONAL_APPROVED_SOURCES: frozenset[tuple[str, str]] = frozenset()
_OPERATIONAL_CATALOG_SHA256 = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


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
    matches = tuple(record for record in records if record.reference_id == reference_id)
    if len(matches) != 1:
        return None
    record = matches[0]
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
        and record.maximum_age_seconds > 0
        and record.effective_at <= record.verified_at <= now < record.expires_at
        and (now - record.verified_at).total_seconds() <= record.maximum_age_seconds
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
    """Resolve only package-owned operational pricing; empty until approved."""

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
