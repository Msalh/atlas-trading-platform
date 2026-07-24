# Sprint 12A Product Contract — Trader Decision Center

**Status:** Product contract for review; no implementation authorization
**Repository reviewed:** `main` at `f983b21`
**Parent decision:** Architecture Review 2.0 accepted with Product Owner refinements
**Scope:** Product behavior, information architecture, contracts, safety policy, and future acceptance criteria only

## 1. Executive Decision

Atlas will become a trader decision center built around a versioned `TraderNow` read model. The Dashboard will provide the compressed operational answer; Market will provide the expanded deterministic evidence behind it. AI remains a cross-cutting explanation layer and a top-level archive, never the authority that selects a trading state.

The authoritative sequence is:

`Raw Market Data → Deterministic Facts → Market Context → Setup Interpretation → Risk and Trade State → Decision Engine → AI Explanation`

The formal contract should use **two related state machines selected by position state**, not one combined state machine:

- flat-position machine: `WAIT`, `PREPARE`, `ENTER`;
- in-position machine: `HOLD`, `REDUCE`, `EXIT`.

This avoids invalid transitions such as `WAIT → REDUCE`, makes preconditions explicit, and permits the flat-position policy to ship before safe in-position management rules exist. A single top-level `decision.state` remains convenient for clients, while `decision.workflow` identifies which machine owns it. Internally, `ENTER` means only “entry conditions met according to the deterministic policy.” The default user-facing label is **ENTRY CONDITIONS MET**.

Sprint 12A defines the contract only. Sprint 12B may compose existing backend packages and expose a versioned endpoint. It must not create a second Market Context Engine, Setup Interpretation layer, or Strategy Engine.

## 2. Product Principles

1. **Dashboard is the decision center.** It answers the current operational questions in approximately 5–10 seconds.
2. **Determinism before narration.** The Decision Engine owns the authoritative state. AI can explain the state but cannot select, alter, suppress, or execute it.
3. **Evidence is one interaction away.** Dashboard compresses; Market expands the same snapshot and trace without recomputation in the browser.
4. **Unknown is a valid result.** Missing, insufficient, stale, degraded, disconnected, and not-applicable states must never be rendered as false, neutral, or safe by default.
5. **Fail safe.** Untrusted inputs cannot produce a new entry-qualified state.
6. **Reuse existing domain logic.** Live productization must compose `live/atlas/market_context`, `live/atlas/setup_interpretation`, and `live/atlas/strategy_engine`.
7. **One authoritative snapshot.** Dashboard, Market, contextual AI, and future replay consume the same identity, timestamps, versions, and evidence references.
8. **Advisory, not execution.** No decision state places, changes, approves, blocks, or cancels an order.
9. **Confidence is provenance-bound.** It is never described as win probability unless a separately validated statistical model explicitly supports that meaning.
10. **Progressive disclosure.** Trader-facing interpretation comes first; raw facts, fingerprints, JSON, and engineering diagnostics remain accessible under evidence or Research.

## 3. Final Information Architecture

### 3.1 Top-level destinations

| Destination | Trader question | Primary contents |
|---|---|---|
| **Dashboard** | What matters now, and what posture is allowed? | trust/freshness, session, market posture, setup, Decision Engine state, risk override, open position, recent changes, contextual AI |
| **Market** | What deterministic evidence produced that answer? | market structure, session/context, VWAP, liquidity, facts, setups, interpretations, strategy evaluation, Decision Trace |
| **Trades** | What am I managing, and what happened previously? | current position, trade management evidence, history, detail, performance |
| **AI** | What has Atlas explained or reported? | contextual explanation archive, notes, intelligence, daily/weekly report history |
| **Research** | What evidence validates the system? | replay, baselines, dataset health, experiments, lineage, promotion governance, engine diagnostics |
| **Settings** | How is the assistant configured and connected? | account/risk display, source/integration health, instrument/strategy identity, notifications and cost policy, advanced activity |

### 3.2 Dashboard–Market relationship

Dashboard and Market must share a snapshot identifier and Decision Trace identifier. Selecting “Why?”, a failed condition, setup, risk gate, or evidence reference on Dashboard opens the corresponding Market section without losing snapshot context. Market may show more detail but must not derive a different answer client-side.

### 3.3 AI placement

AI is hybrid:

- contextual entry points appear beside deterministic decisions and evidence;
- `/ai` remains the durable archive for notes, intelligence, and reports;
- every explanation identifies the snapshot and trace it explains;
- if AI is unavailable, deterministic product functions remain complete.

## 4. Route Migration Map

This is a target ownership map, not authorization to rename or remove routes.

