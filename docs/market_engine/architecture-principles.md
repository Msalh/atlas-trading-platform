# Market Engine — Architecture Principles

**Status: permanent baseline, approved 2026-07-19.**

This document is distinct from the Roadmap (`roadmap.md` in this folder — the *what* and *when*)
and from any Sprint's own Architecture Decision Log entries (the *why* behind one specific past
choice). This document is the *invariants* — the rules a roadmap must always be written to
respect, and that no ADR may quietly override. Roadmaps change. These principles do not, except
by an explicit, separate decision to amend this document itself — never as a side effect of a
Sprint's implementation discovering something inconvenient.

If a future Sprint's implementation appears to require violating a rule below, that Sprint stops
before writing code and this document gets amended first, deliberately — the same discipline
that produced the Architecture Planning Sprint this document supports, applied permanently rather
than once.

---

## Core Architectural Principles

1. **Modular monolith.** One deployable process, internally modular via packages, not services.
   Revisit only under a real, measured operational need — never speculatively, never because
   microservices are the more familiar industry default.
2. **Hexagonal layering, dependencies point inward.** `core` (innermost) depends on nothing else
   in this codebase. Domain packages (`market_engine`, and future `ai_analysis`, `strategy`,
   `execution`) depend only on `core` and each other's public ports, never on the application
   layer. The application layer (`api/`, `main.py`, `monitoring.py`) may depend on any domain
   package. Adapters (TradingView, Postgres) implement ports the domain defines; the domain never
   imports an adapter.
3. **No speculative abstraction.** An abstraction earns its place by having a real, present
   consumer — not an anticipated future one. Guessing the "right" general shape ahead of a
   concrete need is exactly the risk this project has repeatedly declined to take.
4. **Every Sprint leaves the system deployable.** No half-finished migration, no broken contract,
   at any shipped commit boundary.
5. **Simplicity over cleverness; modify existing code before inventing new patterns.**

## Data Ownership

1. Market Engine is the sole owner and single source of truth for market state. No other package
   ever writes to `market_state_events`.
2. The canonical domain model (`MarketState`) and wire-format adapter models
   (`TradingViewMarketStatePayload`) are strictly separate. Adapters translate inward only;
   nothing outside an adapter constructs a wire model, and nothing inside the domain depends on
   one.
3. `occurred_at` (when the market event happened) and `received_at` (when this system learned
   about it) are permanently distinct fields, never collapsed into one. Every future capability
   that reasons about time must know which one it actually needs.
4. The raw inbound payload (`raw_payload`) is a persistence/traceability concern, not a domain
   concept — it exists for audit and replay-fidelity, never as an input to business logic.
5. Trade/execution data and market data remain separately owned stores
   (`TradeRepository`/`MarketStateRepository`). A future Strategy or Execution layer reads from
   both; neither store absorbs the other's responsibility.

## Dependency Rules

1. Dependencies point inward, always — verified by inspection at every Sprint's self-review, not
   assumed.
2. No dependency cycles between domain packages, ever.
3. Future domain packages (AI Analysis, Strategy, Execution) depend on Market Engine's read ports
   (`MarketStateRepository`) — the same public contract any authenticated external caller uses —
   never on its repository implementations, adapters, or migrations directly.
4. Independent trust domains keep independent secrets, established by `WEBHOOK_SECRET` vs.
   `MARKET_STATE_WEBHOOK_SECRET`. Any future inbound integration gets its own secret unless its
   trust domain is genuinely identical to an existing one.

## Immutability Rules

1. Market Engine is an append-only event store. Once a `market_state_events` row is written, no
   code path ever updates or deletes it.
2. A correction to a previously ingested event is a new event, never an edit to the old one — the
   history of what this system believed, and when, is itself a fact worth preserving.
3. Domain value objects (`MarketState`, `Event`, `Price`, `Symbol`) are immutable. A value, once
   constructed, cannot change under a caller holding a reference to it.
4. Idempotency is enforced by uniqueness at write time (`ON CONFLICT DO NOTHING`), never by
   allowing a duplicate write and reconciling it after the fact.

## AI Boundaries

1. **AI never writes to Market Engine** — not the canonical store, not any derived table. This is
   the platform's hardest boundary; nothing in any future phase may cross it.
2. AI consumes Market Engine exclusively through its public read ports, with no privileged or
   internal repository access.
3. AI never places, modifies, or cancels an order, directly or indirectly. Anything AI's output
   leads to must pass through the Strategy and Execution boundaries below.
