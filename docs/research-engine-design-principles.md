# Research Engine Design Principles

**Status:** Constitutional reference — permanent, amend only deliberately
**Date:** 2026-07-21
**Scope:** `live/atlas/research/` and everything built under it, for the life of the platform

## Preamble

Phase N4's master blueprint (`docs/phase-n4-research-engine-blueprint.md`) describes *what* the Research Engine is. This document describes what it must **always remain**, regardless of what it becomes. Packages will be renamed. Storage will change. The AI models involved will be replaced more than once. None of that may touch what is written here.

Every principle below follows the same five-part form: the rule, why it exists, the architectural mistake it exists to prevent, an example of following it, and an example of violating it. A pull request that violates any rule below is violating the architecture, independent of how well-intentioned, well-tested, or clever the change is. When a future situation isn't explicitly covered, resolve it in the direction these principles point, not in the direction that's fastest to ship.

---

## I. Research Philosophy

### I.1 — Hypotheses, not strategies, are the center of gravity
**Rule:** Every unit of research work exists to test a claim. No object may enter the system whose only purpose is "a rule to trade."
**Why:** A strategy-first system can only ever grade ideas a human already had. A hypothesis-first system can also discover ideas nobody thought to test.
**Prevents:** Strategy-first design — the single anti-pattern this entire platform was re-architected to avoid.
**Correct:** A researcher registers "displacement following a liquidity sweep produces excess forward return in compressed regimes" and only later decides whether that becomes a rule.
**Violation:** A researcher writes a parametrized trading rule first, then backfills a "hypothesis" record to satisfy the schema.

### I.2 — A strategy is a consequence of knowledge, never its starting point
**Rule:** `Realization` objects (including `StrategyVariant`) may only be constructed from an already-registered `Hypothesis`.
**Why:** If a strategy can exist without a claim behind it, the whole falsifiability discipline becomes optional in practice.
**Prevents:** Ad hoc strategy authoring that quietly bypasses the hypothesis ledger.
**Correct:** `experiment_builder` refuses to construct a `Realization` without a `hypothesis_ref`.
**Violation:** A "quick backtest" tool that runs a rule against history with no hypothesis behind it at all, "just to see."

### I.3 — The product is knowledge, not strategies
**Rule:** Success is measured by what has been learned — including what has been ruled out — never by strategy count.
**Why:** A metric of "strategies shipped" incentivizes exactly the shortcut this document exists to prevent.
**Prevents:** Organizational pressure to skip rigor in order to produce something promotable.
**Correct:** A quarter with zero promotions but fifty well-documented rejected hypotheses is a successful quarter.
**Violation:** Reporting research progress by strategy count rather than by hypotheses tested.

### I.4 — An idea producing no working strategy is not a failed research program
**Rule:** A `REJECTED` or purely descriptive `Hypothesis` with no `Realization` is a complete, successful unit of work.
**Why:** Otherwise every non-actionable finding is quietly treated as wasted effort, which pressures researchers to force actionability onto findings that don't have it.
**Prevents:** Pressure to manufacture a strategy from a finding that was never meant to be one (e.g., a pure risk/context finding).
**Correct:** "Session open causes elevated volatility" ships as a risk-input finding, never forced into a synthetic entry rule.
**Violation:** A researcher invents an arbitrary entry/exit rule around a purely descriptive finding just so it has a `Realization`.

---

## II. Knowledge Philosophy

### II.1 — Negative results are permanent knowledge
**Rule:** `REJECTED`, `DECLINED`, `DISMISSED`, and `DUPLICATE` records are never deleted.
**Why:** A negative result is exactly as much institutional memory as a positive one — its entire value is preventing the same dead idea from being re-tested.
**Prevents:** Survivorship-shaped data that forgets everything except what worked.
**Correct:** A hypothesis rejected in year one is still queryable and still surfaces as a duplicate warning in year five.
**Violation:** A cleanup script that purges "old, unsuccessful" experiments to save storage.

