# Rule Engine Architecture — Planning Sprint

**Status: architectural baseline, originally approved 2026-07-19 as planning-only, before any
Phase 3 code existed. Implementation status updated through Sprint 13 (2026-07-19) — Sprints
11–13 have since implemented the Rule Engine package, its output types, and six facts against
this document's design. The original planning rationale below is retained unchanged for
traceability; only status/resolution markers have been added on top of it — see "Explicitly
deferred" and "Recommended future directions" below for what's resolved versus still open.**

Builds on `architecture-principles.md`'s AI Boundaries section (the rule this document exists to
make concrete) and `roadmap.md`'s Phase 3 definition. Read those first; this document does not
repeat their reasoning, only extends it.

## Why this planning Sprint exists

Phase 3 (AI Analysis) was already split, by standing instruction, into two separate architectural
concerns: rule-based market analysis and LLM reasoning, never one combined "AI" layer. That
split is a boundary, not a design. This document defines what sits on each side of it, concretely
enough that Phase 3's first real implementation Sprint has a spec to build against instead of a
principle to interpret from scratch.

## Existing precedent this extends, not reinvents

`atlas/intelligence.py` already proves this pattern works, for a different domain (trade entry
scoring, not market analysis): it computes a confidence score, expected R, and historical win
rate deterministically, and Claude is only ever called afterward, to explain numbers that already
exist — never to invent its own. The Rule Engine is this same pattern, applied to market state
instead of trade history. Nothing below invents a new relationship between deterministic
computation and LLM narration; it specifies where that already-proven relationship applies to
Market Engine data specifically.

---

## 1. Objective Market Facts

An objective market fact is a value computable from stored `MarketState` data with **one correct
answer, reproducible by anyone given the same input** — no interpretation, no judgment call, no
model. "Close is 7.25 points above VWAP" is a fact. "This looks like a breakout" is not — that's
either a rule-based *classification* (still deterministic, but a step removed from a raw fact) or
an LLM's narration, never a fact itself.

**A concrete, already-latent architectural finding this planning pass surfaced**: the Pine script
(Sprint 5) deliberately sends every derived/pattern field — `trend_1m/5m/15m/1h`,
`liquidity_sweep`, `reclaim`, `rejection`, `displacement`, `volume_spike`, the four
`*_status` fields — as `null`/`false` placeholders, an explicit Sprint 5 decision to avoid
encoding unvalidated pattern-detection assumptions in Pine. Read in light of this document, that
decision implies where those facts *should* be computed: server-side, by the Rule Engine, from
raw OHLCV and the reference levels TradingView already sends (VWAP, previous-day high/low,
overnight high/low, `rth_open`) — not left permanently null, and not computed in Pine either. The
Rule Engine's first real responsibility is exactly the fact-computation Sprint 5 deferred.

**Facts require a window, not a snapshot.** Most of the interesting facts above (`trend_*`,
`liquidity_sweep`, `volume_spike`) are inherently multi-bar — they cannot be computed from one
`MarketState` in isolation. This makes Sprint 9/10's read capabilities load-bearing prerequisites,
not incidental: the Rule Engine's live input is `get_latest` + a bounded `get_history` window for
the same `(symbol, timeframe)`; its historical/validation input is `get_range` /
`replay_market_state`. Both paths go through Market Engine's existing read ports — the Rule
Engine never touches Market Engine's repositories or adapters directly (Dependency Rules, already
established).

