"""
Atlas domain kernel. Zero dependencies on anything else in this system - no FastAPI,
no psycopg, no other atlas.* package. Every other package depends on this one;
this one depends on nothing.

Not wired into atlas.main yet (Sprint 1 of the roadmap) - nothing outside
atlas.core and its own tests imports this package until atlas.market_engine
(Sprint 2) exists to consume it.
"""
