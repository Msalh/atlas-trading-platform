# Architecture Review 2.0 — AI Trading Assistant

**Status:** Product and architecture recommendation; no implementation authorization
**Repository state reviewed:** `main` at `f983b21`
**Review question:** What should a trader see on screen while actively trading?

## 1. Executive Summary

Atlas has a strong deterministic backend and a secure frontend transport, but its product surface reflects the sequence in which engineering capabilities were built rather than the sequence of decisions a trader makes. The current UI exposes 18 routes through primary navigation, section navigation, and a “More” menu. Live trading, system health, deterministic facts, setup diagnostics, frozen research data, research-ledger administration, analytics, and AI commentary are all first-class destinations.

The target should be a six-destination product:

1. **Dashboard** — the ten-second operational answer: what matters now and what posture is permitted.
2. **Market** — structured market context, facts, active setups, and evidence.
3. **Trades** — open-trade management plus searchable completed-trade review.
4. **AI** — evidence-bound explanations, briefings, reports, and review narratives.
5. **Research** — replay, statistical baselines, dataset health, experiments, lineage, and diagnostics.
6. **Settings** — account limits, integrations, data freshness, and advanced diagnostics.

The immediate opportunity is not to add more LLM behavior. It is to productize capabilities that already exist but are fragmented or not exposed live:

- The live UI already has deterministic Rule Engine facts and four Setup Engine detectors.
- The backend already contains `market_context`, `setup_interpretation`, `replay_engine`, and `strategy_engine` packages.
- One deterministic strategy plugin already emits `candidate`, `rejected`, or `no_signal` with machine-readable reasons.
- These context/strategy outputs are currently replay-domain objects only: there is no live API, BFF route, or trader-facing presentation for them.

The recommended immediate sprint is therefore **Product IA and Dashboard Contract**, split into a product-contract sub-sprint and a frontend navigation/shell sub-sprint. It should define the canonical “trader now” read model before attempting a visual dashboard or AI recommendation. A subsequent sprint should expose the existing deterministic live context/strategy pipeline through a versioned backend read API.

The recommended action vocabulary—`WAIT / PREPARE / ENTER / HOLD / REDUCE / EXIT`—must not be generated directly by an LLM. It should be a deterministic policy result with explicit reason codes, freshness, confidence provenance, and safety gating. The LLM may explain that result; it must never create, override, or execute it.

## 2. Current Product Audit

### 2.1 Verified product shape

The global shell is implemented in `frontend/src/app/layout.tsx`. It presents:

- a fixed Atlas/MNQU6/strategy identity;
- global risk and system-status indicators (`HeaderKillSwitchDot`, `HeaderStatusDot`);
- `AppNav`;
- a footer still labeled “Sprint 7,” which is engineering history rather than product information.

`frontend/src/components/AppNav.tsx` exposes:

- primary: Dashboard, Trading, Research, Analytics, AI, Account;
- Trading secondary: Market View, Rule Engine, Active Setups, Timeline;
- Research secondary: Overview, Leaderboard, Snapshot Explorer, Promotion Queue, Promotion History, Run Center;
- More: Episode Inspector, Statistical Baseline, Dataset Health, Activity.

This is a meaningful improvement over a flat 18-link navigation, but it still gives engineering concepts (“Rule Engine,” “Dataset Health,” “Snapshot Explorer”) product-level prominence.

### 2.2 Trader-facing surfaces

- **Dashboard** (`frontend/src/app/page.tsx`): current position, recent trades, connection status, today’s statistics.
- **Account** (`frontend/src/app/account/page.tsx`): account balance, daily loss, trailing drawdown, exposure, display-only kill switch.
- **Analytics** (`frontend/src/app/analytics/page.tsx`): performance summary, equity curve, drawdown, session/setup/weekday breakdowns.
- **AI** (`frontend/src/app/ai/page.tsx`): open-trade Copilot, report generation/history, AI notes.
- **Trade Detail** (`frontend/src/app/trades/[correlationId]/page.tsx`): trade state, lifecycle timeline, AI notes, PMT relay diagnostics.
- **Market View** (`frontend/src/app/market-view/page.tsx`): Rule Engine facts and Setup Engine results for the selected symbol/timeframe.
- **Active Setups** and **Timeline**: live episode projections and activation history.

### 2.3 Engineering/research-facing surfaces

- **Rule Engine**: raw fact output and refresh controls.
- **Episode Inspector**: live episode state beside frozen historical duration distributions.
- **Statistical Baseline**: raw RE-1/RE-2 JSON sections.
- **Dataset Health**: dataset identity, certification, and warnings.
- **Research Ops** pages: readiness, leaderboard, snapshot lineage, promotion queue/history, and run-center availability.
- **Activity**: a useful operations feed, but the category model combines trading, AI, risk, analytics, and system events.
- **PMT diagnostics** inside Trade Detail: valuable for incident response, not a primary completed-trade review section.

### 2.4 Incomplete, placeholder, or deliberately constrained surfaces