**Applying your EmptyResult/InvalidRange recommendation forward**: the same distinction you raised
for Replay generalizes naturally here. A Rule Engine computing, say, a 20-bar trend needs to
distinguish "computed the fact; the market is genuinely quiet/range-bound" (a real, meaningful
result) from "cannot compute this fact; fewer than 20 bars exist in the requested window" (a data
sufficiency problem, not a market observation). Collapsing these into one "no signal" result would
hide a data problem behind what looks like a market fact. This document does not resolve the
implementation shape of that distinction (that's the next Sprint's job, matching your "no change
required now" for Replay) — it only records that the same principle applies here and should not
be forgotten by the time Rule Engine output types are actually designed.

## 2. Rule Engine Outputs

Properties the Rule Engine's output must have, independent of its exact future schema:

- **Deterministic and reproducible** — same input window, same output, always. No hidden state,
  no clock dependency beyond what's already in the input.
- **Fully testable without any LLM or external API** — the same discipline `atlas/intelligence.py`
  and `atlas/monitoring.py` already established for this codebase's pure functions.
- **Its own domain type, not an extension of `MarketState`.** `MarketState` is Market Engine's
  canonical model (a Stable Interface per Sprint 10's Interface Stability section) and should not
  absorb churn from a much faster-moving concern. The Rule Engine consumes `MarketState` as
  input and produces a new, separately-owned output type — the same "canonical model strictly
  separate from what consumes it" discipline already applied to the TradingView wire model.
- **Versioned** — the eventual output type should carry something like `MarketState.schema_version`
  does, so a heuristic change (e.g., a retuned trend-detection threshold) is a visible, traceable
  event, not a silent behavior change under callers who assume stability.
- **Ownership if persisted**: if Rule Engine output is ever stored (not decided here), it gets its
  own store, the same way `ai_notes` is owned by the existing AI Copilot and not folded into
  Market Engine's tables. Data Ownership's rule — Market Engine is the sole owner of
  `market_state_events`; nothing else writes to it — extends unchanged: the Rule Engine is a
  reader of Market Engine, never a writer to it.

**Explicitly not decided here**: the literal field list, the output type's name, or its package
location. Those are implementation decisions for Phase 3's first real Sprint, made against an
actual first fact set (trend, VWAP relationship, liquidity context are the obvious starting
candidates, not a commitment).

## 3. Interface Between Rule Engine, Setup Engine, and LLM

**Superseded 2026-07-19 (Sprint 17 planning), corrected 2026-07-19 (Sprint 17A close-out):** the
dependency chain is `Market Engine → Rule Engine → Setup Engine → LLM`. **Setup Engine consumes
Rule Engine output; the future LLM consumes Setup Engine output only — never Rule Engine output,
and never Market Engine output.** This document previously described the LLM as depending
directly on Rule Engine output; that was stale as soon as Setup Engine was approved, and every
paragraph below has been corrected to match. See `docs/market_engine/roadmap.md`'s Phase 3 entry
for the current layering.

Rule Engine's own public interface additionally now includes a windowed capability (Sprint 17A,
`atlas/rule_engine/service.py::build_rule_engine_output_window`): given a strictly contiguous
`list[MarketState]` for one symbol/timeframe, it returns one `RuleEngineOutput` per input bar, in
order — validated via `atlas/rule_engine/window_integrity.py` before any fact is evaluated. This
is what Setup Engine's `SetupEvaluationContext.history` is built from. Deliberately
calendar-agnostic: a caller (Replay, Dataset Builder) is responsible for segmenting a raw series
at session/weekend/holiday boundaries before calling it — Rule Engine does not consult
`atlas.monitoring.is_market_hours_expected` to decide what counts as contiguous, so its own
disclosed non-holiday-awareness never becomes a Rule Engine correctness bug.

One-directional at each hop, matching Architecture Principles' AI Boundaries #4: **LLM reasoning
depends on Setup Engine output; Setup Engine depends on Rule Engine output; nothing downstream
ever depends on or waits for an LLM call.** Concretely, this means:

- The LLM's prompt is constructed **entirely** from Setup Engine's output type. The
  prompt-construction code must never import or reference `atlas.rule_engine` or
  `atlas.market_engine` (including `MarketState` or any Market Engine read port) directly — only
  Setup Engine's output. This is a checkable rule, the same way Dependency Rules are checked by
  grep at every Sprint's self-review: "does the LLM module import `atlas.rule_engine` or
  `atlas.market_engine` at all?" should always answer no.
- Setup Engine's output must be **self-sufficient** for narration — the LLM should never need to
  ask a clarifying question or fetch more data mid-reasoning. If a setup could not be evaluated,
  Setup Engine's output says so explicitly (the same `InsufficientData` discipline Rule Engine
  already established); the LLM narrates the absence, it doesn't go looking for the missing data
  itself, and it never reaches past Setup Engine to Rule Engine or Market Engine to fill the gap.
- The interface data is **inert** — facts, structures, and classifications only, never an
  instruction or a directive. This is the same boundary that already prevents AI from placing
  orders, applied one layer earlier: the data crossing from Setup Engine to LLM must not itself
  look like a command, so there's no ambiguity for a future reader (human or code) about who
  decided what.
- The interface should carry its own version marker (see Outputs above, and Setup Engine's own
  two-tier versioning), so a prompt-engineering change and a fact- or setup-computation change
  are distinguishable from each other in hindsight.

## 4. Deterministic vs. Probabilistic Responsibilities

