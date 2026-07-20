"""
UI v2, amendments 1 and 3. Data shapes for live-window episode projection -
kept entirely outside atlas.research.setup_profiling (RE-2), per
architecture doc §4.

LeftBoundaryReason / LiveTerminationReason are deliberately NOT RE-2's own
TerminationReason: a live window has no dataset_end concept (there is
always more data coming), and needs a genuine "still open" state RE-2's
frozen model never has (every historical SetupEpisode is closed by
construction - RE-2 only ever runs against a complete, already-ended
dataset). Reusing RE-2's enum here would silently blur that distinction.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Optional

from atlas.research.setup_profiling.models import RegisteredFactSnapshot

__all__ = [
    "RegisteredFactSnapshot",
    "LeftBoundaryReason",
    "LiveTerminationReason",
    "LiveEpisodeProjection",
    "LiveComputabilitySummary",
    "LiveSetupSnapshot",
    "SegmentBoundary",
    "LiveActivationEvent",
    "LiveWindowResult",
]


def _frozen_mapping(source: Mapping) -> MappingProxyType:
    return MappingProxyType(dict(source))


class LeftBoundaryReason(str, Enum):
    """Why an episode's left (activation) boundary is - or is not -
    genuinely known, given a bounded live query window. Only
    observed_activation and insufficient_data carry a real
    activation_timestamp_observed; segment_start and query_window_start
    both leave it null, but for different reasons (architecture §4.1)."""

    OBSERVED_ACTIVATION = "observed_activation"
    INSUFFICIENT_DATA = "insufficient_data"
    SEGMENT_START = "segment_start"
    QUERY_WINDOW_START = "query_window_start"


class LiveTerminationReason(str, Enum):
    """Why an episode's right (ending) boundary was observed as real,
    within the live window - only ever populated when is_active=false.
    No dataset_end value here (see module docstring) and no member at all
    for "still open" - that is is_active=true with termination_reason
    absent entirely, never a fabricated enum member standing in for
    "unknown"."""

    BECAME_FALSE = "became_false"
    INSUFFICIENT_DATA = "insufficient_data"
    SEGMENT_END = "segment_end"


@dataclass(frozen=True)
class LiveEpisodeProjection:
    """One setup's one episode, as observed within a bounded live window.
    Amendment 3's UI rule: while is_active=true, end_timestamp_observed
    and termination_reason are ALWAYS None - never presented as a real
    ending - and duration_bars_observed / activation_timestamp_observed
    follow the same left-boundary rules as a closed episode."""

    setup_name: str
    segment_id: str

    # Left boundary (amendment 1).
    left_boundary_reason: LeftBoundaryReason
    activation_timestamp_observed: Optional[str]
    observed_start_timestamp: str
    duration_bars_observed: int
    is_window_truncated: bool

    # Right boundary (amendment 3).
    is_active: bool
    last_observed_timestamp: str
    end_timestamp_observed: Optional[str]
    termination_reason: Optional[LiveTerminationReason]
    right_boundary_observed: bool

    is_continuation: bool
    start_state: RegisteredFactSnapshot
    end_state: RegisteredFactSnapshot

    def __post_init__(self) -> None:
        if self.is_active:
            if self.end_timestamp_observed is not None:
                raise ValueError("end_timestamp_observed must be None while is_active=True")
            if self.termination_reason is not None:
                raise ValueError("termination_reason must be None while is_active=True")
            if self.right_boundary_observed:
                raise ValueError("right_boundary_observed must be False while is_active=True")
        else:
            if self.end_timestamp_observed is None:
                raise ValueError("end_timestamp_observed must be set once is_active=False")
            if self.termination_reason is None:
                raise ValueError("termination_reason must be set once is_active=False")
            if not self.right_boundary_observed:
                raise ValueError("right_boundary_observed must be True once is_active=False")
        if self.left_boundary_reason in (LeftBoundaryReason.SEGMENT_START, LeftBoundaryReason.QUERY_WINDOW_START):
            if self.activation_timestamp_observed is not None:
                raise ValueError(f"activation_timestamp_observed must be None when left_boundary_reason={self.left_boundary_reason.value}")
        else:
            if self.activation_timestamp_observed is None:
                raise ValueError(f"activation_timestamp_observed must be set when left_boundary_reason={self.left_boundary_reason.value}")
        if self.left_boundary_reason == LeftBoundaryReason.QUERY_WINDOW_START and not self.is_window_truncated:
            raise ValueError("is_window_truncated must be True when left_boundary_reason=query_window_start")


@dataclass(frozen=True)
class LiveComputabilitySummary:
    computable_bars: int
    non_computable_bars: int
    detected_true_bars: int
    detected_false_bars: int
    insufficient_reason_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "insufficient_reason_counts", _frozen_mapping(self.insufficient_reason_counts))


@dataclass(frozen=True)
class LiveSetupSnapshot:
    setup_name: str
    current_episode: Optional[LiveEpisodeProjection]
    recent_episodes: tuple[LiveEpisodeProjection, ...]  # always is_active=False
    computability: LiveComputabilitySummary


@dataclass(frozen=True)
class SegmentBoundary:
    segment_id: str
    start_timestamp: str
    end_timestamp: Optional[str]  # None only for the window's own last (still-open) segment


@dataclass(frozen=True)
class LiveActivationEvent:
    timestamp: str
    segment_id: str
    activated_setups: tuple[str, ...]  # sorted alphabetically, same display-only convention as RE-2's own


@dataclass(frozen=True)
class LiveWindowResult:
    requested_window: int
    actually_used_window: int
    data_as_of: str  # occurred_at of the latest evaluated bar (architecture §2.1)
    setups: Mapping[str, LiveSetupSnapshot]
    segments: tuple[SegmentBoundary, ...]
    activation_events: tuple[LiveActivationEvent, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "setups", _frozen_mapping(self.setups))
