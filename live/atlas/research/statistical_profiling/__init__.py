"""
Sprint RE-1 (Research Engine Phase 1) - statistical characterization of the
Market State itself, via already-computed Rule Engine fact outputs.

Explicitly NOT profitability, expectancy, or forward-return analysis - see
service.py's own module docstring for the full boundary statement. Every
value this package produces is a count, rate, distribution, or association
measure over already-deterministic Rule Engine outputs; nothing here reads
or infers a forward price outcome.

Sits above atlas.rule_engine and atlas.profiling (reuses
atlas.profiling.service.segment_by_gap and
atlas.rule_engine.service.build_rule_engine_output_window unchanged, and
atlas.profiling.service.profile_market_state_series for base fact
frequency/true-false numbers - never re-derives what those already compute
correctly). Sibling to atlas.research's Hypothesis/Experiment machinery
(Sprint 28), not a replacement for it - this package characterizes the
DATA; Sprint 28's Research Engine machinery evaluates HYPOTHESES against
that characterization later.

Public entry point: build_statistical_profile() (pure) in service.py.
Domain types: models.py. Markdown rendering: reports.py.
"""