### II.2 — Nothing formalized is ever forgotten; only ephemeral, unformalized findings may expire
**Rule:** Retention/expiry policy applies exclusively to `Finding`s that were never formalized into a `Hypothesis`. Everything downstream of formalization is permanent.
**Why:** Discovery must be allowed to be cheap and high-volume, which requires somewhere for the noise to eventually go — but only the noise, never a tested claim.
**Prevents:** Either unbounded storage growth from raw findings, or accidental loss of real, tested knowledge.
**Correct:** An unreviewed Finding older than its retention window is pruned; the Hypothesis it might have become, once formalized, never is.
**Violation:** A single retention policy applied uniformly to Findings and Hypotheses alike.

### II.3 — Superseding a conclusion creates a link, never a deletion
**Rule:** When a hypothesis is refined or replaced, the old record is marked `SUPERSEDED` and linked forward. It is never overwritten or removed.
**Why:** The history of how understanding evolved is itself research-relevant; overwriting it destroys that record.
**Prevents:** Silent rewriting of research history to make past work look more polished than it was.
**Correct:** `Hypothesis v2` carries a `supersedes: Hypothesis v1` pointer; both remain queryable forever.
**Violation:** Editing a hypothesis's statement in place once a refinement is found.

### II.4 — Duplicate research must be detectable before it is repeated
**Rule:** Formalizing a new hypothesis requires a similarity check against the existing ledger, including rejected entries, before registration.
**Why:** A ledger nobody can query before acting on it provides none of the protection permanence is meant to buy.
**Prevents:** Re-testing the same idea under a different name every few months.
**Correct:** A proposed hypothesis surfaces three structurally similar prior hypotheses, two rejected, before it is registered.
**Violation:** Registering hypotheses purely by exact-text match, or not checking at all.

---

## III. Evidence Philosophy

### III.1 — Evidence is computed, not judged
**Rule:** The act of running an experiment produces `Evidence`; it never simultaneously produces a verdict.
**Why:** Conflating computation and judgment is exactly the mistake this platform has avoided at every certified layer (`FactResult` vs. `SetupResult` vs. `SetupInterpretation`); Evidence is that same split one level up.
**Prevents:** A statistic quietly doubling as an unexamined pass/fail decision.
**Correct:** `atlas.research.statistics` computes an effect size; `atlas.research.validation` separately decides whether it clears the bar.
**Violation:** An experiment runner that returns `passed: bool` directly, with no separate, inspectable judgment step.

### III.2 — Evidence is immutable once created
**Rule:** An `Evidence` record is never edited after creation. A correction is new Evidence, linked to what it corrects.
**Why:** Mutable evidence means the historical record of what was actually observed can silently change underneath a conclusion built on it.
**Prevents:** Retroactive "cleanup" of inconvenient results.
**Correct:** A bug in a metric calculation is fixed by producing new Evidence from a re-run, not by patching the old row.
**Violation:** An UPDATE statement (of any kind, in any storage technology) applied to an existing Evidence record's metrics.

### III.3 — Every piece of evidence is traceable to the exact experiment, dataset, and code that produced it
**Rule:** Evidence always carries its `experiment_ref`, and through it, a dataset manifest and a `code_version`.
**Why:** A number with no lineage cannot be trusted or reproduced, and cannot be distinguished from a number produced by a since-fixed bug.
**Prevents:** Orphaned statistics nobody can explain or re-derive.
**Correct:** Every Evidence record resolves, unambiguously, to one Experiment fingerprint.
**Violation:** A statistics dashboard that displays numbers with no link back to the experiment that produced them.

### III.4 — Absence of data is not evidence of absence
**Rule:** Insufficient data must be modeled as its own explicit outcome, never silently coerced into a negative result.
**Why:** This is the same discipline Rule Engine's `InsufficientData` has enforced from the platform's very first certified layer — collapsing "couldn't be measured" into "measured as false" hides a data problem behind what looks like a market observation.
**Prevents:** A hypothesis being wrongly rejected because the dataset was too short to test it, not because the claim was false.
**Correct:** A criterion evaluated against a fact with `InsufficientData` returns `INCONCLUSIVE`, never `NOT_SUPPORTED`.
**Violation:** Treating a missing or unmeasurable value as a numeric zero or as automatic falsification.