| Current route | Verified current purpose | Target destination / section | Migration treatment |
|---|---|---|---|
| `/` | position, trade history, connection, daily stats | Dashboard | Replace composition after contract implementation; retain useful position/risk summaries |
| `/market-view` | Rule Engine facts and Setup Engine latest | Market / Now | Canonical target route becomes `/market`; redirect later |
| `/rule-engine` | raw/latest deterministic facts | Research / Advanced diagnostics; linked Market evidence | Preserve diagnostic access; remove from primary trading navigation |
| `/active-setups` | live setup snapshots | Market / Setups | Merge |
| `/timeline` | live setup episode timeline | Market / Timeline | Merge |
| `/episodes` | episode inspection | Research / Replay & diagnostics | Merge; link from Market evidence |
| `/account` | account risk and display-only kill-switch state | Settings / Account & risk | Merge; no implied editable/enforced controls |
| `/analytics` | performance summary, equity, drawdown, breakdown | Trades / Performance | Merge |
| `/trades/[correlationId]` | trade detail/timeline/intelligence | Trades / Trade detail | Preserve dynamic detail under target Trades ownership |
| `/ai` | copilot, report history, notes | AI | Retain; clarify archive/report role |
| `/activity` | activity/event stream | Settings / Advanced activity | Merge |
| `/research` | statistical baseline RE-1/RE-2 | Research / Baselines | Merge |
| `/dataset-health` | certification and warnings | Research / Data quality; trust summary linked from Dashboard | Merge |
| `/research-ops` | research operations overview | Research / Overview | Canonical target route becomes `/research`; resolve legacy collision during implementation planning |
| `/research-ops/leaderboard` | ranked hypotheses | Research / Leaderboard | Merge |
| `/research-ops/snapshot` | frozen snapshot inspection | Research / Snapshots | Merge |
| `/research-ops/promotion/queue` | promotion candidates | Research / Governance / Queue | Merge |
| `/research-ops/promotion/history` | promotion decision history | Research / Governance / History | Merge |
| `/research-ops/run-center` | research operational readiness | Research / Operations | Merge |
| none | consolidated open/current/history landing page | Trades | New route required |
| none | product configuration workspace | Settings | New route required |

Implementation must preserve deep links with redirects or aliases until telemetry and user confirmation permit removal. No current diagnostic capability is deleted merely because it leaves top-level navigation.

## 5. Trader Workflow Scenarios

### 5.1 Pre-session

1. Trader opens Dashboard.
2. Trust strip states source connectivity, last input time, freshness, and any unavailable context.
3. Session card shows `pre_open` when existing Market Context can compute it; otherwise it says unavailable, never infers from browser time.
4. Decision is `WAIT` because the market is not entry-eligible under the approved policy.
5. “Monitor next” identifies deterministic conditions or levels, if available.
6. Trader opens Market for levels and evidence without changing snapshot identity.

### 5.2 Flat, no setup

1. Position selector resolves to `flat`.
2. Facts and context may be current, but no relevant strategy trigger exists.
3. Strategy disposition may eventually be `no_signal`; until live composition exists it is unavailable.
4. Decision is `WAIT`; trace distinguishes “no signal” from “insufficient data.”
5. Dashboard shows the next observable conditions, not speculative advice.

### 5.3 Setup forming

1. A Setup Engine result or active episode exists but not all deterministic policy conditions pass.
2. Setup interpretation supplies direction only when computable.
3. Decision becomes `PREPARE` if freshness, quality, risk, and policy-specific forming conditions pass.
4. Trace lists satisfied, failed, and unavailable conditions separately.
5. Market opens focused on the setup’s facts, evidence, direction source, and invalidation.

### 5.4 Entry conditions met

1. Existing deterministic layers are current and trusted enough for the policy.
2. Strategy disposition is `candidate`, risk gates allow consideration, and all required conditions pass.
3. Internal state becomes `ENTER`; UI says **ENTRY CONDITIONS MET** with direction and timestamp.
4. Copy explicitly says this is not an order, authorization, or execution.
5. Trace records all inputs, versions, transition reason, and snapshot hash.

### 5.5 Stale or degraded data

1. A required input exceeds its freshness threshold, is disconnected, has an invalid timestamp, or context quality is degraded/unknown.
2. No new `ENTER` transition is permitted.
3. Flat workflow resolves to `WAIT`, with a machine-readable fail-safe reason.
4. An existing position is never silently told `HOLD` solely because data is unavailable; until management policy exists, state is unavailable and the UI presents a safety escalation message, not trading advice.
5. Dashboard’s exception strip leads to source-level diagnostics.

### 5.6 Risk breach

1. Current `RiskSnapshot` exposes daily loss, trailing drawdown, exposure, and display-only kill-switch indications.
2. Decision Engine treats approved risk gates as overriding inputs once Sprint 14 implements their formal coupling.
3. Flat workflow resolves to `WAIT`.
4. The UI must not claim the existing kill switch is enforced: `live/atlas/risk.py` explicitly sets `KillSwitchStatus.enforced = False`.
5. In-position action remains policy-dependent; a breach does not justify inventing `REDUCE` or `EXIT`.

### 5.7 Open trade

1. Current trade and risk position are shown in the first viewport.
2. Workflow selector chooses `in_position`.
3. Until full update history and management rules exist, authoritative management decision is unavailable—not automatically `HOLD`.
4. Latest price, P&L, stop, target, exposure, and known invalidation are displayed with provenance.
5. Future `HOLD`, `REDUCE`, or `EXIT` must come only from approved deterministic rules and current-enough data.

### 5.8 Completed-trade review