4. **Rule-based market analysis and LLM reasoning are separate architectural concerns — never one
   combined "AI" layer.**
   - *Rule-based analysis*: deterministic, code-defined computation over market state. Produces
     structured facts (scores, classifications, distances). No LLM involved. Fully
     unit-testable without any external API.
   - *LLM reasoning*: consumes rule-based analysis's **output**, never raw market state directly,
     and never computes a fact the rule-based layer could compute deterministically. Its job is
     interpretation and narration of numbers that already exist — not invention of new ones.
   - Dependency direction is one-way: LLM reasoning depends on rule-based analysis; rule-based
     analysis never depends on or waits for an LLM call, and must be useful with zero LLM
     involvement.
   - This is not a new invention — it is the existing, proven pattern already running in
     `atlas/intelligence.py` → Claude for trade entry scoring (deterministic confidence score
     computed first; Claude only explains the numbers, never invents its own). This document
     makes that pattern permanent and extends it to Market Engine's future AI Analysis phase,
     rather than leaving it to be re-decided per Sprint.

## Replay Guarantees

1. Replay is deterministic — the same `(symbol, timeframe, range)` request always produces the
   same ordered output, for as long as the underlying stored data is unchanged (which, per
   Immutability Rules, is always).
2. Replay is strictly read-only — zero writes, zero side effects, anywhere.
3. Replay draws only from data that has passed Market Engine's own integrity checking (gap
   detection) — a replay consumer can always know whether its requested range had gaps, rather
   than silently trusting incomplete data as complete.
4. Replayed data must always be distinguishable from live data by every downstream consumer.
   Nothing that consumes a replay stream may mistake it for a live feed — this matters most at
   the Execution boundary, where confusing the two risks real capital.

## Execution Boundaries

1. Only the Execution layer places orders. AI, rule-based analysis, and Strategy layers may only
   ever produce proposals or signals — never a direct order.
2. Paper and Live execution are strictly separated. The transition from Paper to Live is never
   automatic — it requires an explicit, separate human decision, never a code path or a schedule.
3. Execution always has a fail-safe kill switch by default, matching the precedent already
   established for trades (`RISK_ENFORCEMENT`) — inherited from the start, not added under
   pressure later.
4. Live execution never runs logic that hasn't first run, unmodified, through Paper.

## Testing Philosophy

1. Business/domain logic is written pure and unit-testable without I/O, a database, or an
   external API — the default shape (as in `atlas/monitoring.py`, `atlas/market_engine/service.py`)
   for all future logic, not an exception granted case by case.
2. Persistence boundaries are tested against a real database (`tests/integration/`), never
   mocked — a mock of Postgres proves nothing about a real migration or a real constraint.
3. A capability is not "done" until tests prove its behavior — no exception, at any Sprint.
4. `ruff --select=F` and the full suite are CI gates on every change — a green suite is necessary,
   never sufficient on its own, but its absence is always disqualifying.

## Reliability Philosophy

1. **Reliability before intelligence** — the platform's central governing philosophy, unchanged
   since the original architecture discussion. Every future phase is built on a foundation
   proven reliable first, never in parallel with it.
2. No optimization without a measured bottleneck.
3. Observability and alerting are advisory-only: they inform a human, never block or alter core
   function, and degrade to a silent no-op when unconfigured rather than failing loudly or
   unsafely.
4. Every known limitation is disclosed in code and documentation, never silently assumed away.
5. Every Sprint stops and reconciles when it discovers something bigger than itself, rather than
   silently absorbing it — this document exists because that principle was followed.

## Documentation Maintenance Rule

Added Sprint 22A/22B, prompted by two concrete instances found in the same review: `roadmap.md`'s
"Next planning point" section going stale across Sprints 19–21 (still describing "one real setup...
the next decision has not been made" long after that had stopped being true), and
`setup-engine-catalog.md`'s `vwap_reversion_with_volume_fade` entry silently drifting until its own
purpose text ("volume declining") contradicted its own required-facts column (`volume_spike`,
elevated volume).

Whenever a Sprint resolves something another document named as upcoming, planned, or "next" —
implements it, defers it, renames it, or redesigns it — that Sprint must update **every** document
that named it as upcoming, not only the document being directly worked on. A stale forward-reference
left in another document after its own resolution is a documentation defect to fix the same Sprint,
not debt to accumulate. This applies with equal force to internal consistency within one document:
a setup or fact's stated purpose must never be left contradicting its own declared inputs.