---

## IV. Validation Philosophy

### IV.1 — Discovery and validation are different activities and must remain structurally separate
**Rule:** Nothing produced by Discovery Engine may be treated as validated. A `Finding` and a `ValidationResult` are different types, produced by different, non-overlapping code paths.
**Why:** Discovery must be free to be loose, cheap, and mostly wrong, because that is what real exploration requires; validation must be free to be strict, because that is what real proof requires. One process cannot safely be both.
**Prevents:** An exploratory statistical artifact quietly being treated as tested knowledge.
**Correct:** A Finding with an eye-catching correlation sits as unformalized data until it passes through formalization and a full validation pipeline.
**Violation:** A dashboard that surfaces raw Discovery output as "validated patterns."

### IV.2 — Acceptance criteria are declared before evidence is examined, never fitted to it afterward
**Rule:** A hypothesis's `AcceptanceCriterion` is fixed at formalization time, before any experiment against it is run.
**Why:** Choosing or adjusting the bar after seeing the result is p-hacking with extra steps — it guarantees a favorable outcome rather than testing for one.
**Prevents:** Hypothesizing After Results are Known (HARKing), the most common way "significant" findings turn out to be noise.
**Correct:** The criterion "excess return exceeds X with p < 0.01" is locked in before the experiment runs, win or lose.
**Violation:** Loosening a significance threshold after an experiment narrowly misses it, then re-declaring success.

### IV.3 — No hypothesis is validated on in-sample evidence alone
**Rule:** `VALIDATED` requires out-of-sample or walk-forward evidence, not merely a good fit to the data the hypothesis was formed from.
**Why:** A pattern can always be found in the exact data used to find it; that tells you nothing about whether it generalizes.
**Prevents:** Overfitting a hypothesis to the one dataset it was mined from.
**Correct:** A hypothesis discovered on 2023–2024 data is required to hold on a genuinely held-out 2025 fold before validation.
**Violation:** Validating a hypothesis using only the same window Discovery Engine used to find it.

### IV.4 — Multiple-testing correction is mandatory whenever many hypotheses are tested against shared data
**Rule:** Any experiment batch testing more than one hypothesis against overlapping data must apply an explicit correction before any individual result is treated as significant.
**Why:** Testing thousands of feature combinations against one dataset guarantees some fraction of "significant" results are pure chance; this is the single most common way a discovery-heavy platform fools itself at scale.
**Prevents:** False-discovery inflation from high-volume, automated hypothesis generation.
**Correct:** A batch of 500 Discovery-sourced hypotheses has its significance thresholds adjusted for the number tested before any is promoted toward validation.
**Violation:** Treating each hypothesis's p-value as if it were the only test ever run against that dataset.

### IV.5 — A validation verdict always carries its statistical justification; a bare boolean is not a verdict
**Rule:** `ValidationResult` must record the criteria applied, the evidence used, and the reasoning — never a standalone `SUPPORTED`/`NOT_SUPPORTED` flag with nothing behind it.
**Why:** A verdict without justification cannot be audited, reproduced, or challenged later — it becomes an assertion the platform must simply be trusted on.
**Prevents:** Unauditable, "trust me" conclusions.
**Correct:** A `ValidationResult` links to the exact Evidence, the exact criterion values, and the correction method applied.
**Violation:** A validation step that stores only `passed = true`.

---

## V. Promotion Philosophy

### V.1 — Human approval is mandatory before production, without exception
**Rule:** No path — automated, AI-assisted, or otherwise — may promote a Realization to production without a `PromotionRecord` created by a human.
**Why:** This is the one non-negotiable point of human accountability in the entire pipeline; removing it removes the platform's only safeguard against its own automation.
**Prevents:** Automatic promotion, however confident the automated validation appears.
**Correct:** A hypothesis with overwhelming statistical support still stops at `PROMOTION_CANDIDATE` until a human reviews and approves it.
**Violation:** A "high-confidence auto-promote" feature that skips human review for sufficiently strong results.