1. Trader opens Trades history and selects a correlation ID.
2. Detail shows the recorded trade timeline, outcome, applicable AI notes, and deterministic historical intelligence.
3. Review distinguishes what was known at decision time from after-the-fact results.
4. Future replay uses persisted Decision Traces and versions; it must not recompute with future data or silently substitute new definitions.

## 6. Dashboard Specification

### 6.1 Information priority

The first viewport follows this order:

1. **Trust and exceptions:** source status, freshness, degraded/unknown inputs, risk breach.
2. **Authoritative action:** label, direction, workflow, timestamp, transition reason, advisory disclaimer.
3. **Market now:** session phase/progress, volatility regime, context quality, trend, VWAP relationship, nearest liquidity/reference levels.
4. **Setup and strategy:** detected/forming/active state, severity, interpreted direction/source, strategy disposition and reasons.
5. **Risk and position:** account limits, remaining buffers, exposure, current trade, stop/target/invalidation.
6. **Monitor next:** deterministic failed/unavailable conditions and relevant evidence.
7. **What changed:** recent material Decision Engine transitions.
8. **Explain:** evidence-bound AI explanation, visually subordinate to authoritative fields.

### 6.2 Detailed text wireframe

```text
┌ TRUST STRIP ─ data CURRENT | context TRUSTED | risk OK | generated 14:35:03Z ┐
├───────────────────────────────────────────────────────────────────────────────┤
│ DECISION                                                                    │
│ PREPARE · LONG BIAS                     changed 14:35:00Z                    │
│ 3/5 conditions satisfied · entry conditions are NOT met                     │
│ [Why?] [Open full evidence in Market]                                       │
├──────────────────────────────┬────────────────────────────────────────────────┤
│ MARKET NOW                   │ SETUP                                          │
│ Mid-session · Normal vol     │ Displacement + volume · forming · normal       │
│ Above VWAP · near ONH        │ Direction bullish · source setup evidence      │
│ Quality trusted              │ Missing: acceptance condition X                │
├──────────────────────────────┼────────────────────────────────────────────────┤
│ RISK / POSITION              │ MONITOR NEXT                                   │
│ Flat · daily buffer …        │ Reclaim level … / volume confirmation …        │
│ exposure 0 / max …           │ Invalidation …                                 │
├──────────────────────────────┴────────────────────────────────────────────────┤
│ WHAT CHANGED: WAIT → PREPARE …                         [Explain this change] │
└───────────────────────────────────────────────────────────────────────────────┘
```

The UI must use an explicit “Unavailable” or “Insufficient data” presentation in place of any missing value. It must not render `0`, `false`, “neutral,” or `WAIT` as a generic substitute for unavailable upstream data.

## 7. Dashboard State Variants

| Variant | Required presentation | Authoritative behavior |
|---|---|---|
| Loading | stable skeleton preserving hierarchy; no action label | none until a validated snapshot arrives |
| No market data | source status, remediation, last known time if available | `WAIT` only if Decision Engine has a trace proving the fail-safe transition; otherwise decision unavailable |
| Disconnected | critical exception strip and retry state | no new entry qualification |
| Delayed | warning with input age and threshold | policy-defined; cannot silently imply current |
| Stale | critical state, affected inputs, last valid snapshot separated | flat workflow fails safe to `WAIT`; management unavailable unless approved stale-data rules say otherwise |
| Degraded/unknown context | reason and affected classifiers | cannot produce `ENTER` |
| Flat/no setup | `WAIT`, no-signal versus insufficient-data reason | show next deterministic monitor conditions |
| Setup forming | `PREPARE`, direction only if evidence-backed | show pass/fail/unavailable checklist |
| Entry qualified | internal `ENTER`, UI “ENTRY CONDITIONS MET” | advisory only; full trace required |
| Risk breach | critical risk override and display-only enforcement truth | no entry qualification |
| Open position | trade and risk dominate first viewport | choose in-position machine; no invented state |
| AI unavailable | deterministic snapshot and evidence remain usable | AI panel fails independently |
| Partial composition error | per-section missing state plus overall trust impact | fail-safe policy decides; never merge mismatched timestamps invisibly |

## 8. TraderNow Contract

### 8.1 Purpose

`TraderNow` is a versioned, server-composed, read-only projection for one symbol, timeframe, and strategy identity at one coherent decision moment. It is not a new domain engine. It references or serializes outputs owned by existing domains and the future Decision Engine.

### 8.2 Proposed top-level schema

The following is a contract proposal, not an implemented type:

```text
TraderNow
  schema_version
  snapshot_id
  generated_at
  input_snapshot_at
  identity
  trust
  market
  facts
  context
  setups
  strategy
  risk
  trade
  decision
  decision_trace
  changes
  evidence
  availability
  warnings
```