The following are not broken, but are incomplete as trader products:

- Dashboard has no market context, setup state, or decision posture.
- Market View shows raw facts and setup detector output but no integrated bias/context interpretation.
- AICopilot only activates for an open trade and provides deterministic client-side management observations; it does not have a persisted recommendation or live context input (`frontend/src/components/AICopilotPanel.tsx`, `frontend/src/lib/copilotNotes.ts`).
- Trade Timeline contains only the latest price update, explicitly not full price history (`live/atlas/api/v1/trades.py`).
- Run Center renders operation availability but does not expose a general live strategy control plane.
- Settings does not exist.
- Trades has no list-level top-level route; trade history is embedded on Dashboard and details exist only at `/trades/{id}`.
- Current production data may legitimately show no MarketState, no active setup, no open position, or no AI reports. These empty states are honest but leave the workflow without a useful pre-session briefing.

### 2.5 Duplicated functionality

| Duplication | Current locations | Product consequence |
|---|---|---|
| Current trade | Dashboard `CurrentPositionCard`; AI `AICopilotPanel`; Trade Detail | The user changes pages to move from status to advice to evidence. |
| Risk | Header; Account cards; AICopilot | Safety information is repeated but not prioritized by workflow state. |
| Rule facts | Market View and standalone Rule Engine | Raw diagnostic and market-summary roles overlap. |
| Setup state | Market View, Active Setups, Timeline, Episode Inspector | Four screens explain related detector/episode state without one canonical “setup now” view. |
| AI trade notes | AI timeline and Trade Detail timeline | Useful at global and per-trade scopes, but the distinction is not explicit. |
| Research overview | `/research` and `/research-ops` | “Research” means both frozen statistical baseline and operational ledger. |
| Status | Header, Dashboard connection panel, Research Ops readiness, Activity | System health is useful but overrepresented in the trading workflow. |
| Performance | Dashboard today stats, Analytics, AI Copilot overall account sentence, AI reports | Different horizons are spread across pages without a shared hierarchy. |

### 2.6 Shared component and data architecture

Positive verified properties:

- All browser JSON calls use the same-origin BFF through `frontend/src/lib/proxyClient.ts`.
- Server-sent events use `/api/stream` through `frontend/src/lib/live-updates.tsx`.
- React Query keys deduplicate repeated risk/status/trade requests.
- `LiveSelectorProvider` shares symbol/timeframe selection across live market tools.
- `useLiveEpisodes` gives Active Setup, Timeline, and Episode Inspector one live episode query contract.
- Runtime validators exist in typed API clients.
- Freshness and live/frozen provenance are represented explicitly for research/setup surfaces.

The main problem is therefore information architecture, not transport or component isolation.

## 3. Current Navigation and Route Inventory

| Route | Current purpose | Main components | API dependencies | Classification / recommendation |
|---|---|---|---|---|
| `/` | Current position, recent trades, system status, today stats | `CurrentPositionCard`, `TradeHistoryTable`, `ConnectionStatusPanel`, `StatsSummaryCard` | `trades/current`, `trades`, `status`, `stats/today`, conditional `ai/notes` | Trader-facing; redesign as ten-second Dashboard. |
| `/account` | Account and risk limits | balance/loss/drawdown/exposure/kill-switch cards | `risk` | Merge into Settings; keep critical risk summary globally. |
| `/analytics` | Historical performance | summary/equity/drawdown/breakdown | analytics endpoints | Merge into Trades “Performance” or keep as a Trades subsection. |
| `/activity` | Cross-domain event feed | `ActivityTimeline` | `activity` | Move under Settings/Diagnostics; optionally expose filtered trading events in Trades. |
| `/ai` | Copilot, reports, AI notes | `AICopilotPanel`, `AiReportsPanel`, `AiNotesTimeline` | current trade, intelligence, risk, analytics, AI notes/reports | Keep top-level but redefine around briefings/explanations, not an isolated data island. |
| `/trades/[correlationId]` | One trade and timeline | `TradeDetailView`, `TradeTimeline`, `PmtDiagnosticsPanel` | dynamic trade detail | Keep under new Trades. Move PMT diagnostics to advanced drawer. |
| `/market-view` | Live facts and setups | `RuleEngineFactsPanel`, `SetupEngineViewer` | rule/latest, setup/latest | Becomes Market overview. |
| `/rule-engine` | Raw fact inspection | `RuleEngineViewer` | rule/latest | Move to Research/Diagnostics; facts remain summarized in Market. |
| `/active-setups` | Current setup episodes | `ActiveSetupBundle` | setup episodes/live | Merge into Market. |
| `/timeline` | Setup activation history | `Timeline` | setup episodes/live | Merge into Market evidence/timeline. |
| `/episodes` | Episode diagnostics plus frozen duration profile | `EpisodeInspector` | setup episodes/live, RE-2 summary | Move to Research/Diagnostics. |
| `/research` | Frozen RE-1/RE-2 raw JSON baseline | `JsonSection` | research RE-1/RE-2 | Merge into Research; replace raw JSON as the default presentation. |
| `/dataset-health` | Frozen dataset certification | health panels | research/dataset-health | Research/Data Quality. |
| `/research-ops` | Research readiness and summary | readiness/stat cards | status, leaderboard, promotion history | Research home. |
| `/research-ops/leaderboard` | Ranked hypotheses | leaderboard table | leaderboard, promotion history | Research/Hypotheses. |
| `/research-ops/snapshot` | Snapshot entry and lineage inspection | lineage/stat components | leaderboard, lineage | Research/Lineage. |
| `/research-ops/promotion/queue` | Candidates awaiting human review | promotion queue | candidates, leaderboard | Research/Governance. |
| `/research-ops/promotion/history` | Recorded promotion decisions | history table | promotion history | Research/Governance. |
| `/research-ops/run-center` | Research readiness and operation availability | operation/readiness cards | status, leaderboard, candidates | Research/Operations; engineering-oriented. |

