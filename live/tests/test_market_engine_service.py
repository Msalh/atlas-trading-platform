import pytest

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.ports import IngestOutcome
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository
from atlas.market_engine.service import ingest_tradingview_payload


def _payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "event_id": "e1",
        "symbol": "MNQU6",
        "source": "tradingview",
        "timeframe": "5m",
        "timestamp": "2026-07-18T13:35:00Z",
        "bar_status": "closed",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def repo():
    return InMemoryMarketStateRepository()


class TestIngestTradingviewPayload:
    @pytest.mark.asyncio
    async def test_valid_payload_stored(self, repo):
        result = await ingest_tradingview_payload(_payload(), raw_payload="{}", repository=repo)
        assert result.outcome == IngestOutcome.STORED
        assert result.error is None

    @pytest.mark.asyncio
    async def test_duplicate_payload_reported_as_duplicate(self, repo):
        await ingest_tradingview_payload(_payload(), raw_payload="{}", repository=repo)
        result = await ingest_tradingview_payload(_payload(), raw_payload="{}", repository=repo)
        assert result.outcome == IngestOutcome.DUPLICATE
        assert result.error is None

    @pytest.mark.asyncio
    async def test_wire_validation_failure_reported_not_raised(self, repo):
        result = await ingest_tradingview_payload(
            _payload(close="not-a-number"), raw_payload="{}", repository=repo
        )
        assert result.outcome is None
        assert result.error is not None
        assert "invalid payload" in result.error

    @pytest.mark.asyncio
    async def test_missing_required_field_reported_not_raised(self, repo):
        payload = _payload()
        del payload["symbol"]
        result = await ingest_tradingview_payload(payload, raw_payload="{}", repository=repo)
        assert result.outcome is None
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_off_tick_domain_failure_reported_not_raised(self, repo):
        result = await ingest_tradingview_payload(_payload(close=20125.80), raw_payload="{}", repository=repo)
        assert result.outcome is None
        assert result.error is not None
        assert "tick grid" in result.error

    @pytest.mark.asyncio
    async def test_illegal_event_type_reported_not_raised(self, repo):
        result = await ingest_tradingview_payload(
            _payload(event_type="not_a_real_event_type"), raw_payload="{}", repository=repo
        )
        assert result.outcome is None
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_rejected_payload_is_never_persisted(self, repo):
        await ingest_tradingview_payload(_payload(close=20125.80), raw_payload="{}", repository=repo)
        assert await repo.get_latest(Symbol("MNQU6"), Timeframe.M5) is None

    @pytest.mark.asyncio
    async def test_raw_payload_reaches_the_repository_unmodified(self, repo):
        raw = '{"schema_version": "1.0", "note": "exact bytes preserved"}'
        await ingest_tradingview_payload(_payload(), raw_payload=raw, repository=repo)
        assert repo.raw_payload_for(Symbol("MNQU6"), Timeframe.M5, "e1") == raw

    @pytest.mark.asyncio
    async def test_result_outcome_and_error_are_mutually_exclusive(self, repo):
        stored = await ingest_tradingview_payload(_payload(), raw_payload="{}", repository=repo)
        assert (stored.outcome is None) != (stored.error is None)  # exactly one is set

        rejected = await ingest_tradingview_payload(
            _payload(event_id="e2", close="bad"), raw_payload="{}", repository=repo
        )
        assert (rejected.outcome is None) != (rejected.error is None)