| Field | Required shape and semantics |
|---|---|
| `schema_version` | version of this transport/read-model schema |
| `snapshot_id` | immutable identifier for the composed response |
| `generated_at` | server generation time |
| `input_snapshot_at` | authoritative aligned input time; distinct from generation time |
| `identity` | symbol, timeframe, strategy ID/version, account scope where applicable |
| `trust` | overall freshness/trust plus per-source statuses and timestamps |
| `market` | bounded raw/reference fields from `MarketState`; never fabricated |
| `facts` | Rule Engine results, including explicit `InsufficientData` |
| `context` | existing `MarketContext` output and fingerprint |
| `setups` | Setup Engine outcomes plus existing Setup Interpretation outputs |
| `strategy` | existing `StrategyDecision` if evaluated live; otherwise explicit unavailable |
| `risk` | existing `RiskSnapshot`, including enforcement truth |
| `trade` | flat/open/unknown state and current trade projection |
| `decision` | future Decision Engine authoritative result |
| `decision_trace` | full trace or stable trace reference; required for authoritative decision |
| `changes` | bounded material transitions relative to previous snapshot |
| `evidence` | typed references resolvable by Market/Research and AI citation layer |
| `availability` | per-section `available`, `insufficient_data`, `not_implemented`, `not_applicable`, `disconnected`, `error` |
| `warnings` | bounded machine-readable warnings; never the sole carrier of availability |

### 8.3 Coherence rules

- Every decision-bearing input must identify its source timestamp and definition version.
- The server must align inputs and state the alignment policy. The browser must not zip independently fetched “latest” responses into an authoritative decision.
- `input_snapshot_at` is no newer than any required authoritative input.
- A decision without a Decision Trace is invalid.
- A referenced context fingerprint must match the Strategy Decision’s `context_fingerprint`.
- Position workflow selection must be explicit and traceable.
- Unknown or missing values use availability discriminators, not omitted fields with ambiguous meaning.
- The contract returns no LLM-generated authoritative fields.

## 9. Decision Engine Definition

The Decision Engine is a new deterministic policy/state-machine layer that consumes already-owned outputs. It does not replace or duplicate facts, context, setup interpretation, strategy evaluation, risk computation, or trade storage.

### 9.1 Inputs

- freshness and data-quality classifications;
- Rule Engine facts;
- `MarketContext`;
- Setup Engine outcomes and `SetupInterpretation`;
- `StrategyDecision`;
- approved fields from `RiskSnapshot`;
- position state and current trade;
- previous Decision Engine state;
- immutable policy definition and version.

### 9.2 Output

```text
Decision
  workflow: flat | in_position
  state: WAIT | PREPARE | ENTER | HOLD | REDUCE | EXIT
  user_facing_label
  direction: long | short | flat | unavailable
  decided_at
  policy_id
  policy_version
  trace_id
```

The output is bounded, machine-readable, auditable, and advisory. It contains no order command.

### 9.3 Ownership boundaries

- Rule Engine answers which facts hold.
- Market Context classifies session, regime, and quality.
- Setup Interpretation supplies the meaning/direction of detected setups.
- Strategy Engine evaluates a named strategy and emits candidate/rejected/no-signal.
- Risk computes account/trade risk information; current implementation is display-only.
- Decision Engine applies approved product policy to these outputs.
- AI explains a completed snapshot and trace.

## 10. Decision State Machine

### 10.1 Recommendation: two related machines

Use a workflow selector derived from authoritative position state:

```text
position = flat        → FlatDecisionState
position = open        → InPositionDecisionState
position = unknown     → decision unavailable / safety escalation
```

This produces one API union:

```text
FlatDecision     { workflow: "flat", state: WAIT | PREPARE | ENTER, ... }
PositionDecision { workflow: "in_position", state: HOLD | REDUCE | EXIT, ... }
```

Consequences:

- impossible state/workflow combinations can be rejected structurally;
- transition tests are smaller and clearer;
- Sprint 14 can implement the flat machine without pretending in-position rules exist;
- opening or closing a position is a workflow handoff recorded in the trace, not an ordinary transition inside one overloaded graph;
- clients still render a shared decision card through the discriminated union;
- replay must record both state and workflow.

### 10.2 Flat-position machine

| From | To | Minimum policy meaning |
|---|---|---|
| initial/unknown | `WAIT` | inputs are trustworthy enough to issue a fail-safe state, but no preparation or entry qualification exists |
| `WAIT` | `PREPARE` | recognized setup/forming condition exists; required freshness/risk gates pass; entry conditions incomplete |
| `PREPARE` | `WAIT` | setup expires/rejects, required condition fails, quality degrades, risk blocks, or data becomes unsafe |
| `PREPARE` | `ENTER` | deterministic strategy candidate and every required policy/risk/freshness condition pass |
| `ENTER` | `PREPARE` | entry qualification lapses but preparation remains valid |
| `ENTER` | `WAIT` | setup invalidates, risk/freshness fails, or opportunity disappears |
| any flat state | unavailable | position/trust cannot be established sufficiently even to claim the traced fail-safe state |

`ENTER` is internally stable but presented as **ENTRY CONDITIONS MET**. It never means buy, sell, click approval, or submit order.

### 10.3 In-position machine

The vocabulary is reserved now; transitions are not product-approved for implementation until trade update history and deterministic management rules exist.

