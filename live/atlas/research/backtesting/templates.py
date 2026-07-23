"""
Phase N4 Sprint 8. Concrete ResearchStrategyPlugin implementations - fixed,
reviewed code, never dynamically generated or discovered (Research Engine
Design Principles, IX.1: closed vocabulary only, the same discipline
atlas.research.features.candidate's closed declarative spec already
established). One implementation this sprint: ThresholdCrossPlugin, backing
RealizationTemplateKind.THRESHOLD_CROSS version "v1" - the roadmap's own
"auto-generated default rule" for TEMPLATED_STRATEGY, expressed as one
fixed, parametrized mechanic rather than any form of generated code. Adding
a second template, or a second version of this one, means adding a class
here and one line to factory.py's own dispatch table - reviewed like any
other code change, never a runtime registration call.
"""
from collections import deque
from typing import Optional

from atlas.research.backtesting.models import ResearchDecision, ResearchDispositionKind
from atlas.research.models import Realization
from atlas.research.replay_bridge import ReplayFrame


class ThresholdCrossPlugin:
    """Enters long the first bar its close crosses above
    parameters["threshold"]; exits the first bar its close crosses back
    below it; NO_ACTION otherwise. Reads MarketState.close directly - no
    Feature Registry dependency, keeping atlas.research.backtesting's own
    audited dependency footprint unchanged (atlas.research.models and this
    package's own local modules only).

    Holds its own bounded internal state (the two most recent close
    values, and whether a position is currently open) across sequential
    decide() calls on the same instance - depends on no external state (no
    I/O, no clock, no config, no environment). ResearchStrategyFactory
    constructs one fresh instance per execute_realization() call, so this
    state never leaks between runs - see factory.py's own purity
    contract."""

    def __init__(self, realization: Realization) -> None:
        self._realization_id = realization.realization_id
        self._realization_version = realization.version
        self._threshold = float(realization.parameters["threshold"])
        self._recent_closes: deque[float] = deque(maxlen=1)
        self._in_position = False

    @property
    def realization_id(self) -> str:
        return self._realization_id

    @property
    def realization_version(self) -> str:
        return self._realization_version

    def decide(self, frame: ReplayFrame) -> ResearchDecision:
        context = frame.market_context
        close = frame.market_state.close

        if close is None:
            return self._decision(context, ResearchDispositionKind.NO_ACTION, "no_close")

        close_value = close.value
        previous: Optional[float] = self._recent_closes[-1] if self._recent_closes else None
        self._recent_closes.append(close_value)

        if previous is None:
            return self._decision(context, ResearchDispositionKind.NO_ACTION, "insufficient_history")

        crossed_up = previous <= self._threshold < close_value
        crossed_down = previous >= self._threshold > close_value

        if not self._in_position and crossed_up:
            self._in_position = True
            return self._decision(context, ResearchDispositionKind.ENTER_LONG, "threshold_cross_up")
        if self._in_position and crossed_down:
            self._in_position = False
            return self._decision(context, ResearchDispositionKind.EXIT, "threshold_cross_down")
        return self._decision(context, ResearchDispositionKind.NO_ACTION, "no_cross")

    def _decision(self, context, disposition: ResearchDispositionKind, reason_code: str) -> ResearchDecision:
        return ResearchDecision(
            occurred_at=context.occurred_at,
            realization_id=self._realization_id,
            disposition=disposition,
            reason_codes=(reason_code,),
            context_fingerprint=context.context_fingerprint,
        )