There is no `/settings` route and no `/trades` index route.

## 4. Current User Journey

### 4.1 Before the New York session

The trader lands on Dashboard and sees account/trade/system state, but not session phase, time to open, overnight range, prior-day levels, VWAP, volatility regime, or setup readiness. They must navigate to Trading/Market View, then possibly Active Setups, Timeline, or Episode Inspector.

Relevant raw fields already exist in `MarketState` (`live/atlas/market_engine/models.py`), including session, RTH/overnight/prior-day levels, VWAP, ATR, liquidity status, and multi-timeframe trend. However, the frontend BFF does not expose the Market State read endpoints.

### 4.2 Understanding the current market

Market View exposes seven deterministic Rule Engine facts and four Setup Engine outputs. It does not expose the canonical raw market state or the backend’s existing `MarketContext` classification. The user must infer “market bias” from fact values and detector evidence.

### 4.3 Determining whether a setup exists

Setup Engine can answer whether each registered setup is detected and with what severity/evidence. Active Setup and Timeline add episode duration and activation history. The answer exists but is distributed across three pages and expressed in engine vocabulary rather than trader vocabulary.

### 4.4 Opening a trade

Atlas receives the entry externally via webhook and relays it to PickMyTrade. The UI is observational; it does not present a pre-entry checklist or an Atlas-owned “candidate” decision in the live product. Entry scoring happens after the entry and is based on similar completed trades. It is therefore evidence/review, not a safe pre-entry authorization.

### 4.5 Managing an active trade

Dashboard shows current position; AI Copilot shows current trade, intelligence, risk, and deterministic client-side observations. The trader must leave Dashboard to see Copilot. Available trade state is limited to the latest update, not a full price path. There is no deterministic action state for HOLD/REDUCE/EXIT and no explicit invalidation monitoring contract.

### 4.6 Reviewing a completed trade

Dashboard trade history links to Trade Detail. Trade Detail provides entry, stop, target, realized P&L, factors, lifecycle events, post-trade review, and PMT diagnostics. This is the most coherent journey. Friction remains because there is no Trades index, comparison workflow, tagging/journaling, or direct link from a completed trade into relevant historical setup research.

### 4.7 Requesting AI analysis

The AI page combines open-trade assistance, paid on-demand reports, and a global note timeline. Entry explanations and reviews are traceable to a trade, but the page does not distinguish deterministic metrics from LLM prose as strongly as the architecture does. Report generation is a paid side effect presented beside read-only content without a cost/confirmation product policy.

### 4.8 Research and diagnostics

Research is powerful but fragmented across nine routes. It mixes frozen dataset baselines, live episode inspection, operational readiness, hypothesis ranking, lineage, governance, and run availability. This is appropriate for a research workstation but not for primary trading navigation.

## 5. Problems and Friction

1. **No canonical “now” object.** The UI assembles current position, risk, facts, setups, and AI independently. There is no versioned read model for the trader’s present decision context.
2. **Engine architecture leaks into navigation.** Rule Engine, Setup Engine episodes, dataset certification, and ledger terms are routes rather than evidence layers beneath user questions.
3. **The Dashboard answers operational health before market opportunity.**
4. **Market state is available in the backend model but not through the frontend contract.**
5. **Existing Market Context and Strategy Engine are not live-product capabilities.** They are composed through replay/research paths and have no live API.
6. **Recommendation semantics are undefined.** `WAIT/PREPARE/ENTER/HOLD/REDUCE/EXIT` mixes opportunity state with position-management state and requires a formal state machine.
7. **AI is presented as a page, not a cross-cutting explanation layer.**
8. **Trade history lacks a home.** Dashboard acts as both current cockpit and trade archive.
9. **System health is duplicated.** Important degradations should be visible globally; detailed diagnostics should be secondary.
10. **Freshness is inconsistent across trader surfaces.** Research envelopes are explicit; dashboard trade/risk cards rely mostly on polling/live connection state.
11. **Fixed instrument/strategy identity is embedded in the shell.** This may be acceptable for a single-strategy product, but it is an unresolved product decision.
12. **The action surface risks false precision.** Confidence labels and an eventual ENTER recommendation need sample-size, data-quality, and invalidation provenance.