| State | Intended future meaning |
|---|---|
| `HOLD` | approved management policy says neither reduction nor exit condition is met |
| `REDUCE` | approved deterministic policy says exposure should be reduced; never an order |
| `EXIT` | approved deterministic policy says exit conditions are met; never an order |

No default transition table is invented in Sprint 12A. In particular, data loss does not automatically establish `HOLD`, `REDUCE`, or `EXIT`. The UI must show a safety escalation/unavailable state until policy D4 is resolved and implemented.

### 10.4 Workflow handoffs

- flat → open position: record prior flat state, trade correlation ID, detected position timestamp, and handoff reason; select in-position machine.
- open → flat: record prior management state, close correlation, timestamp, and handoff reason; initialize flat policy from current inputs rather than inheriting a management state.
- conflicting/duplicate position data: decision unavailable and critical trace reason.

## 11. Decision Trace Contract

Every authoritative decision and material transition requires an immutable trace.

```text
DecisionTrace
  trace_id
  schema_version
  decision
  workflow
  direction
  decided_at
  input_snapshot_at
  freshness
  reason_codes[]
  satisfied_conditions[]
  failed_conditions[]
  unavailable_conditions[]
  risk_gates[]
  setup_refs[]
  strategy_ref
  evidence_refs[]
  definition_versions
  policy_id
  policy_version
  input_snapshot_hash
  previous
  transition_reason
  invalidation_conditions[]
  confidence
```

### 11.1 Condition item

Each condition includes:

- stable `condition_id`;
- result: `satisfied`, `failed`, or `unavailable`;
- observed value and typed comparison where safe;
- source timestamp;
- evidence references;
- definition/policy version;
- machine-readable reason code.

The three result arrays remain separate so unavailable is never collapsed into failed.

### 11.2 Risk gate item

Each gate includes gate ID, pass/fail/unavailable, observed value, configured limit, source, timestamp, enforcement status, and reason code. Current kill-switch output must preserve `enforced: false`.

### 11.3 Previous and transition

`previous` includes trace ID, workflow, state, decided time, and snapshot hash. Initial decisions explicitly use `previous: null`. `transition_reason` is a stable code plus referenced changed conditions, not free-form AI prose.

### 11.4 Confidence

If present:

```text
confidence:
  value
  meaning
  method
  source
  sample_size
  definition_version
```

Existing `StrategyDecision.confidence` is documented in `live/atlas/strategy_engine/models.py` as an optional deterministic scalar, not a learned probability. Existing AI intelligence is historical/rubric-based and must retain its own meaning. Neither may be labeled “probability of winning.”

### 11.5 Hashing and persistence

The hash covers the canonical decision-bearing input snapshot, source identities, and relevant definition versions. Material state transitions should be persisted in Sprint 14. Exact canonicalization, retention, and storage ownership remain design work for Sprint 12B/14.

## 12. Freshness and Fail-Safe Policy

### 12.1 Status vocabulary

Per source:

- `current`;
- `delayed`;
- `stale`;
- `no_data`;
- `disconnected`;
- `invalid`;
- `not_applicable`.

Overall trust:

- `trusted`;
- `degraded`;
- `unavailable`.

The frontend currently defines current/delayed/stale thresholds in `frontend/src/lib/freshness.ts`: current through 1.5 bar durations, stale after `max(3 × bar duration, 5 minutes)`, with invalid or future timestamps treated as stale. This is an existing UI heuristic, not yet an authoritative Decision Engine policy. Sprint 12B must choose one server-owned policy and version it.

### 12.2 Fail-safe rules

1. Any required decision input that is stale, disconnected, invalid, or unavailable prevents transition into `ENTER`.
2. `ContextQuality.DEGRADED` or `UNKNOWN` prevents `ENTER` unless a future approved policy explicitly proves otherwise; initial policy should fail safe.
3. Rule/Setup `InsufficientData` remains unavailable, not false.
4. Unknown position state prevents workflow selection and therefore prevents an authoritative action state.
5. A breached approved risk gate prevents flat-position entry qualification.
6. Mismatched timestamps or fingerprints invalidate composition.
7. AI unavailability has no effect on the deterministic decision.
8. A stale previous decision must be visibly historical and must not be displayed as current.
9. Recovery requires a new fully evaluated trace; do not simply remove a warning from an old decision.
10. In-position data loss invokes an explicit safety escalation. No management state is invented.

### 12.3 Freshness ownership

The backend-composed contract must return:

- policy version;
- generated time and aligned input time;
- each source’s observed time, age, threshold, and status;
- overall status and reason codes.

The frontend may format this data but must not independently change the authoritative trust classification.

## 13. Existing Capability Mapping