### V.2 — Every promotion is explainable
**Rule:** A `PromotionRecord` requires a mandatory, human-written rationale and a pinned snapshot of the exact evidence reviewed.
**Why:** A promotion decision that can't be explained later can't be audited, learned from, or defended when questioned.
**Prevents:** Undocumented, ad hoc promotions that nobody can reconstruct the reasoning behind.
**Correct:** Two years later, a reviewer can read exactly why a strategy was approved and exactly what evidence justified it at the time.
**Violation:** A promotion approved with no recorded rationale, or with a rationale added after the fact from memory.

### V.3 — A declined promotion is as permanent and valuable as an approved one
**Rule:** `DECLINED` promotion records are retained forever, with the same rigor as `APPROVED` ones.
**Why:** Otherwise the same rejected idea can be resubmitted repeatedly until someone forgets it was already declined.
**Prevents:** Promotion review fatigue turning into accidental re-approval of previously rejected work.
**Correct:** A resubmitted, lightly-reworded version of a declined strategy is flagged against its prior decline record before review.
**Violation:** Deleting declined promotion records because "nothing came of them."

### V.4 — Promotion rigor never varies by origin
**Rule:** A human-authored, Discovery-sourced, and AI-proposed hypothesis face the identical validation and promotion bar.
**Why:** Any origin-based shortcut creates an incentive to route ideas through whichever path has the weaker bar.
**Prevents:** A two-tier system where AI- or discovery-sourced findings are held to a lower (or, just as dangerous, an automatically higher and unfairly dismissive) standard than human ones.
**Correct:** An AI-proposed hypothesis and a human-proposed hypothesis pass through the exact same funnel stages.
**Violation:** A "fast lane" that promotes AI-sourced findings with lighter review because the AI's confidence score was high.

---

## VI. AI Philosophy

### VI.1 — AI may propose; it may never validate
**Rule:** No AI output may set a `Hypothesis` status to `VALIDATED` or `REJECTED`, or otherwise stand in for the statistics/validation pipeline.
**Why:** Validation must remain a deterministic, auditable, criterion-driven process; an AI judgment is neither deterministic nor fully auditable in the same sense.
**Prevents:** Statistical rigor being quietly replaced by a model's opinion.
**Correct:** An AI-proposed hypothesis still runs through `atlas.research.statistics`/`validation` like any other.
**Violation:** An AI assistant that outputs "this hypothesis is validated" and that status is accepted directly.

### VI.2 — AI never makes or influences a trading decision, directly or indirectly
**Rule:** No AI-authored object may reach Strategy Engine, Replay Engine, or any execution path without passing through the full, unmodified human-gated pipeline first.
**Why:** This is the platform's hardest boundary, stated explicitly by design from the outset — the Research Engine's purpose is knowledge discovery, not delegated trading authority.
**Prevents:** Any drift toward autonomous AI trading, however indirect or well-intentioned.
**Correct:** An AI-drafted `Experiment` spec is queued and constructed exactly like a human-authored one, with no privileged execution path.
**Violation:** An AI assistant given any code path that reaches a live order, a paper-trading engine, or even a "shadow mode" execution without the same gates.

### VI.3 — AI-authored content is permanently, individually distinguishable by provenance
**Rule:** Every entity carries an immutable `provenance` field, and lineage (`derived_from`) is tracked per version, never once at a root that can go stale.
**Why:** Without this, five years of mixed human/AI contribution becomes an unreconstructable blur, and accountability for any given claim becomes impossible to assign.
**Prevents:** Provenance laundering — an AI-originated idea becoming indistinguishable from a human one after a single edit.
**Correct:** A hypothesis refined by a human from an AI draft shows `provenance: human, derived_from: <ai draft id>`, forever.
**Violation:** A single mutable "author" field that gets overwritten whenever anyone touches the record.

### VI.4 — An AI explanation is a claim, not a fact
**Rule:** AI-authored explanations of findings are stored as annotations, never as statistics, never as validated conclusions.
**Why:** A fluent explanation can sound more convincing than the evidence behind it warrants; treating it as fact would smuggle unvalidated reasoning into the knowledge base.
**Prevents:** Plausible-sounding AI narrative being mistaken for statistical proof.
**Correct:** An AI's explanation of why a pattern might exist is itself eligible to become a new, separately-tested hypothesis.
**Violation:** An AI-generated explanation displayed alongside validated statistics with no visual or structural distinction between the two.

