"""
Sprint 11 (Rule Engine foundation) orchestration, extended Sprint 13 to accept
a WINDOW of MarketState rather than a single one, and Sprint 14 to drive fact
evaluation from atlas.rule_engine.registry.REGISTRY instead of a hardcoded
dict literal - see registry.py's own module docstring for the registry's
design. This module no longer imports atlas.rule_engine.facts or
atlas.rule_engine.definitions directly; REGISTRY already composes them.

build_rule_engine_output is pure/sync (no I/O) - the property both
"deterministic tests" and "replay reproducibility tests" depend on: given the
same window of MarketState, this function always returns the same
RuleEngineOutput, regardless of whether that window came from live ingestion
(get_history) or Sprint 10's replay_market_state. Nothing in this function -
or in the registry's evaluators underneath it - knows or cares which path
produced its input.

evaluate_latest_rule_engine_output is the one async wrapper - the same
thin-adapter shape already established by atlas/monitoring.py's background
loop and every async function in atlas/market_engine/service.py: all the real
logic stays in the pure function above it. It fetches
registry.required_history() bars via get_history (most-recent-first) and
reverses them into the ascending convention build_rule_engine_output expects -
Sprint 13's hardcoded HISTORY_LIMIT constant is gone; this number is now a
computed consequence of the registry, not a value a future Sprint has to
remember to bump by hand.

No `history_limit` override parameter (Sprint 13 had one; Sprint 14 removes
it) - no real caller ever used it, and an override would reopen exactly the
caller-induced-under-fetching risk removing HISTORY_LIMIT was meant to close:
a caller passing a value below what the active registry actually needs would
silently produce InsufficientData for genuinely available history, which is
indistinguishable from a real data gap. If a real future need for a narrower
or wider fetch ever appears, that deserves its own explicit design then, not
speculative support now.

Sprint 15 adds rule_engine_output_to_dict() - the first real consumer
(atlas/api/v1/rule_engine.py) now exists, so a serialization shape is
finally needed. This module still has zero FastAPI/HTTP awareness: the
route owns the {"ok", "found", "data"} transport envelope, this module only
ever produces a plain, JSON-safe dict of the domain output itself - the
same domain/transport split atlas.market_engine.service.market_state_to_dict
already established.

Sprint 17A adds build_rule_engine_output_window() - the capability Setup
Engine needs to construct a SetupEvaluationContext, but that Rule Engine
itself did not yet have: turning a WINDOW of MarketState into a
corresponding window of RuleEngineOutput, one per input bar, rather than
only the single latest output build_rule_engine_output already produced.
Pure, like build_rule_engine_output - validated via
atlas.rule_engine.window_integrity.validate_market_state_window before any
fact is evaluated, so a caller gets a typed WindowIntegrityError instead of
a RuleEngineOutput silently built over a gappy or malformed window.
Deliberately no impure repository-backed wrapper yet (contrast
evaluate_latest_rule_engine_output above): a naive "most recent N" query can
itself cross a session boundary and immediately violate this function's
strict-contiguity contract, and no range/session-aware repository query
exists yet to avoid that. Input selection and segmentation remain the
caller's responsibility for now (Replay, Dataset Builder, or a hand-built
window in a test) - a repository-backed wrapper is future work once a real
range/session contract exists to build it against.
"""
from typing import Any, Optional

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import MarketState
from atlas.market_engine.ports import MarketStateRepository
from atlas.rule_engine.models import FactOutcome, FactResult, RuleEngineOutput
from atlas.rule_engine.registry import REGISTRY, required_history
from atlas.rule_engine.window_integrity import validate_market_state_window

SCHEMA_VERSION = "1.0"


def build_rule_engine_output(window: list[MarketState]) -> RuleEngineOutput:
    """Pure. `window` must be chronologically ASCENDING with the current
    (latest) bar LAST - the same convention get_range/replay_market_state
    already use. Evaluates every fact in REGISTRY, in registration order
    (deterministic, for reproducibility and debugging - no current fact
    depends on another's output; see registry.py for the full reasoning).
    Each registration's `evaluate` already knows whether it needs the whole
    window or just the current bar (see FactRegistration/single_bar_adapter
    in registry.py) - this function does not distinguish the two cases
    itself.

    See docs/market_engine/rule-fact-inventory.md for why each registered
    fact was added and why the rest remain deferred."""
    current = window[-1]
    return RuleEngineOutput(
        schema_version=SCHEMA_VERSION,
        symbol=current.symbol.ticker,
        timeframe=current.timeframe.value,
        occurred_at=current.envelope.occurred_at.isoformat(),
        facts={r.name: r.evaluate(window, r.definition) for r in REGISTRY},
    )


