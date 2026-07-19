"""
Market Engine: the perception layer - records what the market did, in canonical
form, replayably. Depends only on atlas.core. Nothing outside this package and
its own tests imports it yet (Sprint 2) - no database, no API, no wiring into
atlas.main. See docs/architecture (project history) for the full package's
eventual scope; this Sprint builds only its canonical model, one adapter, and an
in-memory repository.
"""
