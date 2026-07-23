"""
Sprint 8.2 (Railway Staging Deployment). Infrastructure-only glue between
atlas.main's startup sequence and the Research Ledger's nine JSONL stores
(atlas.research.stores) - never a research package itself, and never
imported by one. This is the one-way boundary the Sprint 8.2 architectural
review names explicitly: every dependency-audit test built across Sprints
1-8.1 governs imports *within* atlas/research/** (which research package
may import which sibling); this package sits entirely outside that audited
tree, importing FROM atlas.research.stores/.models the same way
atlas.research_export/atlas.live_view already call into their own domains
without those domains knowing an HTTP/deployment layer exists. See
test_research_deploy_dependencies.py for the mechanical proof that nothing
under atlas/research/** ever imports this package back.

check_ledger_storage() (startup_check.py) mirrors
atlas.research_export.startup_check.check_snapshots()'s exact shape and
"never block LIVE, never crash startup" contract, applied to the write side
instead of the read side: a real write-then-delete of a sentinel file,
never a hard startup failure. build_startup_report() renders the
one-time, human-readable "Research Startup" block atlas.main's lifespan
logs exactly once per process start.
"""
