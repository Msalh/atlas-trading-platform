"""
POST /api/v1/market-state (Sprint 3) - ingests a TradingView market_state
event: authenticates, parses, validates, translates to canonical form, and
persists it idempotently.

GET /api/v1/market-state/latest, GET /api/v1/market-state/history (Sprint 4),
GET /api/v1/market-state/integrity (Sprint 8), GET /api/v1/market-state/export
(Sprint 9) - read the persisted state back, report gaps found in it, or
export a range of it. Unlike the POST route, these are protected
by the shared API_KEY (Depends(require_api_key), applied per-route below),
the same scheme every other read endpoint in this app already uses (trades,
stats, analytics, risk, activity) - not the POST route's own webhook-style
secret, which protects a different trust domain (an inbound TradingView
event, not an authenticated read by this system's own frontend). Applied
per-route rather than at router-registration time (unlike every other
existing router) because this file, uniquely, mixes both auth schemes on one
router - the POST route keeps its inline secret check unchanged.

POST's authentication uses a dedicated MARKET_STATE_WEBHOOK_SECRET (see
atlas/config.py for why it's separate from WEBHOOK_SECRET), body-embedded and
constant-time compared - the exact same scheme atlas/api/v1/webhook.py
already uses, not a new one. Rate-limited (30/minute per IP) against the same
class of flooding risk /webhook is already protected against - same limiter,
same threshold, reused directly.

_secret_matches/_sanitize_raw_body are deliberately duplicated from
webhook.py rather than imported - the same call this project already made in
Sprint 1 for now_iso() (see atlas/core/time.py's docstring): consolidating
small, private helpers into a shared module is a safe, low-priority cleanup
for whenever a Sprint is already touching those files, not a reason to modify
webhook.py - an execution-critical, currently-live file - for a Sprint whose
declared scope doesn't call for it.
"""
import hmac
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from atlas.api.deps import get_event_bus, get_market_state_repository
from atlas.api.security import require_api_key
from atlas.config import settings
from atlas.core.errors import AtlasDomainError, NaiveDatetimeError
from atlas.core.time import require_utc
from atlas.events import types as event_types
from atlas.events.bus import EventBus
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.ports import IngestOutcome, MarketStateRepository
from atlas.market_engine.service import (
    get_latest_market_state,
    get_market_state_export,
    get_market_state_history,
    get_market_state_integrity_report,
    ingest_tradingview_payload,
)
from atlas.rate_limit import limiter

logger = logging.getLogger("atlas.market_state")

router = APIRouter()


def _parse_symbol_and_timeframe(symbol: str, timeframe: str) -> tuple[Symbol, Timeframe] | JSONResponse:
    """Returns the parsed domain values, or a ready-to-return 422 JSONResponse
    if either query parameter is invalid - callers check isinstance(result,
    JSONResponse) once rather than duplicating two separate try/except blocks
    in every route."""
    try:
        parsed_symbol = Symbol(symbol)
    except AtlasDomainError as e:
        return JSONResponse({"ok": False, "error": f"invalid symbol: {e}"}, status_code=422)
    try:
        parsed_timeframe = Timeframe(timeframe)
    except ValueError:
        valid = [t.value for t in Timeframe]
        return JSONResponse(
            {"ok": False, "error": f"invalid timeframe {timeframe!r} - must be one of {valid}"},
            status_code=422,
        )
    return parsed_symbol, parsed_timeframe


def _parse_utc_query_timestamp(raw: str, param_name: str) -> datetime | JSONResponse:
    """Same accepted shape (trailing 'Z' or explicit numeric offset, rejects
    naive) as atlas.market_engine.adapters.tradingview.translator's own
    _parse_utc_timestamp - deliberately duplicated rather than imported, the
    same call this file already made for _secret_matches/_sanitize_raw_body
    above: that helper is TradingView-adapter-private and wire-format
    specific, and importing it here for a generic query-parameter would blur
    "adapters translate inward only" for no real benefit over six duplicated
    lines."""
    normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return JSONResponse(
            {"ok": False, "error": f"{param_name} {raw!r} is not a valid ISO-8601 datetime"},
            status_code=422,
        )
    try:
        return require_utc(parsed)
    except NaiveDatetimeError:
        return JSONResponse(
            {"ok": False, "error": f"{param_name} {raw!r} has no timezone information - must be explicit UTC (a trailing 'Z' or a numeric offset)"},
            status_code=422,
        )


def _secret_matches(provided: str | None, expected: str) -> bool:
    if not expected:
        return True
    if not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided, expected)


def _sanitize_raw_body(raw_body: str) -> str:
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body
    if isinstance(data, dict) and "secret" in data:
        data = {k: v for k, v in data.items() if k != "secret"}
        return json.dumps(data)
    return raw_body


