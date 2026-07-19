"""
GET /api/v1/rule-engine/latest (Sprint 15) - the Rule Engine's first real
consumer: evaluates and returns the latest RuleEngineOutput for a
(symbol, timeframe), computed on demand, never persisted. A dedicated Rule
Engine route namespace, not nested under /market-state - Rule Engine is its
own domain package (atlas/rule_engine/), depending on Market Engine's read
ports, never the reverse (Dependency Rules,
docs/market_engine/architecture-principles.md) - its read surface evolves
independently.

Protected by the same shared API_KEY every other read endpoint in this app
already uses (Depends(require_api_key), applied at router-registration time
in atlas/main.py, matching trades.router/status.router/etc. - this router,
unlike market_state.router, has exactly one route and one auth scheme, so
there is no reason to apply it per-route). No query-string API key
workaround (unlike /stream's ?api_key=, which exists for a real technical
constraint - browsers' EventSource can't set headers - this endpoint
doesn't have): the browser-viewability need is already met by FastAPI's
existing /docs (Sprint 9), not a reason to widen this endpoint's auth
surface.

No LLM integration, no setup scoring, no entry/SL/TP recommendations, no
trade execution - this endpoint exposes raw, deterministic Rule Engine facts
only, exactly what atlas.rule_engine.service already computes. See
docs/market_engine/rule-engine-architecture.md's Interface section for why
that boundary matters.

"Insufficient history" is not a distinct HTTP-level condition - if some
MarketState exists but not enough for every fact's window, the response is
still 200/found=true, with the affected facts individually serialized as
status="insufficient_data" (see rule_engine_output_to_dict's docstring).
Inventing a different status code for a partial-but-valid result would
contradict the whole reason InsufficientData exists as a first-class,
non-exceptional outcome (Sprint 11).

_parse_symbol_and_timeframe is deliberately duplicated from
atlas/api/v1/market_state.py rather than imported - the same call this
project has made since Sprint 3 for small, private, per-file helpers (see
market_state.py's own docstring for the precedent).
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from atlas.api.deps import get_market_state_repository
from atlas.core.errors import AtlasDomainError
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.ports import MarketStateRepository
from atlas.rule_engine.service import evaluate_latest_rule_engine_output, rule_engine_output_to_dict

router = APIRouter()


def _parse_symbol_and_timeframe(symbol: str, timeframe: str) -> tuple[Symbol, Timeframe] | JSONResponse:
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


@router.get("/rule-engine/latest")
async def read_latest_rule_engine_output(
    symbol: str,
    timeframe: str,
    repository: MarketStateRepository = Depends(get_market_state_repository),
):
    parsed = _parse_symbol_and_timeframe(symbol, timeframe)
    if isinstance(parsed, JSONResponse):
        return parsed
    parsed_symbol, parsed_timeframe = parsed

    output = await evaluate_latest_rule_engine_output(parsed_symbol, parsed_timeframe, repository)
    if output is None:
        return JSONResponse({"ok": True, "found": False, "data": None}, status_code=200)

    return JSONResponse({"ok": True, "found": True, "data": rule_engine_output_to_dict(output)}, status_code=200)