async def evaluate_latest_rule_engine_output(
    symbol: Symbol, timeframe: Timeframe, repository: MarketStateRepository,
) -> Optional[RuleEngineOutput]:
    """Live path: fetches enough history (registry.required_history()) for
    (symbol, timeframe) to satisfy every active fact, and evaluates the Rule
    Engine against it. Returns None if nothing has been ingested yet - the
    same "nothing to evaluate" posture get_latest_market_state already uses;
    not a special Rule Engine case. get_history returns most-recent-first;
    reversed() here produces the ascending order build_rule_engine_output
    requires - reusing get_history plus a reverse, not a new repository
    query."""
    history = await repository.get_history(symbol, timeframe, limit=required_history(REGISTRY))
    if not history:
        return None
    window = list(reversed(history))
    return build_rule_engine_output(window)


def build_rule_engine_output_window(market_state_window: list[MarketState]) -> list[RuleEngineOutput]:
    """Pure. `market_state_window` must be chronologically ASCENDING and
    strictly contiguous (see window_integrity.validate_market_state_window,
    called first - raises a WindowIntegrityError subclass and evaluates
    nothing if the window is empty, mixes symbol/timeframe, is out of order,
    contains a duplicate timestamp, or contains any gap not exactly one
    timeframe cadence wide).

    Returns exactly one RuleEngineOutput per input bar, in the same order -
    never a shorter list. For bar i, build_rule_engine_output is called with
    market_state_window[i]'s own preceding history, up to
    required_history(REGISTRY) bars, however many are actually available
    within the window so far. Early bars therefore naturally receive
    InsufficientData for facts whose required_window exceeds what precedes
    them - the same, already-existing mechanism build_rule_engine_output
    uses for any under-length window, not a new concept introduced here.
    Omitting early bars instead (requiring the caller to over-fetch by
    required_history() - 1 bars beyond what they want output for) was
    considered and rejected: it would make this function's contract depend
    on a padding amount the caller has to know and get right, for no benefit
    over the outcome InsufficientData already models correctly."""
    validate_market_state_window(market_state_window)
    depth = required_history(REGISTRY)
    return [
        build_rule_engine_output(market_state_window[max(0, i - depth + 1) : i + 1])
        for i in range(len(market_state_window))
    ]


def _fact_outcome_to_dict(name: str, outcome: FactOutcome) -> dict[str, Any]:
    if isinstance(outcome, FactResult):
        return {
            "name": name,
            "status": "computed",
            "value": outcome.value,
            "definition_version": outcome.definition_version,
            "evidence": outcome.evidence,
        }
    return {
        "name": name,
        "status": "insufficient_data",
        "definition_version": outcome.definition_version,
        "reason": outcome.reason,
    }


def rule_engine_output_to_dict(output: RuleEngineOutput) -> dict[str, Any]:
    """Sprint 15. Pure domain serialization - shapes a RuleEngineOutput into
    a JSON-safe dict. Knows nothing about HTTP/FastAPI and does not build
    the {"ok", "found", "data"} transport envelope - that is the route's
    concern, not this function's (the same "read-side analogue of
    translator.to_canonical()... not vendor-specific" precedent
    atlas.market_engine.service.market_state_to_dict already established).

    `facts` serializes as an ORDERED LIST, not an object keyed by name.
    RuleEngineOutput.facts is itself an insertion-ordered dict (registry
    order, Sprint 14), but JSON objects are unordered by spec even though
    real serializers preserve insertion order in practice; a JSON array's
    order is spec-guaranteed. This is the deliberately rigorous
    interpretation of "deterministic serialized ordering" - REGISTRY order
    preserved into the wire format, at the cost of direct by-name lookup
    ergonomics for whatever eventually consumes this.

    Every value here is already an ordinary JSON-native primitive, list, or
    dict (see each fact's own evidence construction in facts.py - none of
    the six current facts ever put a datetime, Price, or other non-JSON-safe
    object into evidence) - no generic conversion framework and no
    `default=str` fallback here. A future fact introducing a non-JSON-safe
    evidence value must fail loudly at serialization time and force an
    explicit decision, not be silently stringified into something that
    looks like data but isn't."""
    return {
        "schema_version": output.schema_version,
        "symbol": output.symbol,
        "timeframe": output.timeframe,
        "occurred_at": output.occurred_at,
        "facts": [_fact_outcome_to_dict(name, outcome) for name, outcome in output.facts.items()],
    }