@router.post("/market-state")
@limiter.limit("30/minute")
async def ingest_market_state(
    request: Request,
    repository: MarketStateRepository = Depends(get_market_state_repository),
    event_bus: EventBus = Depends(get_event_bus),
):
    raw = await request.body()
    try:
        raw_json = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "error": "invalid JSON"}, status_code=400)

    provided_secret = raw_json.get("secret") if isinstance(raw_json, dict) else None
    if not _secret_matches(provided_secret, settings.market_state_webhook_secret):
        return JSONResponse({"ok": False, "error": "bad secret"}, status_code=401)

    if not isinstance(raw_json, dict):
        return JSONResponse({"ok": False, "error": "invalid payload: expected a JSON object"}, status_code=422)

    sanitized_raw_body = _sanitize_raw_body(raw.decode("utf-8", errors="replace"))

    try:
        result = await ingest_tradingview_payload(raw_json, sanitized_raw_body, repository)
    except Exception as e:
        logger.exception("market_state ingestion failed")
        return JSONResponse({"ok": False, "error": f"internal error: {e}"}, status_code=500)

    if result.error is not None:
        return JSONResponse({"ok": False, "error": result.error}, status_code=422)

    # Sprint 7: published for BOTH outcomes below - a duplicate still proves
    # data is flowing (a TradingView redelivery, not a gap), which is exactly
    # what atlas.monitoring's staleness detection needs to know. Never on the
    # request-critical path itself (EventBus.publish awaits subscribers, but
    # every subscriber that does real work - atlas.status.SystemStatus.record,
    # atlas.monitoring's own alerting - is fast/non-blocking by the same
    # discipline already established in atlas/alerting.py's module docstring).
    await event_bus.publish(event_types.MARKET_STATE_INGESTED, {
        "event_id": raw_json.get("event_id"),
        "symbol": raw_json.get("symbol"),
        "timeframe": raw_json.get("timeframe"),
        "duplicate": result.outcome == IngestOutcome.DUPLICATE,
    })

    if result.outcome == IngestOutcome.DUPLICATE:
        return JSONResponse({"ok": True, "duplicate": True}, status_code=208)

    return JSONResponse({"ok": True, "duplicate": False}, status_code=200)


@router.get("/market-state/latest", dependencies=[Depends(require_api_key)])
async def read_latest_market_state(
    symbol: str,
    timeframe: str,
    repository: MarketStateRepository = Depends(get_market_state_repository),
):
    parsed = _parse_symbol_and_timeframe(symbol, timeframe)
    if isinstance(parsed, JSONResponse):
        return parsed
    parsed_symbol, parsed_timeframe = parsed

    data = await get_latest_market_state(parsed_symbol, parsed_timeframe, repository)
    return JSONResponse({"ok": True, "found": data is not None, "data": data}, status_code=200)


@router.get("/market-state/history", dependencies=[Depends(require_api_key)])
async def read_market_state_history(
    symbol: str,
    timeframe: str,
    limit: int = Query(default=100, ge=1, le=1000),
    repository: MarketStateRepository = Depends(get_market_state_repository),
):
    parsed = _parse_symbol_and_timeframe(symbol, timeframe)
    if isinstance(parsed, JSONResponse):
        return parsed
    parsed_symbol, parsed_timeframe = parsed

    data = await get_market_state_history(parsed_symbol, parsed_timeframe, limit, repository)
    return JSONResponse({"ok": True, "count": len(data), "data": data}, status_code=200)


@router.get("/market-state/integrity", dependencies=[Depends(require_api_key)])
async def read_market_state_integrity(
    symbol: str,
    timeframe: str,
    limit: int = Query(default=100, ge=1, le=1000),
    repository: MarketStateRepository = Depends(get_market_state_repository),
):
    """Sprint 8 (Data Validation & Integrity) - reports gaps in the stored
    series over the most recent `limit` events. Detection and reporting only;
    does not repair or backfill anything. See
    atlas.market_engine.service.find_gaps's docstring for what counts as a
    gap and the disclosed market-hours-awareness limitation."""
    parsed = _parse_symbol_and_timeframe(symbol, timeframe)
    if isinstance(parsed, JSONResponse):
        return parsed
    parsed_symbol, parsed_timeframe = parsed

    report = await get_market_state_integrity_report(parsed_symbol, parsed_timeframe, limit, repository)
    return JSONResponse({"ok": True, **report}, status_code=200)


@router.get("/market-state/export", dependencies=[Depends(require_api_key)])
async def read_market_state_export(
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    limit: int = Query(default=10000, ge=1, le=50000),
    repository: MarketStateRepository = Depends(get_market_state_repository),
):
    """Sprint 9 (Dataset Builder, Phase 1) - a static export of a stored
    series over [start, end], gap-annotated. See
    atlas.market_engine.service.get_market_state_export's docstring for the
    response-shape decision (a JSON array, not a downloadable file body) and
    atlas.market_engine.ports.MarketStateRepository.get_range's docstring for
    the `limit` ceiling reasoning."""
    parsed = _parse_symbol_and_timeframe(symbol, timeframe)
    if isinstance(parsed, JSONResponse):
        return parsed
    parsed_symbol, parsed_timeframe = parsed

    parsed_start = _parse_utc_query_timestamp(start, "start")
    if isinstance(parsed_start, JSONResponse):
        return parsed_start
    parsed_end = _parse_utc_query_timestamp(end, "end")
    if isinstance(parsed_end, JSONResponse):
        return parsed_end

    if parsed_start > parsed_end:
        return JSONResponse({"ok": False, "error": "start must not be after end"}, status_code=422)

    report = await get_market_state_export(parsed_symbol, parsed_timeframe, parsed_start, parsed_end, limit, repository)
    return JSONResponse({"ok": True, **report}, status_code=200)