### VI.5 — AI has no write access to any validated or production-adjacent state
**Rule:** AI write permissions are limited to draft objects (status `PROPOSED`) and annotations. It cannot alter Feature registrations, ValidationResults, PromotionRecords, or anything already persisted.
**Why:** Write access is the actual boundary that matters; a read-only-except-drafts AI cannot corrupt the ledger no matter how it is prompted or misused.
**Prevents:** An AI system, however capable, gaining the practical ability to alter historical record or bypass governance.
**Correct:** An AI integration is implemented such that its write path physically cannot reach an already-registered Hypothesis or any Evidence.
**Violation:** An AI assistant granted the same write credentials as the formalization/validation services it is supposed to be advisory to.

---

## VII. Reproducibility Philosophy

### VII.1 — Every experiment is reproducible from its recorded inputs
**Rule:** Given the same `Experiment` fingerprint (hypothesis, realization, dataset manifest, spec, code version, seed), re-running it must produce the same Evidence.
**Why:** Research that can't be reproduced isn't research — it's an anecdote with a timestamp.
**Prevents:** Unverifiable, "trust the number" results.
**Correct:** Re-running a six-month-old experiment against its recorded dataset manifest and code version reproduces its Evidence exactly.
**Violation:** An experiment whose result depends on wall-clock time, ambient system state, or an unrecorded parameter.

### VII.2 — Every stochastic process is explicitly seeded; never sourced from system entropy
**Rule:** Monte Carlo, resampling, and any other randomized method must take an explicit, recorded seed as a required input.
**Why:** Unseeded randomness makes a result unreproducible by definition — the same principle already enforced project-wide since Phase N1.
**Prevents:** "It worked when I ran it" results nobody can verify a second time.
**Correct:** A Monte Carlo validation spec records its seed as part of the Experiment; re-running with that seed reproduces the identical resample sequence.
**Violation:** A validation method that calls a random-number generator without an explicit seed argument.

### VII.3 — Re-running an experiment either reproduces its result exactly or reveals exactly what changed
**Rule:** A reproducibility check is not "close enough" — it either matches exactly, or the system must identify precisely which input (code version, dataset, dependency) differs.
**Why:** Silent drift between two runs of "the same" experiment is far more dangerous than an obvious failure, because it erodes trust in the whole ledger without anyone noticing.
**Prevents:** Undetected reproducibility drift accumulating invisibly over time.
**Correct:** A fingerprint mismatch between two runs is treated as a first-class, investigable event, not silently ignored.
**Violation:** A test suite or research tool that accepts "approximately the same" results as sufficient proof of reproducibility.

### VII.4 — Every output is versioned against the exact code and data that produced it
**Rule:** Every persisted object carries a `schema_version` and is traceable to a `code_version` (and, where relevant, a feature/registry version).
**Why:** Registries and code evolve; without this, an old result becomes impossible to interpret correctly once the code that produced it has changed.
**Prevents:** Silently misinterpreting historical evidence under today's code as if it were produced by today's code.
**Correct:** An Evidence record from eighteen months ago is read alongside its own `code_version`, not assumed to reflect the current registry.
**Violation:** A report or dashboard that displays historical results without any indication of which code version produced them.

---

## VIII. Architecture Philosophy

### VIII.1 — Research never modifies production
**Rule:** No Research Engine code, process, or human working within it may edit Rule Engine, Setup Engine, Setup Interpretation, Replay Engine, Strategy Engine, or Market Context.
**Why:** These packages are certified through a rigorous, real-data process; research's entire value depends on that certification remaining trustworthy and untouched.
**Prevents:** Research convenience quietly eroding production certification.
**Correct:** A new experimental fact lives in `atlas.research.features`, never as an edit to Rule Engine's frozen registry.
**Violation:** "Just this once" adding a research-only parameter to a certified production function.