| Contract area | Repository evidence | Classification | Contract use |
|---|---|---|---|
| canonical market input | `live/atlas/market_engine/models.py::MarketState` | Existing | raw/reference market fields and timestamps through its `Event` envelope |
| session fields/levels | `MarketState.session_name`, `is_rth`, `rth_open`, PDH/PDL, ONH/ONL | Existing but not exposed in current trader UI | compose into `market` |
| VWAP/ATR/volume/liquidity/trends | `MarketState` fields | Existing but not generally exposed | compose into `market`; preserve `None` |
| deterministic facts | `live/atlas/rule_engine/models.py`, registry/service and `live/atlas/api/v1/rule_engine.py` | Existing live API | `facts`, including `InsufficientData` |
| setup detection | `live/atlas/setup_engine/models.py`, registry/service and `live/atlas/api/v1/setup_engine.py` | Existing live latest/episodes API | `setups` detection, severity, evidence |
| session/regime/context quality | `live/atlas/market_context/models.py`, `service.py` | Existing domain, replay composition only | reuse for `context`; requires live composition |
| setup direction/source | `live/atlas/setup_interpretation/models.py`, `service.py` | Existing domain, not live API | reuse; requires live composition |
| strategy evaluation | `live/atlas/strategy_engine/models.py`, `strategies/displacement_volume_context.py` | Existing replay-domain capability; narrow plugin coverage | reuse for `strategy`; requires live evaluation/composition |
| strategy state | candidate/rejected/no-signal in `StrategyDisposition` | Existing type | input to Decision Engine, not final product decision |
| risk snapshot | `live/atlas/risk.py::RiskSnapshot` and API | Existing live display data | `risk`; enforcement truth required |
| position/trades | `live/atlas/api/v1/trades.py` and frontend typed clients | Existing current/list/detail; current update limitations | `trade` and workflow selection subject to data integrity |
| historical intelligence | `live/atlas/intelligence.py` and AI intelligence endpoint | Existing deterministic historical comparison | contextual evidence; not action authority |
| AI notes/reports | `live/atlas/ai.py`, AI APIs, `frontend/src/lib/aiApi.ts` | Existing | AI archive; no authority |
| browser transport | `frontend/src/lib/proxyClient.ts`, proxy allowlist/route | Existing BFF boundary | future frontend endpoint must use BFF |
| freshness display | `frontend/src/lib/freshness.ts`, `FreshnessBadge` | Existing client heuristic | inform server policy, not remain final authority |
| replay composition | `live/atlas/replay_engine/models.py`, `service.py` | Existing | reference for live equivalence and future replay |

## 14. Missing Capability Matrix

| Capability | State | Required future work |
|---|---|---|
| versioned `TraderNow` API | Missing | Sprint 12B server composition and BFF/client contracts |
| authoritative server freshness policy | Missing | align, version, test, and expose source statuses |
| live Market Context composition | Derivable from existing packages | use existing service against live aligned history |
| live Setup Interpretation | Derivable from existing packages | compose existing service with matching Rule/Setup outputs |
| live Strategy Engine evaluation | Derivable but coverage-limited | reuse engine/plugin; prove live/replay equivalence and label coverage |
| Decision Engine | Missing | deterministic flat-position policy in Sprint 14 |
| Decision Trace persistence | Missing | schema, canonical hashing, event persistence, retention |
| full material-change feed | Missing | compare traces and persist transitions |
| Trades landing workspace | Missing | future frontend consolidation |
| safe in-position rules | Missing | full update history, invalidation monitoring, approved policy |
| reliable position-state conflict handling | Incomplete | define authoritative source and reconciliation |
| AI snapshot explanation/citations | Missing | Sprint 15 structured prompt/evidence contract |
| settings write APIs | Missing and not currently approved | governance, audit, authorization if ever needed |
| order-flow data | Missing | separate vendor/data/research decision; out of scope |

## 15. Live-Equivalence Test Plan

The goal is to prove that live composition reuses existing deterministic behavior and produces the same outputs as replay for identical aligned inputs.

### 15.1 Fixture construction

- Build immutable MarketState windows covering each supported timeframe.
- Include pre-open, opening range, mid-session, closing range, overnight, daylight-saving boundaries, missing upstream session labels, and insufficient ATR history.
- Include every registered setup as detected, not detected, and insufficient data.
- Include strategy candidate, rejected, and no-signal cases.
- Freeze calendar/classifier/interpretation/strategy definition versions.

### 15.2 Equivalence assertions

For the identical ordered input window:

- live and replay `MarketContext` compare field-for-field, including fingerprint;
- Setup Interpretation compares direction, source, fact IDs, reason codes, version, and fingerprint;
- Strategy Decision compares disposition, direction, setup IDs, reasons, context fingerprint, levels, and deterministic confidence;
- missing data yields the same explicit unavailable result;
- input ordering and timestamp alignment are identical;
- repeat evaluation is byte/canonical-serialization stable.

### 15.3 Negative and safety cases

- mismatched symbol, timeframe, or occurred time;
- context fingerprint mismatch;
- missing required fact;
- invalid fact value;
- unknown setup ID;
- duplicated or out-of-order bars;
- forming versus closed bar policy;
- repository returns no history or truncated history;
- delayed/stale inputs;
- DST/session calendar boundary;
- concurrent live requests and cache behavior;
- strategy plugin not applicable or not registered.

### 15.4 API and integration assertions for Sprint 12B

- one versioned response with aligned timestamps;
- explicit per-section availability;
- no LLM call on the read path;
- no duplicated domain calculations;
- BFF-only browser transport;
- schema validation and unknown-field policy;
- deterministic errors and safe HTTP semantics;
- performance budget measured at minimum and maximum required history;
- existing Rule/Setup APIs remain regression-tested.