## 6. Proposed Product Information Architecture

### 6.1 Dashboard

**Purpose:** Immediate session, opportunity, risk, and position posture.

**Questions:** Is data fresh? What session/regime/bias is active? Is a setup forming or active? Am I allowed to act? Is a trade open? What is the deterministic recommended posture and why?

**Sections, in priority order:**

1. safety/freshness exception banner;
2. session clock and market state;
3. deterministic action card with reasons;
4. active setup and evidence;
5. risk budget;
6. open trade and invalidation;
7. recent high-priority events.

**Merge:** current Dashboard, selected Market View facts, Active Setup summary, Account risk summary, current-position Copilot explanation.

**Required data:** a composed, versioned `TraderNow`/decision-context endpoint.

### 6.2 Market

**Purpose:** Explain the deterministic market picture behind the Dashboard.

**Questions:** What is price doing relative to references? Which facts are true? Which setups are active/forming? How fresh and complete is the evidence?

**Sections:** price/reference map; session and regime; multi-timeframe trend/structure; liquidity context; VWAP/ATR; facts; setup cards; activation timeline; evidence drawer.

**Merge:** Market View, Active Setups, Timeline. Preserve Rule Engine and Episode Inspector as advanced diagnostics.

**Data available:** MarketState fields, rule facts, setup outputs, live episodes.
**Missing live product data:** exposed MarketContext, strategy decisions, a stable “forming”/readiness model, and possibly raw bars for charting.

### 6.3 Trades

**Purpose:** Manage the open trade and review completed trades.

**Questions:** What is open? What is the risk/invalidation state? What changed? How did completed trades perform and why?

**Sections:** open trade; trade-management state; trade list with filters; detail/timeline; performance analytics; AI review; diagnostics drawer.

**Merge:** Dashboard trade history, Trade Detail, Analytics, trade-related Activity.

**Missing:** `/trades` index, full update history, trader journal/annotations, strategy-decision provenance at entry, replay link.

### 6.4 AI

**Purpose:** Evidence-bound narrative and coaching.

**Questions:** What does the deterministic state mean? What changed? What should I pay attention to? What did I learn?

**Sections:** pre-session briefing; current-market explanation; active-trade explanation; post-trade review; daily/weekly reports; evidence citations and freshness.

**Merge:** current AI page plus explanations embedded contextually in Dashboard/Market/Trades.

**Principle:** AI is both a top-level archive/workspace and an inline explanation layer. It is never the source of market facts, risk gates, or execution actions.

### 6.5 Research

**Purpose:** Validate, compare, replay, and govern strategies.

**Sections:** overview/readiness; hypotheses/leaderboard; replay; statistical baseline; setup/episode profiling; dataset health; lineage; promotion governance; operations.

**Merge:** all `/research*`, Episode Inspector, Dataset Health, raw Rule Engine diagnostics, and Run Center.

**Presentation:** default to interpreted tables/charts; put raw JSON and fingerprints in advanced evidence views.

### 6.6 Settings

**Purpose:** Configure and diagnose the trading assistant without entering the research workflow.

**Sections:** account/risk parameters (initially read-only if backend does not support writes); integrations; instrument/strategy selection; data/source health; notifications; AI model/cost policy; advanced diagnostics and Activity.

**Merge:** Account, Connection Status detail, integration status, Activity/system filters, PMT diagnostic access.

**Missing:** dedicated settings APIs and write authorization/governance. Do not create editable risk controls until ownership, validation, audit, and enforcement are approved.

## 7. Ideal Dashboard Specification

### 7.1 Ten-second hierarchy

The first viewport should answer:

1. **Can I trust the data?**
2. **Where are we in the session?**
3. **What is the deterministic market posture?**
4. **Is there a qualified setup?**
5. **What action state applies?**
6. **What risk or open-trade constraint overrides it?**

Recommended visual order:

1. **Exception strip:** stale/degraded data, breached risk, integration failure.
2. **Action card:** `WAIT`, `PREPARE`, `ENTER`, `HOLD`, `REDUCE`, or `EXIT`; direction where applicable; timestamp; reason codes; evidence link.
3. **Market now:** session phase, volatility regime, context quality, trend, VWAP relationship, nearest liquidity/reference levels.
4. **Setup:** detector name, status, direction interpretation, age, severity, evidence.
5. **Risk/trade:** remaining daily loss/drawdown, exposure, open trade, stop/target/invalidation and current P&L.
6. **What changed:** last three material events.
7. **AI explanation:** short prose generated only from the exact structured snapshot above.

### 7.2 Availability and ownership matrix

