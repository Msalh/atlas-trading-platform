"""
Sprint 12: the actual tunable values for each fact, separated from
atlas.rule_engine.facts' evaluation logic - see FactDefinition's docstring in
models.py for why. Every value below is an unvalidated starting heuristic, not
measured against real data (no production traffic has ever exercised this
system) - see docs/market_engine/rule-fact-inventory.md and Sprint 11/12's own
Engineering Heuristics review sections.

DEFAULT_REJECTION_DEFINITION sources its tick_size from
atlas.market_engine.constants.TICK_SIZE - the existing single source of truth
for this instrument's tick size (Sprint 4) - rather than duplicating the
number here. It is still explicit, named metadata on the definition (not an
unexplained constant buried inside an evaluator), it is just SOURCED from the
one place this project already tracks tick size, so the two can never drift
independently.
"""
from atlas.market_engine.constants import TICK_SIZE
from atlas.rule_engine.models import FactDefinition

DEFAULT_VOLUME_SPIKE_DEFINITION = FactDefinition(
    name="volume_spike",
    version="1.0",
    params={"threshold": 1.5},
)

DEFAULT_DISPLACEMENT_DEFINITION = FactDefinition(
    name="displacement",
    version="1.0",
    params={"threshold": 1.5},
)

DEFAULT_REJECTION_DEFINITION = FactDefinition(
    name="rejection",
    version="1.0",
    params={"wick_body_ratio_threshold": 2.0, "tick_size": TICK_SIZE},
)

# Sprint 13: the first three facts needing a WINDOW of MarketState, not just
# the current bar - see atlas.rule_engine.facts' module docstring for the
# window-ordering convention (ascending, current bar last) all three share.

DEFAULT_TREND_5M_DEFINITION = FactDefinition(
    name="trend_5m",
    version="1.0",
    params={"window": 20, "up_threshold": 1.0, "down_threshold": -1.0},
)

DEFAULT_LIQUIDITY_SWEEP_DEFINITION = FactDefinition(
    name="liquidity_sweep",
    version="1.0",
    params={"window": 3},
)

# window=3 here is a disclosed, unvalidated default, NOT specified in the
# approved reclaim definition (unlike liquidity_sweep's explicit "three-bar
# resolution window") - chosen to match liquidity_sweep's window for
# consistency among the two remaining liquidity-interaction facts, pending
# real data.
DEFAULT_RECLAIM_DEFINITION = FactDefinition(
    name="reclaim",
    version="1.0",
    params={"window": 3},
)

# Sprint 22B. threshold=1.0 is a provisional, EXPLICITLY UNVALIDATED heuristic
# (same disclosed status as every value in this file) - borrowed from
# trend_5m's own up_threshold/down_threshold shape (the closest existing
# precedent: ATR-normalized distance, symmetric threshold, three-way
# classification), not from displacement's single-boolean threshold (1.5),
# which is a structurally different kind of classification. No history
# window needed - single current bar, same shape as volume_spike/
# displacement/rejection.
DEFAULT_VWAP_RELATIONSHIP_DEFINITION = FactDefinition(
    name="vwap_relationship",
    version="1.0",
    params={"threshold": 1.0},
)
