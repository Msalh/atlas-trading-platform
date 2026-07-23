"""
Phase N4 Sprint 7 (Ranking). An organizational layer, not a scientific
scoring layer - see the Sprint 7 architectural review for the full
reasoning this package implements exactly.

--- Why no scientific score is computed ---

Every quantitative signal that could be built from ValidationResult's
current, frozen shape (a relative margin, effect size, a p-value) is
confounded by the hypothesis author's own choice of threshold in their
AcceptanceCriterion: a hypothesis authored against a deliberately low bar
would score higher than a more rigorously-authored one testing a
genuinely stronger effect against a harder bar, purely as an artifact of
how the criterion was phrased, not of the evidence's true strength. That
is not a minor imprecision to accept for v1 - it disqualifies every
currently-available signal from honestly representing "scientific
quality." Introducing one anyway would be worse than not ranking by
quality at all: a false signal shaped like a real one, which a future
reader (or eventually Promotion) would trust more than it deserves.
Sprint 8 (Realizations, backtests) and Sprint 9 (Promotion, human
judgment) are where grounded, cross-hypothesis-comparable signals are
supposed to enter - not here.

Ranking therefore does exactly three things: filters to
verdict == SUPPORTED (Validation's own, already-decided scientific
judgment - never recomputed, never reinterpreted, never overridden);
orders the eligible entries by a purely organizational, non-evaluative
basis (validated_at descending - most recently validated first - tied by
hypothesis_id ascending, a total, deterministic order); and records the
result as an immutable, versioned LeaderboardSnapshot. It never builds an
Experiment, computes a Feature, runs statistics, calls AI, or promotes
anything.

LeaderboardEntry.score is a required float on a frozen Sprint 1 type -
Ranking sets it to the constant 1.0 for every eligible entry, never a
rank-derived transform (which would falsely imply the gaps between
adjacent entries are meaningful, when they are really just "validated a
few seconds apart"). It is a compatibility placeholder only, carrying
zero scientific meaning - `score_description` says so explicitly, on
every entry.

rank() is pure (no Ledger access - it receives an already-gathered
tuple[ValidationResult, ...], mirroring atlas.research.validation.validate()'s
own precedent exactly). snapshot_leaderboard() is the one function that
touches the Ledger, via the Sprint 2 LeaderboardSnapshotStore Protocol -
no second, competing persistence abstraction is introduced.

batch_size correctness (whether multiple_testing_correction was honestly
applied) remains, as in Sprint 6, an orchestration responsibility outside
what this package can verify - Ranking trusts the ValidationResult it
receives completely and never reopens Validation's own internals.
"""