| Dashboard information | Status | Source / requirement |
|---|---|---|
| System/API freshness | Available | `status`, live connection, research envelopes; needs one consistent trader-facing freshness policy. |
| Account risk and exposure | Available | `risk`. |
| Open trade and latest update | Available | `trades/current`; latest update only. |
| Session name/RTH flag and levels | Exists in raw backend data | `MarketState`; not currently exposed through BFF/UI. |
| Session phase/progress | Backend domain logic exists | `market_context`; not exposed live. |
| Volatility regime/context quality | Backend domain logic exists | `market_context`; not exposed live. |
| VWAP relationship | Available as deterministic fact | Rule Engine. Raw VWAP/reference values need MarketState read exposure. |
| Trend | Available as raw MarketState fields and `trend_5m` fact | Needs product interpretation/multi-timeframe policy. |
| Liquidity context | Raw fields and facts exist | Needs live read model and presentation policy. |
| Active setup/severity/evidence | Available | Setup Engine latest and live episodes. |
| Setup direction interpretation | Backend domain logic exists | `setup_interpretation`; currently replay-only/no live API. |
| Candidate/rejected/no-signal | One backend strategy exists | `strategy_engine`; currently replay-only/no live API. |
| Historical setup confidence | Available after trade entry/on demand | `intelligence`; deterministic but may have insufficient history. |
| WAIT/PREPARE/ENTER | Missing as a product contract | Must be deterministic policy over context/setup/strategy/risk/freshness. |
| HOLD/REDUCE/EXIT | Missing | Requires explicit trade-management rules and better update/invalidation data. |
| AI explanation | Partially available | Claude narratives exist for entry/review/reports; live snapshot explanation contract is missing. |

### 7.3 Action-state rules

The six labels should be modeled as two related state machines:

- **Flat:** `WAIT → PREPARE → ENTER`
- **In position:** `HOLD → REDUCE / EXIT`

`ENTER` must mean “deterministic candidate meets policy,” not “send an order.” Atlas remains advisory unless separately approved. Risk breach, stale data, unknown context, or missing evidence must downgrade to a safe state, normally `WAIT` or `EXIT-REVIEW-REQUIRED` depending on position state. The LLM must not perform this transition.

## 8. Intelligence Layer Architecture

| Layer | Inputs | Outputs | Ownership / behavior | Persistence and API | Failure / LLM |
|---|---|---|---|---|---|
| 1. Raw Market Data | TradingView today; future feeds | Canonical `MarketState` | Market Engine; deterministic validation/translation | Persist canonical states; expose bounded latest/history through server API | Reject invalid data; never fabricate. LLM forbidden. |
| 2. Deterministic Facts | MarketState window | typed facts or `InsufficientData` | Rule Engine | Computed on demand today; API exists | Partial facts remain explicit insufficient data. LLM forbidden. |
| 3. Market Context | aligned market window, calendar, ATR history, upstream session labels | session phase/progress, volatility regime, quality, fingerprint | `market_context`; deterministic | Currently composed in replay; needs live API and likely snapshot persistence/audit policy | Unknown/degraded are first-class. LLM forbidden. |
| 4. Setup Detection | Rule outputs/window | detected/severity/evidence; episodes; interpretation | Setup Engine + Setup Interpretation | latest/episodes APIs exist; interpretation needs live exposure | Insufficient data remains explicit. LLM forbidden. |
| 5. Risk and Trade State | account config, trades, latest prices, candidate | risk snapshot, position state, deterministic strategy decision | Risk, Trades, Strategy Engine | risk/trade APIs exist; live strategy decision API missing; persist decision provenance if shown/actionable | Safe degradation; no new entries when freshness/risk gates fail. LLM forbidden. |
| 6. AI Narrative | immutable structured snapshot from Layers 2–5 plus historical outcomes | explanation, briefing, review, questions | AI orchestration; probabilistic prose only | Persist prompt-input references, model, output, timestamps, evidence IDs | Failure never blocks deterministic UI. LLM allowed only here. |
| 7. User-Facing Recommendation | deterministic strategy decision, risk policy, freshness, position state | action state + reasons + invalidation + provenance | New Recommendation Policy layer; deterministic state machine | Persist/replay if surfaced as historical advice; one composed read API | Fail closed to safe posture. LLM may explain, never choose or override. |

### 8.1 Important boundary

Layer 7 is not “the LLM layer.” It is a deterministic product policy translating machine outputs into a bounded vocabulary. Layer 6 can render “Why Atlas says WAIT,” but the authoritative state remains a machine-verifiable object.

## 9. AI Responsibility Boundaries

### 9.1 AI should explain

- what deterministic facts and context classifications mean;
- why a setup was detected, rejected, or unavailable;
- why a risk gate changed the allowed posture;
- how the current setup compares with similar completed trades;
- what changed since the previous structured snapshot;
- post-trade lessons grounded in recorded entry, management, exit, and outcome;
- daily/weekly summaries of deterministic analytics.

### 9.2 AI may recommend

AI may offer **non-authoritative attention guidance**, such as “watch the overnight high” or “the setup has limited historical precedent,” only when:

