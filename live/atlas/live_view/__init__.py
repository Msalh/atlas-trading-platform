"""
UI v2. Additive, live-window projection of Setup Engine episode state for
the Market Intelligence Dashboard's LIVE track.

This package NEVER modifies, and is never imported by,
atlas.research.setup_profiling (RE-2) - it reads RE-2's own already-frozen
build_setup_profiling_dataset() output (a real, exact reuse of RE-2's
episode-construction logic, unchanged) and translates it into a separate
projection model with its own left-boundary AND right-boundary semantics,
because a live window's "is this episode's start/end real, or just where
my query happened to begin/end" question is a genuinely different concept
from RE-2's frozen SetupEpisode, which only ever describes a complete,
already-ended historical dataset. See
docs/ui_v2/market-intelligence-dashboard-architecture.md §4 for the full
design.

No new statistic, aggregation, or threshold is computed anywhere in this
package - every field on LiveEpisodeProjection is either read directly
from RE-2's own SetupEpisode/ComputabilityRecord objects, or a simple,
undisputed translation of one (e.g. TerminationReason.DATASET_END on the
episode covering the window's own latest bar means "still active", not a
new judgment call).
"""