### 15.5 Approval gate

Sprint 12B cannot claim live capability until equivalence fixtures pass against the existing public services. Any required change to an existing domain definition must be reviewed as a correction/version change, not hidden in the composition layer.

## 16. AI Evidence and Citation Contract

### 16.1 Allowed input

AI receives a frozen, redacted projection of one `TraderNow` snapshot and its Decision Trace:

- snapshot/trace IDs and times;
- authoritative decision and user-facing label;
- reason/condition/risk-gate records;
- evidence objects explicitly approved for narration;
- freshness and availability;
- historical intelligence with its actual provenance;
- requested explanation type.

AI does not receive authority to query arbitrary current state and reconcile it independently.

### 16.2 Required output

```text
AIExplanation
  explanation_id
  snapshot_id
  trace_id
  generated_at
  model_id
  purpose
  summary
  claims[]
  citations[]
  limitations[]
  freshness_at_generation
```

Every material claim maps to one or more evidence reference IDs. Unsupported claims are rejected or omitted. The response visually states that it explains a deterministic decision.

### 16.3 Contextual explanation types

- why the action is `WAIT`, `PREPARE`, or entry-qualified;
- why a setup was rejected or unavailable;
- what changed from the previous trace;
- why trust is degraded;
- how historical outcomes relate, with sample size and definition caveats;
- completed-trade review.

### 16.4 Prohibited behavior

AI must not:

- compute facts from raw bars;
- choose or override a Decision Engine state;
- invent unavailable values or evidence;
- convert deterministic confidence into win probability;
- conceal stale/degraded inputs;
- generate orders, authorize execution, change risk limits, or claim enforcement;
- contradict authoritative trace fields.

### 16.5 Failure behavior

Timeout, provider error, invalid schema, stale snapshot, missing citation, or cost limit produces an unavailable explanation state. It never blocks Dashboard/Market, changes the decision, or substitutes uncited prose.

## 17. Acceptance Criteria

### 17.1 Sprint 12A document acceptance

- all six destinations have non-overlapping primary responsibilities;
- every current frontend page has a target owner;
- eight required trader workflows are specified;
- Dashboard hierarchy and state variants are explicit;
- `TraderNow` fields distinguish existing, derivable, and missing data;
- Decision Engine is deterministic and separate from Strategy Engine and AI;
- two-machine recommendation is recorded;
- Decision Trace contains all Product Owner minimum fields;
- freshness policy fails safe and preserves unavailable states;
- live-equivalence plan covers existing packages;
- AI evidence contract requires traceable claims;
- Sprint 12B boundary contains no implementation authorization.

### 17.2 Future trader-scenario acceptance tests

1. **Pre-session:** given trusted pre-open context and flat position, Dashboard states why entry is unavailable and shows next monitored conditions.
2. **No setup:** given current data and no signal, `WAIT` trace says no signal—not insufficient data.
3. **Setup forming:** given a recognized incomplete setup, `PREPARE` lists exact passes/failures/unavailable conditions.
4. **Entry qualified:** given candidate + all gates passing, internal `ENTER` renders “ENTRY CONDITIONS MET,” direction, disclaimer, and trace.
5. **Stale data:** if a required input crosses stale threshold, no new entry qualification is possible and the transition is traceable.
6. **Degraded context:** disagreement or insufficient history is visible and safely gates entry.
7. **Risk breach:** entry is gated; UI preserves `enforced: false` where applicable.
8. **Open trade:** workflow changes to in-position; before policy implementation, UI does not invent HOLD/REDUCE/EXIT.
9. **Completed trade:** review separates contemporaneous trace evidence from outcome knowledge.
10. **AI failure:** deterministic state and Market evidence remain usable.
11. **Evidence navigation:** Dashboard “Why?” opens matching Market evidence for the same snapshot.
12. **Replay:** identical input/version set reproduces the same decision and hash once persistence exists.

## 18. Product Decision Register