| | Deterministic (Rule Engine, Setup Engine) | Probabilistic (LLM) |
|---|---|---|
| Reproducibility | Same input → same output, always | May vary run to run (temperature, model updates) |
| Testability | Unit-testable, no external API | Not meaningfully unit-testable the same way |
| Responsibility | Computing facts and higher-level structures — anything with one correct answer | Narrating/explaining what Setup Engine already produced, in readable language |
| Cost/latency | Fast, free | Slower, has a real API cost |
| Trusted for facts? | Yes — the only source of truth for "what is true about the market right now" | Never — the LLM must not be the origin of a fact or structure any downstream system relies on |
| May Strategy (Phase 4) consume it? | Strategy may consume deterministic analysis outputs, according to its own future approved architecture — not decided here | Strategy must never consume or parse LLM prose as a decision source |

The last row is deliberately neutral: Phase 4 (Strategy & Signal Layer) has not been designed
yet, and whether it consumes Rule Engine output, Setup Engine output, or both is a decision for
that Phase's own planning Sprint, not this document. What **is** settled, and does not wait on
that decision: **Strategy must never consume or parse the LLM's prose as a decision source.** The
LLM's output is presentation-layer only — a human-facing explanation — and nothing downstream
should ever parse it looking for a decision. Decisions need to be reproducible and auditable;
only the deterministic side (Rule Engine, Setup Engine) can promise that.

---

## Explicitly deferred to Phase 3's first implementation Sprint

Originally named here so they wouldn't be silently decided by default once implementation
started. Retained below with resolution status, not erased — this is what was actually decided,
and when.

**Resolved through implementation (Sprints 11–13):**

- Package name and location for the Rule Engine — resolved: `atlas/rule_engine/`, a new
  top-level domain package (Sprint 11), matching `market_engine`'s own internal shape
  (`models.py`, `service.py`, plus `facts.py`/`definitions.py` added as the fact count grew).
- The literal first fact set and output schema — resolved: `volume_spike`, `displacement`
  (Sprint 11), `rejection` (Sprint 12), `trend_5m`, `liquidity_sweep`, `reclaim` (Sprint 13).
  Output schema: `RuleEngineOutput` (`schema_version`, `symbol`, `timeframe`, `occurred_at`,
  `facts: dict[str, FactOutcome]`) — see `rule-fact-inventory.md` for each fact's implemented
  definition.
- The EmptyResult/InvalidRange-equivalent type shape for Rule Engine outputs — resolved:
  `FactResult` (computed, with `value` and evidence) versus `InsufficientData` (could not be
  computed, with a `reason`), unioned as `FactOutcome` (Sprint 11).

**Still deferred:**

- Whether/how Rule Engine output is persisted, and in what store — not yet decided; no fact
  output has been persisted anywhere through Sprint 13.
- Prompt design and which existing Claude integration pattern (`atlas/services/claude.py`) to
  reuse versus adapt — not yet started; no LLM reasoning code exists yet, only the Rule Engine
  (deterministic) side.

## Recommended future directions (not yet actioned)

Approved recommendations for later work, deliberately not implemented yet — named here so they
survive to whichever Sprint actually takes them on, rather than living only in a chat transcript
that could be lost the way the original roadmap was.

- **Dynamic history requirements (raised after Sprint 13).** `atlas.rule_engine.service`'s
  `HISTORY_LIMIT` constant is a manually-maintained upper bound on how much history the live path
  fetches, kept in sync by hand with the largest windowed fact's `FactDefinition.params["window"]`
  (TD-15 in Sprint 13's Technical Debt Register). Recommended direction: derive the required
  history automatically from the registered `FactDefinition`s (e.g. the maximum configured window
  across all active facts) instead of a hardcoded constant, removing the maintenance burden and
  the risk of silent under-fetching once a fact needing a larger window is added.
- **Typed categorical values (raised after Sprint 13).** `FactResult.value` is currently
  `Union[bool, str]` — widened in Sprint 13 specifically to fit `trend_5m`'s "up"/"down"/"flat"
  classification. Recommended direction: once a second categorical fact exists (not `trend_5m`
  alone), introduce typed categorical values (e.g. a `TrendDirection` enum) rather than letting
  `value`'s union grow indefinitely as more non-boolean facts appear. Explicitly not a Sprint 13
  retrofit — this is the preferred long-term direction, to be taken up when it's actually needed.

## What this planning Sprint does not change

No code, no migration, no new dependency, no change to any Sprint 1–10 deliverable. Sprint 10's
approval, and Architecture Principles/Roadmap's approval as permanent baseline, stand unmodified.