### VIII.2 — Production never depends on research
**Rule:** No package outside `atlas.research` may import anything from it, ever, without a separate, human-led, fully-certified promotion sprint changing that fact deliberately.
**Why:** If production could import research, research code would inherit production's certification obligations without ever earning them, and a research-only bug could reach live trading.
**Prevents:** Silent contamination of the certified path by exploratory, unaudited code.
**Correct:** A promoted strategy is *reimplemented* by hand in `atlas.strategy_engine`, exactly as Setup Interpretation's own migration did — never imported directly from research.
**Violation:** Strategy Engine importing a `ResearchStrategyPlugin` or any `atlas.research.*` module "temporarily, to save time."

### VIII.3 — Dependency direction is enforced mechanically, not by convention alone
**Rule:** Every dependency boundary in this document must be backed by an automated, AST-based (or equivalent) test that fails the build on violation.
**Why:** A rule enforced only by discipline degrades the moment a deadline is tight; a rule enforced by a failing test does not.
**Prevents:** Boundary erosion that "everyone knows" is wrong but nothing actually stops.
**Correct:** A dependency test asserts zero production imports of `atlas.research`, run on every change, exactly as the equivalent tests already do for every N1–N3 boundary.
**Violation:** A dependency boundary that exists only in a docstring or a design document, with no test enforcing it.

### VIII.4 — Research objects are never structurally interchangeable with production objects, even when their shapes rhyme
**Rule:** `ResearchStrategyPlugin` is a distinct type from `StrategyPlugin`, `Realization` is distinct from `StrategyDecision`, even where their fields look similar.
**Why:** Structural typing means a "close enough" shape can be accepted where it shouldn't be; a small amount of deliberate duplication buys a hard boundary a shared type cannot.
**Prevents:** A research object being accidentally accepted by a production function expecting a similar-looking production type.
**Correct:** `evaluate_strategies()` cannot accept a `ResearchStrategyPlugin` even by accident, because it is not the same type.
**Violation:** Reusing `StrategyPlugin` directly for research "since it's basically the same shape."

### VIII.5 — New capability is added beside what exists, never inserted into it
**Rule:** A new feature family, discovery method, criterion, or validation technique is a new, additive module — never a modification of an existing one's meaning.
**Why:** This is the same additive-sibling discipline that has held throughout Market Context, Setup Interpretation, Replay Engine, and Strategy Engine; it is what makes years of accumulated capability safe to keep extending.
**Prevents:** A change to one capability silently altering the behavior or meaning of another that happens to sit nearby.
**Correct:** A new causal-discovery method is added as a new submodule under `atlas.research.discovery`, with its own version, touching no existing method's code.
**Violation:** Generalizing an existing, already-used discovery method's behavior in place to also cover a new case, changing what its old callers get.

---

## IX. Evolution Philosophy

### IX.1 — Implementation may change; principles may not
**Rule:** Every principle in Sections I–VIII binds regardless of language, framework, storage engine, or team.
**Why:** This document's entire value is that it outlives any particular implementation choice; a principle that implementation details could override wouldn't be a principle.
**Prevents:** Architectural decay disguised as "just an implementation detail."
**Correct:** A future migration from file-backed storage to a database changes nothing about immutability, provenance, or the dependency boundary.
**Violation:** Justifying a violation of a principle above by pointing to a technical constraint of the current implementation.

### IX.2 — Storage technology, AI models, and package layout are implementation details, not architecture
**Rule:** None of these may be treated as load-bearing to any principle above; they are free to change at any time without amending this document.
**Why:** Naming this explicitly prevents the common failure mode where a technology choice is mistaken for a design decision and becomes accidentally permanent.
**Prevents:** Technology lock-in masquerading as architectural necessity.
**Correct:** Swapping the underlying AI model behind `atlas.research.assistant` requires no change to Section VI.
**Violation:** A principle that can only be satisfied by one specific database or one specific model vendor.