| ID | Decision | Recommended resolution | Status / blocker |
|---|---|---|---|
| D1 | Initial product scope | Single MNQ instrument and current named strategy; make identity explicit | **Product confirmation required** before IA copy and contract cardinality |
| D2 | Recommendation authority | Deterministic advisory only; never execution | Approved principle; legal/product wording still required |
| D3 | `ENTER` semantics/copy | Internal `ENTER`; user-facing “ENTRY CONDITIONS MET” | Semantics approved; **copy confirmation required** |
| D4 | In-position states | Reserve HOLD/REDUCE/EXIT but do not implement until data and rules are approved | **Blocks in-position machine implementation** |
| D5 | Dashboard density | One critical first viewport with evidence drill-down | **Design confirmation required** |
| D6 | AI placement | Hybrid contextual explanations plus top-level archive | Approved principle |
| D7 | Freshness authority | Server-owned, versioned policy informed by existing UI thresholds | **Blocks authoritative TraderNow decisions** |
| D8 | Composition alignment | One server-aligned snapshot; reject mismatched timestamps/fingerprints | Recommended; **backend design approval required** |
| D9 | Context reuse | Reuse existing three packages after equivalence tests | Approved principle |
| D10 | Strategy coverage | Start with existing `displacement_volume_context`; expose coverage honestly | **Product confirmation required** |
| D11 | Risk gate semantics | Define which display fields become policy gates; never imply existing enforcement | **Blocks Decision Engine policy** |
| D12 | Position authority | Select authoritative open-position source and conflict behavior | **Blocks workflow selector** |
| D13 | Decision persistence | Persist material transitions with canonical input hash | Recommended; **storage/retention decision required** |
| D14 | Evidence identifier design | Typed, resolvable, immutable references | **Blocks AI citation and Market deep links** |
| D15 | Market visualization scope | Context/reference-level visualization first; defer full chart workstation | Design confirmation required |
| D16 | Research route collision | Target `/research` as workspace; plan redirect for current baseline and `/research-ops` | Implementation routing decision required |
| D17 | Settings editability | Read-only first; no writes without governance/audit | Recommended; no current blocker |
| D18 | Paid reports | Preserve explicit user action and cost disclosure; no automatic invocation | Product/cost UX decision for later AI work |
| D19 | Order flow | Defer behind validated hypothesis and data-source decision | Not an immediate blocker |
| D20 | Confidence language | Require method/provenance; prohibit win-probability wording without validated model | Approved principle |

### 18.1 Unresolved blockers for Sprint 12B

The minimum blocking decisions are D1, D7, D8, D10, D12, D13, and D14. D3 and D5 block final user-facing design. D4 blocks only in-position policy implementation, not flat-position composition.

## 19. Sprint 12B Planning Boundary

Sprint 12B is a future backend-composition sprint. It is not authorized by this document.

Expected scope:

- review the public services in `market_context`, `setup_interpretation`, and `strategy_engine`;
- prove live/replay equivalence;
- define server-owned alignment and freshness policy;
- compose a versioned read-only `TraderNow` endpoint;
- expose Decision Trace-shaped source data where available, while marking Decision Engine output not implemented until Sprint 14;
- add BFF allowlisting and typed frontend client only when implementation is approved;
- preserve existing APIs and semantics.

Sprint 12B must not:

- clone or rewrite the three existing engines;
- implement the Decision Engine early;
- call an LLM to fill missing deterministic fields;
- add execution behavior;
- imply risk enforcement that does not exist;
- silently change definition versions;
- change backend credentials or deployment configuration as an implementation shortcut.

Its decision gate requires API contract approval, equivalence results, source alignment policy, performance evidence, security/proxy tests, regression tests, and an explicit list of unavailable fields.

## 20. Explicit Non-Goals

- No application-code, route, API, database, infrastructure, Railway, environment, deployment, or credential change.
- No commit or push.
- No second Market Context Engine, Setup Interpretation layer, or Strategy Engine.
- No live backend composition during Sprint 12A.
- No Decision Engine implementation during Sprint 12A or 12B.
- No order submission, approval, modification, cancellation, blocking, or broker integration.
- No claim that current risk calculations enforce trading controls.
- No default HOLD, REDUCE, or EXIT logic.
- No LLM-selected state, direction, setup, risk gate, stop, target, invalidation, or execution action.
- No confidence-as-win-probability claim without a separately validated model.
- No order-flow integration.
- No deletion of existing diagnostics or routes under this planning task.
- No modification of `ARCHITECTURE_REVIEW_2_0.md`; this contract refines it under the Product Owner decision.

## Repository Evidence Index

- Frontend shell/navigation: `frontend/src/app/layout.tsx`, `frontend/src/components/AppNav.tsx`
- Current pages: `frontend/src/app/**/page.tsx`
- Typed browser APIs/BFF: `frontend/src/lib/*Api.ts`, `frontend/src/lib/proxyClient.ts`, `frontend/src/lib/proxyAllowlist.ts`
- Current UI freshness heuristic: `frontend/src/lib/freshness.ts`
- Canonical market state: `live/atlas/market_engine/models.py`
- Rule Engine: `live/atlas/rule_engine/models.py`, `registry.py`, `service.py`, `live/atlas/api/v1/rule_engine.py`
- Setup Engine: `live/atlas/setup_engine/models.py`, `registry.py`, `service.py`, `live/atlas/api/v1/setup_engine.py`
- Market Context: `live/atlas/market_context/models.py`, `service.py`
- Setup Interpretation: `live/atlas/setup_interpretation/models.py`, `service.py`, `definitions.py`
- Replay composition: `live/atlas/replay_engine/models.py`, `service.py`
- Strategy Engine: `live/atlas/strategy_engine/models.py`, `service.py`, `strategies/displacement_volume_context.py`
- Risk: `live/atlas/risk.py`, `live/atlas/api/v1/risk.py`
- Trades: `live/atlas/api/v1/trades.py`
- Historical intelligence and AI: `live/atlas/intelligence.py`, `live/atlas/ai.py`, `live/atlas/services/claude.py`

All “existing” claims refer to repository code. “Existing domain” does not imply a live API or current user-facing capability; those limitations are stated explicitly above.
