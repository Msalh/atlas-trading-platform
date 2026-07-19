"""
TICK_SIZE - relocated here in Sprint 4 from
atlas/market_engine/adapters/tradingview/translator.py (Sprint 2), where it
originally lived because it had exactly one consumer. Sprint 4's read path
(atlas/market_engine/repositories/postgres.py) needs the identical constant to
reconstruct Price from stored floats, and importing it from one specific
adapter would make the repository depend on that adapter - backwards, since a
future second adapter's data must read back through the same repository
without the repository caring which adapter wrote it. This module is the
neutral home both the write path and the read path import from.

Still a documented placeholder, not a design decision made fresh here: MNQ/NQ's
tick size (0.25) is hardcoded the same way in tools/research/execution_model.py
("a platform fact, not a sweep parameter"). Building a real per-instrument
tick-size registry ahead of a second real instrument would be exactly the
speculative abstraction the project charter prohibits - replaced only when a
second instrument makes a registry a genuine need.
"""

TICK_SIZE = 0.25  # MNQ/NQ - see this module's docstring
