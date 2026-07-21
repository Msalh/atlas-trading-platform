"""
Strategy Engine - Phase N3. Consumes atlas.replay_engine.models.ReplayFrame
(the aligned MarketState/RuleEngineOutput/SetupEngineOutput/MarketContext
bundle for one historical bar) and produces an immutable StrategyDecision -
an evaluation result, never an order. Pure, deterministic, immutable,
replay-safe, side-effect-free, versioned, auditable, plugin-based.

Strategy Engine never recomputes MarketState, Rule Engine facts, Setup
Engine setups, or Market Context - every StrategyDecision is derived
entirely from a ReplayFrame's own already-computed fields. It never
depends on an LLM.

Sprint 1 scope only: models.py (StrategyDirection, StrategyDisposition,
StrategyDecision) and ports.py (the StrategyPlugin Protocol). No
service.py, no concrete strategy, no ReplaySession dependency, no paper
trading, execution, broker integration, or live trading - see the Phase
N3 architecture report for the full reasoning behind each Sprint 1 design
choice (Protocol over ABC, single-ReplayFrame evaluation over a windowed
sequence, open string reason/setup identifiers over a closed enum).

Strategy Engine may depend only on atlas.replay_engine.models,
atlas.setup_engine.models, atlas.market_context.models, atlas.core
primitives where genuinely needed, and the Python standard library -
never atlas.market_engine, atlas.rule_engine, repositories, the API,
events, execution, paper trading, brokers, LLM services, the research
engine, or market data providers.
"""