- the referenced evidence is present;
- the statement is tagged as narrative;
- the deterministic action state is shown separately;
- it cannot contradict a risk gate or deterministic state;
- it carries data/model timestamps.

### 9.3 AI must not decide

- raw-price pattern recognition;
- fact, regime, session, setup, direction, risk, or stop/target computation;
- whether an order is sent, modified, reduced, canceled, or blocked;
- whether stale/unknown data should be treated as valid;
- promotion of research hypotheses;
- credential/integration configuration;
- retrospective facts such as P&L or whether a stop was hit.

### 9.4 Hallucination controls

1. Generate from a versioned structured snapshot, not arbitrary database text.
2. Include stable evidence identifiers, timestamps, and definition versions.
3. Require every factual sentence to reference one or more allowed evidence fields.
4. Render citations as links to evidence drawers.
5. Validate output against a response schema; reject unsupported action verbs/claims.
6. Compare narrative snapshot timestamp with live snapshot; mark stale and suppress if materially outdated.
7. Never silently fall back from missing evidence to model judgment.
8. Preserve model, prompt version, input snapshot hash, and output for audit.
9. Keep deterministic numbers out of model generation; interpolate or verify them from source data.
10. Make AI failure a local narrative failure, never a trading-state failure.

## 10. Existing Data vs Missing Data Matrix

| Capability | Available now | Derivable now | Missing / work required |
|---|---|---|---|
| OHLC, volume, session/reference fields | Canonical `MarketState` backend | latest market snapshot | Frontend allowlist/client/product read model. |
| Facts | Seven Rule Engine facts | compact market summary | Trader-language mapping and evidence hierarchy. |
| Setups | Four registered deterministic setups | active/age/recent activation from episodes | Setup readiness/forming semantics if desired. |
| Session phase | `market_context` code | pre-open/opening/mid/closing/overnight | Live composition/API. |
| Volatility regime | `market_context` code | compressed/normal/expanded with quality | Live composition/API and product validation. |
| Setup direction | `setup_interpretation` code | bullish/bearish/ambiguous/unavailable | Live composition/API. |
| Strategy candidate | One deterministic plugin | candidate/rejected/no-signal with reasons | Live evaluation/API, registry/product policy, audit persistence. |
| Risk | Complete current snapshot | safe-entry gate inputs | Formal coupling to recommendation policy. |
| Trade state | Current/list/detail and latest update | basic HOLD context | Full update history, management rules, explicit invalidation monitoring. |
| Historical intelligence | Similar trades, confidence rubric, factors | setup historical context | Better sample-quality policy and pre-entry timing contract. |
| Performance | Summary/equity/drawdown/breakdowns | Trades performance view | tagging, richer attribution, strategy version/context joins. |
| AI narratives | Entry review, post-trade review, reports | evidence-bound explanation pattern | Live market briefing/snapshot narrative contract and citations. |
| Recommendation | None in product | narrow candidate policy from existing strategy | Approved action state machine, safety gates, live API, audit. |
| Order flow | None; code explicitly says current setups are not order flow | None | New data vendor/adapter, canonical model, facts, validation, cost decision. |
| Settings | Account/integration data are readable | status summary | Product ownership and safe write APIs if edits are desired. |

## 11. Proposed Sprint Roadmap

### Sprint 12 — Product IA and Dashboard Contract

**Objective:** Define the product shell and canonical trader questions before new intelligence work.
**Outcome:** Approved navigation/wireframes and a versioned `TraderNow` contract specification with honest placeholders.
**Backend:** Contract design only; inventory composition sources and freshness rules.
**Frontend:** Consolidate navigation to six destinations; introduce route aliases/shells without deleting diagnostics.
**Dependencies:** Product decisions D1–D6 below.
**Acceptance:** Every existing route has a destination; no capability loss; Dashboard priority validated with trader scenarios; no invented recommendation.
**Risk:** Cosmetic reorganization without agreeing on decision semantics.
**Split:** 12A contract/workflow; 12B navigation/shell.

### Sprint 13 — Live Context Productization

**Objective:** Expose existing deterministic Market Context and Setup Interpretation safely for the latest live bar.
**Outcome:** Market shows session phase, volatility regime, quality, setup direction, freshness, and evidence.
**Backend:** Compose existing packages on live history; add versioned read endpoint; validate live/replay equivalence.
**Frontend:** Market summary and evidence drawers.
**Dependencies:** TraderNow/context contracts; data freshness policy.
**Acceptance:** Same input produces identical replay/live outputs; unknown/degraded states tested; no LLM.
**Risk:** Existing packages were designed through replay consumers; live performance/alignment assumptions need proof.
**Split:** 13A equivalence/API; 13B Market UI.

### Sprint 14 — Deterministic Opportunity and Recommendation Policy