### IX.3 — New capability never requires re-litigating an already-certified boundary
**Rule:** Extending the Research Engine must never require reopening Rule Engine, Setup Engine, Setup Interpretation, Replay Engine, or Strategy Engine's own certification.
**Why:** If every new research capability risked reopening certified production boundaries, certification would mean nothing and every extension would carry production-level risk.
**Prevents:** Scope creep that repeatedly drags certified, frozen work back into question.
**Correct:** Adding representation-learning-based discovery requires zero changes anywhere in N1–N3.
**Violation:** A proposed feature that "just needs one small change" to a certified production package to work.

### IX.4 — This document changes only by deliberate, explicit amendment, never by silent drift
**Rule:** A change to any principle in this document requires the same review rigor as a change to a production certification — an explicit, reasoned, reviewed amendment, never an implicit reinterpretation.
**Why:** A constitution that can be quietly reinterpreted by whoever is implementing this week's feature is not a constitution.
**Prevents:** The document becoming decorative rather than governing.
**Correct:** A genuine need to change a principle produces a dated, explicit amendment section below, with its own rationale.
**Violation:** A pull request that violates a principle here, justified only by "the document is outdated" with no formal amendment.

---

## X. Anti-Patterns — permanently forbidden

| Anti-pattern | Why it is forbidden | Principle violated |
|---|---|---|
| **Strategy-first design** | Reduces the platform to grading pre-known ideas instead of discovering new ones | I.1, I.2 |
| **Deleting failed or rejected experiments/hypotheses** | Destroys the permanent negative-result knowledge the platform exists to accumulate | II.1 |
| **Allowing AI to validate or promote anything** | Removes the deterministic, auditable judgment layer and the mandatory human gate | V.1, VI.1 |
| **Skipping or weakening validation for a "clearly obvious" finding** | Multiple-testing and out-of-sample discipline exists precisely because intuition about significance is unreliable at scale | IV.3, IV.4 |
| **Mixing research and production code or dependencies in either direction** | Collapses the entire certification boundary this platform depends on | VIII.1, VIII.2 |
| **Editing historical Evidence, Hypothesis statements, or ValidationResults in place** | Destroys the auditable, reproducible record; a correction must be new, linked evidence | III.2, II.3 |
| **Re-running an experiment without recording/verifying its full version and seed** | Makes the result unreproducible and any drift undetectable | VII.2, VII.3 |
| **Silent feature mutations** (changing a feature's definition without a version bump) | Makes every historical result referencing that feature retroactively ambiguous | VII.4, VIII.5 |
| **Hidden or overwritten provenance** | Makes accountability and lineage unreconstructable, and is the specific failure mode Section VI exists to prevent | VI.3 |
| **Fitting acceptance criteria to results after they're known (HARKing)** | Guarantees favorable-looking results regardless of whether the claim is true | IV.2 |
| **Treating InsufficientData as a negative result** | Conflates "couldn't measure" with "measured and it's false" | III.4 |
| **Un-seeded randomness anywhere in validation** | Makes stochastic methods unreproducible by construction | VII.2 |
| **A research strategy structurally passing as a production `StrategyPlugin`** | Defeats the deliberate type-level boundary between research and production objects | VIII.4 |
| **Dynamically generating and executing feature code from automated discovery** | Introduces an arbitrary-code-execution surface where a declarative, sandboxed specification would do | VIII.1 (extends to feature generation safety) |
| **A "fast lane" or confidence-based bypass of human promotion review** | The one mandatory gate this platform has; there is no confidence level that replaces it | V.1, V.4 |
| **Merging raw Discovery output directly into the Hypothesis ledger without formalization** | Collapses the deliberate detected-vs-interpreted boundary between exploration and claim | IV.1 |
| **A dependency boundary enforced only by documentation, not by an automated test** | Boundaries not mechanically enforced erode under deadline pressure | VIII.3 |
| **Conflating causal and associative claims without distinguishing them** | A causal claim requires materially more evidence than an associative one; treating them the same overstates confidence | (extends IV, from the Discovery Engine's own claim-strength discipline) |

---

## Amendments

*(None yet. Any future change to Sections I–IX must be recorded here, dated, with its rationale, per Principle IX.4.)*
