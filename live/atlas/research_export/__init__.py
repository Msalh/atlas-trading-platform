"""
UI v2. Additive, read-only export of the frozen RE-1/RE-2 baseline for the
Market Intelligence Dashboard's FROZEN track.

This package NEVER modifies, and is never imported by,
atlas.research.statistical_profiling (RE-1) or atlas.research.setup_profiling
(RE-2) - it reads their already-computed, already-frozen dataclasses and
serializes them. No new statistic, aggregation, or threshold is computed
anywhere in this package; every figure it emits already exists in the
checked-in RE1_*.md / RE2_*.md reports.

See docs/ui_v2/market-intelligence-dashboard-architecture.md §5 for the
full design (deterministic payload / dynamic export metadata split,
provenance fields, typed warnings, single-pass substrate requirement).
"""
