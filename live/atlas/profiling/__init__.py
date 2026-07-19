"""
Sprint 24B/24C. Historical fact and setup profiler - a deterministic,
observational-only analysis layer sitting ABOVE Market Engine, Rule Engine,
and Setup Engine (imports all three; none of them import this package - see
this Sprint's own dependency-boundary verification).

Reports how often the current Rule Engine facts and Setup Engine setups
compute, fire, overlap, and encounter insufficient data over real historical
MarketState data. Never interprets those counts as a trading signal,
confidence score, or profitability claim - see atlas.profiling.service's own
module docstring and docs/market_engine/roadmap.md's Sprint 24B/24C entries
for the full design boundary.

Public entry points: atlas.profiling.service.profile_market_state_series
(pure) and .profile_market_state_range (repository-backed). Report shape:
atlas.profiling.models.ProfilingReport, serialized via
atlas.profiling.serialization.profiling_report_to_dict.
"""
