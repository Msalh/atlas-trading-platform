"""
Sprint RE-2 (Research Engine Phase 2). Descriptive Setup Profiling - episode-
aware statistical characterization of Setup Engine outputs (activation
frequency, persistence, time concentration, clustering, pairwise overlap,
activation context, and episode-level transitions).

Explicitly NOT profitability, expectancy, alpha, forward-return, MFE/MAE, or
win-rate analysis: nothing in this package reads a MarketState past the bar
being described or computes a price outcome. Every value here is a count,
duration, rate, or association measure over already-computed, already-
deterministic SetupOutcome/FactOutcome values - the same purely-observational
boundary atlas.research.statistical_profiling (RE-1) establishes one sibling
package over.

Reuses, unchanged: atlas.setup_engine.service.build_setup_engine_output_window
and atlas.rule_engine.service.build_rule_engine_output_window (never a second
setup/fact evaluator - no setup-detection logic is duplicated here),
atlas.profiling.service.filter_input_states/.segment_by_gap (never a second
gap-detection implementation), and
atlas.research.statistical_profiling.models.RunManifest (read-only reuse of a
metadata shape - RE-1's frozen computation core is never modified or moved by
this package).

trend_1m is never read anywhere in this package - it is not one of the 7
registered Rule Engine facts these structures read from RuleEngineOutput.facts,
so its exclusion is structural, not a rule that has to be remembered.
"""