**Objective:** Turn setup/context/risk into a safe, bounded flat-position action state.
**Outcome:** Dashboard shows WAIT/PREPARE/ENTER with reasons and evidence.
**Backend:** Live Strategy Engine evaluation; new Recommendation Policy; audit snapshot.
**Frontend:** action card, reason codes, invalidation/evidence.
**Dependencies:** Sprint 13, decisions on advisory/execution boundary.
**Acceptance:** State-machine tests; stale/risk/unknown always fail safe; no LLM decisions; replayable provenance.
**Risk:** “ENTER” may be interpreted as execution advice; require wording/legal/product approval.
**Split:** 14A strategy live exposure; 14B policy; 14C UI.

### Sprint 15 — Trades Workspace and Live Trade Assistant

**Objective:** Consolidate open-trade management, history, detail, and analytics.
**Outcome:** `/trades` becomes the home for open and completed trades; deterministic HOLD/REDUCE/EXIT only if rules are approved.
**Backend:** Full trade update history and management-state contract; no order execution changes.
**Frontend:** Trades index, open-trade cockpit, detail/review, analytics subsection.
**Dependencies:** Recommendation semantics and update-history design.
**Acceptance:** Complete trade journey without Dashboard/AI/Analytics hopping; every management recommendation has deterministic reasons.
**Risk:** Incomplete price/update data can make management advice unsafe.
**Split:** 15A Trades IA; 15B update history; 15C management policy.

### Sprint 16 — Evidence-Bound AI Analyst

**Objective:** Add narrative on top of the structured live snapshot.
**Outcome:** Pre-session/current-market explanations and contextual “why” panels.
**Backend:** snapshot hashing, prompt/response schemas, citation mapping, persistence/cost controls.
**Frontend:** inline explanations plus AI archive.
**Dependencies:** stable Layers 3–7 contracts.
**Acceptance:** every claim traceable; stale narrative suppressed; deterministic values unchanged; AI failure isolated.
**Risk:** plausible unsupported prose and cost growth.
**Split:** 16A evidence contract; 16B prompts/evaluation; 16C UI.

### Sprint 17 — Replay and Learning

**Objective:** Let the trader review what Atlas knew and recommended at each historical moment.
**Outcome:** replay market/context/setup/recommendation/trade sequence; compare decisions/outcomes.
**Backend:** persist/reconstruct recommendation snapshots; replay API.
**Frontend:** replay timeline and journal links.
**Dependencies:** persisted recommendation provenance.
**Acceptance:** deterministic reproducibility/version disclosure; no hindsight leakage.
**Risk:** definition/version drift and accidental future-data leakage.
**Split:** yes.

### Sprint 18 — Research Workspace Consolidation

**Objective:** Consolidate current nine-route research/diagnostic surface.
**Outcome:** coherent Research sections for hypotheses, replay, data quality, governance, and advanced diagnostics.
**Backend:** mostly existing APIs; selectively expose approved operations.
**Frontend:** replace raw JSON defaults, preserve lineage/fingerprints in evidence views.
**Dependencies:** target IA and replay.
**Acceptance:** all current functionality reachable; fewer primary routes; clearer live/frozen provenance.
**Risk:** hiding tools researchers still need; validate with research-user workflow.

### Future — Order-Flow Integration

**Objective:** Add bid/ask, delta, footprint, imbalance, or absorption only if a product hypothesis justifies it.
**Scope:** vendor selection, canonical data model, storage, integrity, deterministic facts, research validation, cost/latency operations.
**Dependency:** explicit product decision and data license.
**Risk:** major scope/cost increase and false confidence. This is not a UI widget sprint.

## 12. Product Decision Register

| ID | Decision | Options | Recommendation | Consequence | Blocks? |
|---|---|---|---|---|---|
| D1 | Product mode | Single instrument/strategy; multi-instrument; multi-strategy | Keep single MNQ strategy for the first assistant release; design identity explicitly | Avoids premature selector/config complexity | Blocks IA labels and Settings. |
| D2 | Recommendation authority | Informational; advisory action labels; execution-connected | Advisory deterministic labels only; no execution | Keeps current safety boundary | Blocks recommendation sprint. |
| D3 | Meaning of ENTER | Qualified opportunity; user authorization; order submission | Qualified opportunity only, labeled “Entry conditions met” | Reduces dangerous ambiguity | Blocks copy and state machine. |
| D4 | Management actions | HOLD only; HOLD/REDUCE/EXIT; no management labels | Defer REDUCE/EXIT until update history and explicit rules exist | Prevents unsafe inference from latest-only price data | Blocks Live Trade Assistant scope. |
| D5 | Dashboard density | One-screen cockpit; scrollable overview; configurable widgets | One-screen critical cockpit plus evidence drill-down | Optimizes ten-second comprehension | Blocks wireframe. |
| D6 | AI placement | Separate page; inline only; hybrid | Hybrid: inline explanations plus AI archive | Preserves context and discoverability | Blocks AI IA. |
| D7 | Paid report UX | Immediate buttons; confirmation; scheduled reports | Confirm with cost disclosure; add scheduling later | Prevents accidental spend | Does not block deterministic work. |
| D8 | Settings editability | Read-only; editable risk/integrations; admin-only | Read-only first; design audit/validation before writes | Avoids accidental production configuration changes | Blocks Settings writes only. |
| D9 | Research audience | Trader-visible; advanced mode; separate internal app | Keep in same app under Research/Advanced initially | Preserves capability without clutter | Does not block shell. |
| D10 | Context engine reuse | Build new; expose existing; replace existing | Reuse existing packages after live-equivalence review | Avoids duplicate domain logic | Blocks Sprint 13 implementation approach. |
| D11 | Strategy coverage | One reference strategy; all four setups; plugin portfolio | Start with the existing reference strategy, label coverage explicitly | Honest narrow scope | Blocks recommendation breadth. |
| D12 | Recommendation persistence | Current-only; persist every change; event-based material changes | Persist material state changes with input hashes | Enables audit/replay without excessive volume | Blocks replay and AI traceability. |
| D13 | Market charting | No chart; lightweight references; full charting workstation | Start with reference-level/context visualization; defer full chart platform | Controls frontend/data scope | Blocks Market visual design. |
| D14 | Order-flow investment | Now; later; never | Later, behind a validated research hypothesis | Avoids expensive speculative integration | No immediate block. |

