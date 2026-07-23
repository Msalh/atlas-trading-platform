"""
Phase N4 Sprint 9 (Promotion, Milestone: Phase N4 Core certification).
The mandatory human review gate - the one required step between a
validated, ranked research result and a human's permanent decision about
it. See docs/phase-n4-research-engine-blueprint.md §8's own pipeline
diagram: this package builds exactly one node, "Human Promotion Review" -
never the separate, later, human-led Production Certification Sprint that
follows it, and never Strategy Engine itself.

list_promotion_candidates() is a pure, read-only query - there is no
PENDING_REVIEW state anywhere in this system to transition into or out of
(PromotionRecordTracker's own docstring, Sprint 2: "there is no
PENDING_REVIEW state represented here"). The review queue is computed,
not stored: LeaderboardSnapshot entries with SUPPORTED-verdict backing
that have no existing APPROVED PromotionRecord yet. A prior DECLINED or
DEFERRED decision is retained and surfaced alongside a candidate, never
hidden (Research Engine Design Principles V.3; the blueprint's own
DEFERRED-can-re-enter-review lifecycle) - only an existing APPROVED
decision excludes a candidate, since re-reviewing an already-promoted
result has nothing left to decide.

record_decision() is the one function that writes - constructs and
records a PromotionRecord via the Sprint 2 PromotionRecordStore, unused by
any real caller until now. The decision itself is never computed: a
human's rationale and reviewer identity are required, non-blank inputs
(PromotionRecord.__post_init__, already enforced since Sprint 1), never
defaulted or inferred. The blueprint's own AI-assistant permission list is
explicit that even a future AI may never "create or approve a
PromotionRecord" - this remains true here too; nothing in this package
computes a decision, only records one already made.

resulting_production_change_ref (Optional[str] on the frozen
PromotionRecord type) is deliberately never populated by this package -
Research must know nothing about production artifacts. The relationship
runs one way only: a future Production Certification process references
a promotion_id from its own records; PromotionRecord never references
anything about production. This preserves complete separation between
Research and Production, the same posture Principle VIII.4 already
enforces at the code-dependency level, extended here to the data level.

Dependencies: atlas.research.models/.ports/.fingerprint only - the same
"none new" footprint the frozen roadmap's own Sprint 9 entry states.
ValidationResult and LeaderboardSnapshot are plain types owned by
atlas.research.models, not by atlas.research.validation/.ranking
themselves, so this package needs neither of those packages directly.
Never imports atlas.research.backtesting/.statistics/.experiment_builder,
and never atlas.strategy_engine/atlas.api/atlas.main - see
test_research_promotion_dependencies.py for the mechanical proof, both
directions.
"""
