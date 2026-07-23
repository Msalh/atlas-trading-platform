"""
Strategy Engine evaluation service - Phase N3, Sprint 2. evaluate_strategies()
is the one function this module defines: given one ReplayFrame and an
ordered sequence of StrategyPlugin implementations, evaluates each plugin
exactly once against that frame and returns their StrategyDecision
objects, unchanged, as an immutable tuple in the same order.

Pure and synchronous: no repository, no async, no I/O, no logging, no
caching, no retry, no registry, no aggregation or winner selection - every
plugin's decision is preserved independently, exactly as produced. This
mirrors the same "compose existing outputs, add no new interpretation"
discipline every other pure evaluator in this pipeline already follows
(atlas.rule_engine.service.build_rule_engine_output,
atlas.setup_engine.service.build_setup_engine_output,
atlas.market_context.service.build_market_context) - the one new thing
this function does is verify each plugin's own output describes the frame
it was actually given, not recompute or reinterpret it.

--- Alignment, not computation ---

evaluate_strategies() never recomputes anything a plugin already decided -
disposition, direction, setup_ids, reason_codes, and every optional
reference field pass through completely untouched, by object identity
(the exact StrategyDecision instance a plugin returns is the exact
instance this function returns - never rebuilt, never normalized). Its
only added behavior is a defense-in-depth check that a plugin's own
output actually describes the frame and plugin identity it claims to:
occurred_at must match frame.market_state.envelope.occurred_at,
context_fingerprint must match frame.market_context.context_fingerprint,
and strategy_id/strategy_version must match the plugin instance that
produced it. A violation here means a real plugin bug (hand-built its own
StrategyDecision and got something wrong, or misreports its own
identity) - so it is raised, never silently corrected or swallowed, the
same "fail loudly" posture atlas.replay_engine.service's own
_assert_aligned already established one layer down.

A plugin's own exception (raised from evaluate()) propagates completely
unchanged - this module adds no try/except around any plugin call. A
broken plugin is a real bug and must surface as itself.

Note: frame.market_state has no top-level occurred_at field -
occurred_at/received_at live on its envelope (see
atlas.market_engine.models.MarketState's own docstring), so alignment is
checked against frame.market_state.envelope.occurred_at.
"""
from collections.abc import Sequence

from atlas.replay_engine.models import ReplayFrame
from atlas.strategy_engine.models import StrategyDecision
from atlas.strategy_engine.ports import StrategyPlugin


class StrategyEvaluationError(Exception):
    """Base type for every Strategy Engine service alignment/identity
    violation raised by evaluate_strategies. Catch this specifically to
    handle "a plugin's own output didn't describe what it was given"
    without also swallowing an unrelated bug - the same
    WindowIntegrityError/ReplayAlignmentError-style split this codebase
    already uses at every other pure-composition boundary."""


class StrategyOccurredAtMismatchError(StrategyEvaluationError):
    """Raised when a plugin's returned StrategyDecision.occurred_at does
    not match the evaluated frame's own market_state.envelope.occurred_at."""


class StrategyContextFingerprintMismatchError(StrategyEvaluationError):
    """Raised when a plugin's returned StrategyDecision.context_fingerprint
    does not match the evaluated frame's own market_context.context_fingerprint."""


class StrategyIdentityMismatchError(StrategyEvaluationError):
    """Raised when a plugin's returned StrategyDecision.strategy_id/
    strategy_version does not match the plugin instance's own
    strategy_id/strategy_version - a plugin misreporting its own identity."""


def _assert_decision_aligned(frame: ReplayFrame, plugin: StrategyPlugin, decision: StrategyDecision) -> None:
    expected_occurred_at = frame.market_state.envelope.occurred_at
    if decision.occurred_at != expected_occurred_at:
        raise StrategyOccurredAtMismatchError(
            f"{plugin.strategy_id}: decision.occurred_at={decision.occurred_at!r} does not match "
            f"frame.market_state.envelope.occurred_at={expected_occurred_at!r}"
        )

    expected_fingerprint = frame.market_context.context_fingerprint
    if decision.context_fingerprint != expected_fingerprint:
        raise StrategyContextFingerprintMismatchError(
            f"{plugin.strategy_id}: decision.context_fingerprint={decision.context_fingerprint!r} does not "
            f"match frame.market_context.context_fingerprint={expected_fingerprint!r}"
        )

    if decision.strategy_id != plugin.strategy_id or decision.strategy_version != plugin.strategy_version:
        raise StrategyIdentityMismatchError(
            f"plugin reports strategy_id={plugin.strategy_id!r}/strategy_version={plugin.strategy_version!r}, "
            f"but its own decision reports strategy_id={decision.strategy_id!r}/"
            f"strategy_version={decision.strategy_version!r}"
        )


def evaluate_strategies(
    frame: ReplayFrame,
    strategies: Sequence[StrategyPlugin],
) -> tuple[StrategyDecision, ...]:
    """Pure. Evaluates every plugin in `strategies` exactly once, in the
    same order, against `frame`. Returns an empty tuple for an empty
    sequence - the same "no position to evaluate, no error" posture every
    other sequence composer in this codebase already uses for an empty
    input. Never mutates frame or strategies; never aggregates, filters,
    ranks, or selects among the returned decisions - every plugin's own
    decision is preserved independently."""
    decisions = []
    for plugin in strategies:
        decision = plugin.evaluate(frame)
        _assert_decision_aligned(frame, plugin, decision)
        decisions.append(decision)
    return tuple(decisions)