## 13. Recommended Immediate Next Sprint

### Sprint 12A — Trader Workflow and `TraderNow` Contract

This should be a product/contract sprint, not a broad UI implementation.

Deliverables:

1. approved six-destination sitemap and route migration map;
2. Dashboard wireframe for flat, setup-forming, candidate, open-trade, stale-data, and risk-breach states;
3. formal action-state vocabulary and transition table;
4. `TraderNow` read-model schema containing provenance, timestamps, definition versions, and explicit missing-data states;
5. mapping from every schema field to an existing source, existing unexposed domain capability, or new logic;
6. live-equivalence test plan for `market_context`, `setup_interpretation`, and `strategy_engine`;
7. AI evidence/citation contract draft;
8. acceptance tests expressed as trader scenarios.

Why this sprint first:

- Navigation can be changed safely only when destination responsibilities are settled.
- The backend already has more intelligence than the frontend exposes; a new engine sprint would risk duplication.
- A visual Dashboard without an authoritative composed contract would recreate today’s client-side fragmentation.
- AI work before deterministic recommendation semantics would put prose ahead of truth.

## 14. Explicit Non-Goals

- No code, route, navigation, API, database, Railway, or deployment change is authorized by this report.
- No order placement, modification, cancellation, blocking, or broker integration change.
- No LLM interpretation of raw OHLC, volume, DOM, or order-flow data.
- No LLM-generated risk limits, setups, direction, stops, targets, or authoritative action state.
- No claim that current Strategy Engine output is already live or covers all setups.
- No claim that Market Context is currently available to the frontend.
- No new “Market Context Engine” parallel to the existing `live/atlas/market_context` package.
- No order-flow integration without a separate data/product/research decision.
- No editable Settings until authorization, validation, audit, and ownership are designed.
- No removal of research/diagnostic capability merely to reduce route count; consolidate and demote it first.
- No use of historical outcomes in live decisions without time-safe, leakage-free evaluation.
- No assumption that confidence is a probability of winning.

---

## Evidence Index

Principal repository evidence used:

- Global shell/navigation: `frontend/src/app/layout.tsx`, `frontend/src/components/AppNav.tsx`
- Current pages: `frontend/src/app/**/page.tsx`
- BFF API policy/client: `frontend/src/lib/proxyAllowlist.ts`, `frontend/src/lib/proxyClient.ts`
- Trader API clients: `frontend/src/lib/{trades,risk,status,stats,analytics,activity,ai,ruleEngine,setupEngine}Api.ts`
- Live episode UI: `frontend/src/lib/useLiveEpisodes.ts`, `frontend/src/components/{ActiveSetupBundle,Timeline,EpisodeInspector}.tsx`
- Raw market model: `live/atlas/market_engine/models.py`
- Rule facts: `live/atlas/rule_engine/registry.py`
- Setup registry: `live/atlas/setup_engine/registry.py`
- Live setup endpoints: `live/atlas/api/v1/setup_engine.py`
- Market Context: `live/atlas/market_context/models.py`, `live/atlas/market_context/service.py`
- Setup Interpretation: `live/atlas/setup_interpretation`
- Replay composition: `live/atlas/replay_engine/models.py`, `live/atlas/replay_engine/service.py`
- Strategy decision model/plugin: `live/atlas/strategy_engine/models.py`, `live/atlas/strategy_engine/strategies/displacement_volume_context.py`
- Risk/trades: `live/atlas/risk.py`, `live/atlas/api/v1/{risk,trades}.py`
- Deterministic historical intelligence: `live/atlas/intelligence.py`
- AI orchestration: `live/atlas/ai.py`, `live/atlas/services/claude.py`

All statements labeled “exists” refer to repository code, not necessarily a deployed user-facing capability. Where code exists without a live API/frontend, this report states that limitation explicitly.
