# Sprint 12B Backend Composition Plan

**Status:** Technical design for review; implementation is not authorized by this document
**Approved scope:** MNQ, 5-minute operation, `displacement_volume_context` strategy
**Repository reviewed:** `main` at `f983b21`
**Contract dependency:** `docs/product/SPRINT_12A_PRODUCT_CONTRACT.md`

## 1. Executive Summary

Sprint 12B should add one read-only, server-composed `TraderNow` endpoint that reuses the existing deterministic pipeline and returns one aligned, versioned snapshot. It should not implement the Decision Engine or emit `WAIT`, `PREPARE`, `ENTER`, `HOLD`, `REDUCE`, or `EXIT`.

Recommended endpoint:

```http
GET /api/v1/trader-now?symbol=MNQU6&timeframe=5m&strategy_id=displacement_volume_context
```

Initial implementation accepts only the approved MNQ contract symbol, `5m`, and `displacement_volume_context`; unsupported identity values return a validation error rather than triggering premature generalization. “MNQ” is the product instrument family. The actual contract symbol remains explicit—currently `MNQU6` in the frontend shell and repository fixtures—and must not be silently substituted.

Composition ownership belongs in a new thin application/orchestration module above the existing packages. It should fetch one bounded chronological MarketState window, call the existing Rule Engine, Setup Engine, Market Context, Setup Interpretation, and Strategy Engine public functions, then attach existing RiskSnapshot and current-trade state. It must not copy their logic into the API router.

The implementation recommendation is **GO with prerequisites**. The architecture is feasible with existing pure services, but coding should begin only after the open engineering decisions in Section 28 are closed—especially the exact supported symbol, server freshness clock/calendar policy, position-conflict query, hash canonicalization profile, evidence URI syntax, and cache ownership.

## 2. Approved Product Decisions

| Decision | Approved outcome | Technical consequence |
|---|---|---|
| D1 initial scope | MNQ only | Explicit supported symbol; no generic instrument registry in 12B |
| Initial strategy | `displacement_volume_context` only | Instantiate only the existing plugin from `live/atlas/strategy_engine/strategies/displacement_volume_context.py`; expose its `1.0.0` version |
| D3 entry semantics | internal `ENTER`, UI “ENTRY CONDITIONS MET” | Not emitted in 12B because Decision Engine is not implemented |
| D5 density | one critical first viewport | Response must be compactly consumable but retain evidence links |
| D7 freshness | server-owned and versioned | Return authoritative freshness/trust classifications; frontend formats only |
| D8 alignment | one server-aligned snapshot | Never join independent “latest” API responses |
| D10 strategy coverage | one existing strategy | Response states coverage; other detected setups remain visible but not strategy-qualified |
| D12 position authority | backend Trades/current-position state | Use the same repository source as `GET /trades/current`; conflicts/unknown block workflow selection |
| D13 persistence | material Decision Engine transitions only | 12B persists no poll responses and no transitions because there is no Decision Engine |
| D14 evidence | typed, immutable, resolvable | Return structured evidence references; exact syntax finalized before implementation |
| In-position scope | states reserved, not implemented | Open position yields `workflow=in_position`, `decision=not_implemented`; never defaults to HOLD |

## 3. Current Backend Capability Inventory

### 3.1 Existing deterministic pipeline

| Capability | Existing type/service | Live status | Important constraint |
|---|---|---|---|
| canonical bar | `live/atlas/market_engine/models.py::MarketState` | persisted/live API | repository history is newest-first; computation requires chronological order |
| facts | `RuleEngineOutput`; `build_rule_engine_output_window` | live API | registry maximum history is 20 bars |
| setups | `SetupEngineOutput`; `build_setup_engine_output_window` | live API | registry maximum history is 2 Rule outputs; combined Rule/Setup minimum is 21 MarketStates |
| context | `MarketContext`; `build_market_context` | replay composition only | `REGIME_CLASSIFIER_V1` requires 288 bars for a non-insufficient volatility regime |
| interpretation | `SetupInterpretation`; `interpret_setups` | replay composition only | dense output; requires aligned Rule and Setup outputs |
| replay alignment | `ReplayFrame`; `build_replay_output_window` | existing pure composition | already composes the first five layers and asserts per-position timestamps |
| strategy | `StrategyDecision`; `evaluate_strategies` | replay-domain only | service checks timestamp, plugin identity/version, and context fingerprint |
| risk | `RiskSnapshot`; `compute_risk_snapshot` and `/risk` | live | display-only; `KillSwitchStatus.enforced` is currently false |
| position | `TradeRepository.get_open_trade`; `/trades/current` | live | returns most recent open trade; repository contract assumes one open position |

### 3.2 Existing versions and identities

- MarketState carries `schema_version`.
- Rule and Setup outputs carry schema versions; every fact/setup outcome carries its definition version.
- Market Context definitions are `CME_RTH_V1` and `REGIME_CLASSIFIER_V1`; its fingerprint hashes definition identities and parameters.
- Setup Interpretation uses `SETUP_INTERPRETATION_V1` and a definition fingerprint.
- Strategy identity is `displacement_volume_context`, version `1.0.0`.
- Current live envelopes expose schema/code/source metadata, but there is no shared authoritative TraderNow freshness policy.

### 3.3 Important repository facts

- `PostgresMarketStateRepository.get_history` orders by `occurred_at DESC`.
- Existing live Rule and Setup handlers reverse history before evaluation.
- `build_replay_output_window` accepts an ascending contiguous window and already composes Rule, Setup, Context, and Interpretation.
- `MarketContext` returns quality `UNKNOWN` for invalid/insufficient windows and `DEGRADED` for verified session disagreement.
- Strategy Engine raises on identity, timestamp, or context-fingerprint mismatches; it never silently repairs them.
- Trade history records only the latest price update, not a complete price-update event history.

## 4. Proposed TraderNow API Contract

### 4.1 Response envelope

```json
{
  "schema_version": "trader_now.v1",
  "snapshot_id": "tn_...",
  "generated_at": "2026-07-24T12:00:01.250Z",
  "input_snapshot_at": "2026-07-24T12:00:00Z",
  "identity": {},
  "trust": {},
  "market": {},
  "facts": {},
  "context": {},
  "setups": {},
  "strategy": {},
  "risk": {},
  "trade": {},
  "decision": {
    "availability": "not_implemented",
    "state": null,
    "trace": null
  },
  "decision_trace_inputs": {},
  "evidence": [],
  "availability": {},
  "warnings": []
}
```

Every top-level section is present. Missing sections use an availability discriminator and `data: null`, not ambiguous omission.

### 4.2 Field-level source and operational matrix

Abbreviations: **P** persisted source, **C** computed per cache miss, **R** repository read.

| Top-level field | Source package/type | Source timestamp | Definition/version source | Required window | Availability | Freshness owner | Mismatch behavior | Storage | Expected cost |
|---|---|---|---|---:|---|---|---|---|---|
| `schema_version` | new transport contract | generation time | `TRADER_NOW_SCHEMA_V1` constant | none | always | n/a | fail startup/test on invalid constant | code | O(1) |
| `snapshot_id` | composition layer | input snapshot + canonical hash | snapshot-ID profile version | all decision-bearing inputs | unavailable only if composition cannot establish identity | composition | fail response if hash cannot be produced | computed; not persisted in 12B | O(serialized input size) |
| `generated_at` | server UTC clock | request completion | clock policy | none | always unless request fails | composition | invalid/non-UTC clock is server error | not persisted | O(1) |
| `input_snapshot_at` | latest aligned closed `MarketState.envelope.occurred_at` | market bar close | alignment policy version | 1 aligned current position after warm-up | no market data → unavailable snapshot | composition | any derived timestamp mismatch makes affected composition unavailable/error | P source/C projection | O(1) |
| `identity` | query + `MarketState` + plugin | bar timestamp | Symbol/Timeframe primitives; strategy ID/version | 1 | required | composition | reject request or fail snapshot on mismatch | C | O(1) |
| `trust` | new freshness classifier + context quality | generated and source timestamps | freshness-policy version + existing Context definitions | current bar/source status | explicit unavailable/degraded | new server classifier | no silent merge; list affected sections | C; short cache only | O(number of sources) |
| `market` | `MarketState` | envelope occurred/received times | MarketState schema version | latest bar | no data/invalid source explicit | server freshness policy | identity/time mismatch fails market-dependent sections | P source/C projection | O(1) after fetch |
| `facts` | `RuleEngineOutput` | `occurred_at` | output schema + per-fact definitions | 20 bars | individual `InsufficientData`; section error on alignment failure | market freshness + composition | timestamp/identity mismatch unavailable/error | C/cache | O(20 × fact registry) within larger pass |
| `context` | `MarketContext` | `occurred_at` | classifier/calendar versions + fingerprint | 288 bars | quality may be trusted/degraded/unknown | market freshness plus context quality | timestamp/identity/fingerprint mismatch unavailable/error | C/cache | O(288) classification scan |
| `setups` | `SetupEngineOutput` + tuple of `SetupInterpretation` | common `occurred_at` | output/per-setup versions + interpretation version/fingerprint | 21 bars for setups; composed inside 288 | per-setup insufficient/unavailable | market freshness; domain computability retained | Rule/Setup timestamp mismatch unavailable/error | C/cache | O(21 × registries) within full window implementation |
| `strategy` | `StrategyDecision` from existing plugin | `occurred_at` | plugin ID/version + context fingerprint | latest aligned `ReplayFrame`; upstream needs 288 | candidate/rejected/no-signal or unavailable | inherits required upstream trust; does not itself declare freshness | service exception or coverage mismatch makes strategy unavailable and trust degraded | C/cache | O(1) plugin evaluation |
| `risk` | `RiskSnapshot` through existing trade repository inputs | no canonical snapshot timestamp in current model | account settings/config at request time; no current explicit risk schema version | trade list used by current risk computation | unavailable if trade repository/config fails | risk-source timestamp design required | do not attach as aligned decision input without observed-at metadata | R/C; trades P | O(number of recent/all trades used by current computation) |
| `trade` | `TradeRepository.get_open_trade` | trade `received_at`/`updated_at` fields | trade storage schema; no explicit domain version | current open query | flat/open/unknown/conflict | repository observation time + trade timestamps | conflict/unknown prevents workflow selection | P source/C projection | indexed query, expected O(log n)/one row |
| `decision` | future Decision Engine | future decision timestamp | future policy version | future | fixed `not_implemented` in 12B | future policy | must never contain a state in 12B | none | O(1) placeholder |
| `decision_trace_inputs` | composition of source provenance | all listed source times | all upstream versions/fingerprints + trace-input schema | same as snapshot | available even while decision not implemented; individual gaps explicit | composition | preserve mismatches as typed failures | C; not persisted in 12B | O(number of evidence/conditions) |
| `evidence` | typed references emitted during projection | referenced source time | evidence schema version + referenced definition | same as source | omit only when source unavailable; never dangling | inherits source | response validation rejects unresolved local refs | C | O(number of emitted refs) |
| `availability` | composition layer | generated time/source time | availability vocabulary version | none | always on successful response | composition | contradictory state is schema failure | C | O(sections) |
| `warnings` | composition layer from typed conditions | source-specific | warning catalog version | none | empty list allowed | composition | never substitute for availability | C | O(conditions) |

### 4.3 Contract rules

- `decision.availability` is always `not_implemented` in Sprint 12B.
- `decision.state`, direction, policy version, and trace are `null`.
- Strategy `candidate` is not mapped to `ENTER`.
- All registered setup outcomes may be visible, but `strategy.coverage.setup_ids` contains only `displacement_with_volume_confirmation`.
- Risk must state `enforcement_mode: display_only` while repository behavior remains unchanged.
- Open position selects `workflow: in_position` only; its decision remains unavailable.

## 5. Proposed Endpoint and Versioning

### 5.1 Endpoint

```http
GET /api/v1/trader-now
  ?symbol=MNQU6
  &timeframe=5m
  &strategy_id=displacement_volume_context
```

All three query parameters should be optional only if their server defaults are the same explicit approved constants returned in `identity`. Supplying any other value returns `422 unsupported_identity`. Silent fallback is forbidden.

### 5.2 Versioning

Use three independent version axes:

1. URI major version: `/api/v1` for breaking HTTP-resource semantics.
2. response schema: `trader_now.v1` for serialized shape.
3. policy/definition versions: freshness, alignment, evidence, hashing, and every upstream domain version/fingerprint.

Additive optional fields may stay in `trader_now.v1`. Removing/renaming fields, changing discriminator meaning, or changing hash inputs requires a schema/profile version. Domain definition changes use their own existing versions and fingerprints.

### 5.3 HTTP semantics

- `200`: structurally valid snapshot, including partial availability.
- `401`: existing API-key authentication failure.
- `422`: unsupported or invalid identity/query.
- `503`: no authoritative position read, market repository failure, or failure so broad that a truthful snapshot cannot be formed.
- `500`: internal contract/alignment invariant violation; return a safe public error and log typed diagnostics.

No request body. No side effect. No AI call.

## 6. Server-Side Composition Flow

Recommended ownership:

```text
API router
  → TraderNow application service
      → MarketStateRepository.get_history(limit=288)
      → reverse to chronological
      → validate identity/order/closed-bar policy
      → existing build_replay_output_window(window)
      → existing evaluate_strategies(latest_frame, [DisplacementVolumeContext()])
      → existing trade repository / risk computation
      → alignment + freshness + availability projection
      → evidence references + canonical snapshot hash
      → response serializer
```

The API router owns query parsing, dependency injection, authentication inherited from router registration, and HTTP mapping only. A proposed `atlas/trader_now` application package owns orchestration, transport-independent models, alignment, freshness, evidence, and hashing. Existing domain packages remain unchanged unless a factual defect is separately approved.

### 6.1 Why reuse `build_replay_output_window`

It already:

- calls the public Rule and Setup window functions;
- bounds Market Context per position;
- calls Setup Interpretation for every position;
- asserts timestamp alignment;
- is pure and deterministic.

For a latest-only endpoint, computing all 288 frames may be more work than necessary. The safe first implementation may reuse it for correctness, benchmark it, then introduce a **thin latest-frame composer that calls the same public functions** if the performance budget requires it. Such an optimization must have equivalence tests against `build_replay_output_window`; it must not reimplement domain logic.

## 7. Input Alignment Policy

Proposed policy ID: `TRADER_NOW_ALIGNMENT_MNQ_5M_V1`.

1. Fetch one MarketState window from one repository call.
2. Reverse newest-first repository output into strict ascending order.
3. Use only `BarStatus.CLOSED` for the authoritative latest snapshot. A forming bar may be exposed separately later but cannot anchor 12B.
4. Require every bar to match the requested symbol and `5m`.
5. Use the latest closed bar’s `occurred_at` as `input_snapshot_at`.
6. Derived Rule, Setup, Context, Interpretation, and Strategy timestamps must equal it for the projected latest frame.
7. Context fingerprints must match between Market Context and Strategy Decision.
8. Plugin ID/version must match the approved identity.
9. Rule/Setup definition versions and interpretation fingerprint are recorded, not normalized.
10. Market sequence gaps remain domain-visible. Context may become `UNKNOWN`; Rule window integrity errors must not be silently caught as successful facts.
11. Risk and trade do not naturally share bar timestamps. Record `observed_at` at repository read completion and their own domain timestamps; do not claim bar alignment.
12. If a section mismatch is isolated, mark that section and all dependants unavailable. If identity, anchor timestamp, or position authority is indeterminate, fail the snapshot safely.

Dependency invalidation:

```text
market unavailable → facts, context, setups, interpretation, strategy unavailable
facts unavailable → setups, interpretation, strategy unavailable
setups unavailable → interpretation, strategy unavailable
context unavailable → strategy unavailable
trade conflict/unknown → workflow unavailable
risk unavailable → risk unavailable; no 12B decision exists to fabricate
```

## 8. Freshness and Trust Policy

### 8.1 Separate dimensions

The server must classify these independently:

- **bar lateness:** whether the expected latest closed 5-minute bar has arrived;
- **API generation delay:** time spent composing the response;
- **source disconnection:** explicit operational/source signal, not inferred solely from age;
- **missing history:** current bar exists but required warm-up depth is absent;
- **invalid future timestamp:** occurred/received/generated time exceeds clock-skew allowance;
- **mismatched snapshot:** identities, timestamps, versions, or fingerprints cannot align;
- **context quality:** existing `TRUSTED`, `DEGRADED`, or `UNKNOWN`, not renamed as freshness.

### 8.2 Recommended initial MNQ 5-minute thresholds

These are **recommendations requiring approval**, not copied from `frontend/src/lib/freshness.ts`.

Assumptions: authoritative bars are confirmed 5-minute closes, server has an exchange-calendar-aware expected-close function, and clocks are UTC synchronized.

| Dimension | Current/acceptable | Degraded/delayed | Unavailable/stale | Rationale |
|---|---:|---:|---:|---|
| bar arrival after expected close | ≤ 90 seconds | >90 to ≤390 seconds | >390 seconds | 90s ingestion grace; 390s means one full 5m bar plus grace has been missed |
| API composition duration | ≤2 seconds | >2 to ≤5 seconds | >5 seconds/time-out | current work is local DB + pure CPU; slow output should not appear “now” |
| future timestamp skew | ≤5 seconds | none | >5 seconds | small clock tolerance; future market data is invalid |
| source disconnection | connected | explicit reconnecting/degraded state | disconnected or health unknown beyond one check cycle | orthogonal to bar age |
| Market Context history | 288 contiguous bars | n/a | less than 288 yields context `UNKNOWN`/insufficient, not endpoint failure | matches `REGIME_CLASSIFIER_V1` |
| Rule/Setup history | ≥21 contiguous bars | partial domain `InsufficientData` | no current bar → unavailable | existing registry requirements |

Bar lateness is calculated against the latest **expected completed close**, not simply `now - latest_bar_at`. During the interval between expected closes, the prior confirmed bar is current. Outside approved market operation/session calendars, return `not_applicable` rather than stale. Holiday/maintenance behavior must be explicit before implementation.

### 8.3 Overall trust aggregation

Proposed `TRADER_NOW_FRESHNESS_MNQ_5M_V1`:

- `unavailable`: no current bar, disconnection, future timestamp, identity/alignment mismatch, or generation timeout;
- `degraded`: delayed bar, slow generation, missing warm-up history, or Context quality `DEGRADED/UNKNOWN`;
- `trusted`: required sources current, aligned, and Context quality trusted.

Trust is not a trading decision. It only reports whether the composed information is dependable.

## 9. Position Authority and Conflict Handling

The initial authority is the backend trade repository used by `GET /api/v1/trades/current`.

Proposed position discriminator:

```text
position_state: flat | open | unknown | conflict
workflow: flat | in_position | null
```

- zero authoritative open trades → `flat`;
- exactly one valid open trade → `open` and `in_position`;
- repository timeout/error or structurally invalid open trade → `unknown`, workflow null;
- more than one open trade, inconsistent correlation IDs, or contradictory lifecycle data → `conflict`, workflow null.

The current `get_open_trade` protocol returns at most one most-recent row and cannot detect multiple-open conflict by itself. Sprint 12B must decide whether to add a repository diagnostic/count query or rely on a database invariant after verifying one exists. It must not call `get_open_trade` and then claim conflicts are impossible without evidence.

An open position never produces `HOLD`. It produces:

```json
{
  "position_state": "open",
  "workflow": "in_position",
  "decision": {"availability": "not_implemented", "state": null}
}
```

## 10. Live Market Context Reuse

Reuse:

- `CME_RTH_V1`;
- `REGIME_CLASSIFIER_V1`;
- `build_market_context`;
- preferably `build_replay_output_window` for the first correct composition.

For 5-minute operation, fetch at least 288 contiguous bars. Pass each latest-position context call the same bounded chronological suffix used by replay. Preserve:

- session phase/progress and upstream drift status;
- volatility regime, percentile rank, and bars used;
- context quality;
- classifier/calendar versions;
- context fingerprint.

Do not implement session or regime logic in `TraderNow`. Context `UNKNOWN` is a successful domain result with degraded trust, not a fake normal regime.

## 11. Live Setup Interpretation Reuse

Reuse `interpret_setups` against the latest aligned Rule and Setup outputs. Preserve one interpretation per Setup outcome, in registry order:

- setup ID;
- detected;
- direction;
- source;
- source fact IDs;
- reason codes;
- interpretation version/fingerprint.

Typed alignment, unknown-setup, missing-fact, and invalid-value exceptions represent internal contract faults. The composition layer may translate them to a typed section failure, but must log and expose a safe correlation identifier; it must never fall back to ad hoc direction inference.

## 12. Live Strategy Engine Reuse

Instantiate only `DisplacementVolumeContext` and call:

```python
evaluate_strategies(latest_frame, (DisplacementVolumeContext(),))
```

Preserve the returned `StrategyDecision` unchanged:

- candidate/rejected/no-signal disposition;
- long/short/flat direction;
- setup IDs and reason codes;
- context fingerprint;
- optional invalidation/stop/target/confidence;
- strategy ID/version.

Publish explicit coverage:

```json
{
  "strategy_id": "displacement_volume_context",
  "strategy_version": "1.0.0",
  "coverage": {
    "qualified_setup_ids": ["displacement_with_volume_confirmation"],
    "all_setup_engine_outputs_strategy_qualified": false
  }
}
```

Candidate does not equal `ENTER`. Strategy output is an input for Sprint 14.

## 13. Availability and Partial-Failure Semantics

Each section uses:

```text
availability:
  status: available | insufficient_data | unavailable | not_applicable | not_implemented
  reason_codes[]
  observed_at
  source_at
data
```

Rules:

- domain `InsufficientData` remains item-level insufficient data;
- missing warm-up may leave market available and context insufficient;
- isolated trade repository failure leaves deterministic market sections available but workflow unavailable;
- market repository failure normally returns `503`, because the snapshot lacks its anchor;
- internal alignment/fingerprint failure invalidates the affected dependency chain and should normally return `500` during initial rollout so defects are visible;
- AI is absent from this endpoint;
- warnings supplement but never replace availability.

Partial `200` responses are allowed only when their trustworthy portions remain useful and no field claims false alignment.

## 14. Evidence Reference Design

### 14.1 Recommended model

Use a typed object, not an opaque unvalidated string:

```text
EvidenceRef
  ref_version: evidence_ref.v1
  kind
  snapshot_id
  source_at
  identity
  locator
  definition
  content_hash
```

`kind` is a closed enum:

- `market_field`;
- `rule_fact`;
- `context_classification`;
- `setup_outcome`;
- `setup_evidence`;
- `strategy_reason`;
- `risk_gate`;
- `trade_state`;
- `decision_trace_condition` (reserved).

`locator` is a kind-discriminated structure, for example:

- market: `{field: "vwap"}`;
- fact: `{fact_id: "trend_5m"}`;
- context: `{classification: "volatility.regime"}`;
- setup: `{setup_id: "...", outcome_index: 0}`;
- setup evidence: `{setup_id: "...", fact_id: "...", evidence_index: 0}`;
- strategy: `{strategy_id: "...", reason_index: 0}`;
- risk: `{gate_id: "daily_loss_limit"}`;
- trade: `{correlation_id: "...", field: "status"}`;
- future trace: `{trace_id: "...", condition_id: "..."}`.

### 14.2 Resolution

Within one response, references resolve through a response-local `ref_id` derived from the typed canonical object. Dashboard-to-Market deep links use `snapshot_id` plus `ref_id`; the Market server/client resolves the reference against the same cached or reconstructable snapshot. Do not put raw JSON Pointer paths in URLs as the authoritative identity—they are fragile across schema evolution.

Exact external syntax—such as `atlas-evidence:v1:<kind>:<digest>`—is an open engineering decision. The structured object is authoritative; any compact URI is a serialization.

## 15. Snapshot Identity and Canonical Hashing

### 15.1 Recommendation

- canonical format: RFC 8785 JSON Canonicalization Scheme (JCS), UTF-8;
- digest: SHA-256;
- profile: `TRADER_NOW_HASH_V1`;
- output: lowercase base64url or hex, selected once and tested with golden vectors;
- snapshot ID: prefixed digest, e.g. `tn_v1_<digest>`.

### 15.2 Included fields

- identity: exact symbol, timeframe, strategy ID/version;
- anchor MarketState event identity, occurred/received times, schema version, and decision-bearing fields;
- Rule/Setup outputs and their definition versions;
- Context output, versions, and fingerprint;
- Setup Interpretations and fingerprint;
- Strategy Decision;
- risk/trade values and their observed/source timestamps if included in snapshot provenance;
- freshness/alignment policy versions;
- explicit availability and missing-data discriminators.

### 15.3 Excluded volatile fields

- `generated_at`;
- request ID, trace/log correlation ID;
- API duration;
- cache hit/miss;
- presentation labels and localized prose;
- warnings derived wholly from included typed states;
- evidence `ref_id` if it is itself derived from the hash;
- AI content.

### 15.4 Assumptions and reproducibility

SHA-256 collision resistance is sufficient for snapshot identity and accidental/corruption detection; this is not a digital signature or proof against a malicious server/database writer. If tamper evidence across trust boundaries is later required, add HMAC or signed audit records without redefining the snapshot hash.

Canonicalization must define decimals, timestamps, enum strings, nulls, tuple/list order, dictionary key order, and non-finite floats. Golden fixtures must reproduce the same digest across processes and replay/live paths.

## 16. Decision Trace Pre-Decision Shape

12B may expose trace-shaped **inputs**, not a Decision Trace:

```text
DecisionTraceInputs
  schema_version: decision_trace_inputs.v1
  snapshot_id
  input_snapshot_at
  workflow_availability
  freshness
  facts[]
  context_ref
  setup_refs[]
  strategy_ref
  risk_inputs[]
  trade_state_ref
  definition_versions
  evidence_refs[]
  input_snapshot_hash
```

It must not contain:

- authoritative state;
- satisfied/failed Decision Engine conditions;
- policy ID/version;
- previous decision;
- transition reason;
- invalidation policy;
- confidence attributed to a decision.

Those fields do not exist until Sprint 14 defines and evaluates a policy.

## 17. Material Change Detection

Sprint 12B should design but not persist Decision Engine transitions.

For efficient polling and future Sprint 14 support:

- identical canonical snapshot hash → no source change;
- changed source snapshot hash → new TraderNow snapshot, but not automatically a material decision transition;
- future material transition → workflow/state/direction or approved decision reason/gate set changes;
- freshness-only recovery/degradation may be material if it changes authoritative decision availability/state under Sprint 14 policy;
- prose, generation time, cache metadata, or field ordering are never material.

12B may support `ETag` from the snapshot hash and `If-None-Match`/`304` after security and proxy behavior are tested. It must not introduce a transition table early.

## 18. Persistence Boundary

| Data | 12B treatment | Retention/audit recommendation |
|---|---|---|
| MarketState | existing persisted source | retain under current policy; authoritative replay input |
| trades/AI notes | existing persisted source | unchanged |
| Rule/Setup/Context/Interpretation/Strategy outputs | compute on cache miss | cache by latest bar + definition fingerprints; reconstructable from source |
| TraderNow serialized response | bounded in-memory cache | retain until next few bar snapshots for deep links; exact TTL is open |
| snapshot hash/evidence refs | computed | persist only when a future material decision transition references them |
| risk/trade read projection | computed from persisted trades/config | no poll-response persistence |
| Decision Trace inputs | computed | not persisted in 12B |
| Decision Engine transition | nonexistent in 12B | Sprint 14 persists material changes only |
| operational metrics | existing observability path | aggregate durations/errors, not full sensitive payloads |

Future replay/audit persistence should store the material Decision Trace plus canonical snapshot hash and enough immutable source identities to reconstruct or verify it. Do not persist every frontend poll.

## 19. BFF and Frontend Client Impact

Future implementation impact:

- add exact `GET trader-now` proxy allowlist entry;
- allow only `symbol`, `timeframe`, and `strategy_id` query keys;
- add a typed `traderNowApi` client with runtime validation;
- use `/api/proxy/trader-now`; browser never contacts backend origin;
- React Query key includes all explicit identity fields;
- frontend renders server `trust` and availability; `frontend/src/lib/freshness.ts` must not override it;
- no direct reuse of independent Rule/Setup/Risk queries to construct an authoritative Dashboard snapshot;
- existing pages and clients remain operational during migration.

No dynamic wildcard route is needed.

## 20. Security and Authorization

- register the new backend router with `Depends(require_api_key)` in the same centralized pattern as protected routers in `live/atlas/main.py`;
- backend key remains server-side in the BFF;
- exact BFF path/method/query allowlisting;
- GET only; no body; no state change;
- strict enum/bounded-length validation for query values;
- no raw exceptions, database values, credentials, or provider configuration in errors;
- avoid logging full risk/trade payloads or hashes of secrets;
- rate-limit consistently with existing middleware and monitor expensive cache misses;
- response security headers remain inherited;
- evidence references must be authorization-scoped and must not allow arbitrary object/path traversal;
- snapshot IDs are identifiers, not authorization tokens;
- use constant-time credential checking through existing security code; no new auth mechanism.

## 21. Performance and Caching

### 21.1 Cost profile

One database query returns up to 288 MarketStates. Pure composition then evaluates a bounded window. Full `build_replay_output_window(288)` is deterministic but may repeat rolling work across all positions; benchmark before promising latency. Risk computation may scan trade rows depending on its existing repository call pattern.

### 21.2 Recommended cache

Cache key:

```text
(symbol, timeframe, latest_event_id/occurred_at,
 rule_registry_fingerprint,
 setup_registry_fingerprint,
 context_fingerprint,
 interpretation_fingerprint,
 strategy_id, strategy_version,
 trader_now_schema_version,
 alignment_policy_version,
 freshness_policy_version)
```

Separate:

- **deterministic frame cache** keyed by source bar and definitions;
- **short response cache** including trade/risk observations, because those may change between bars.

Suggested targets requiring measurement:

- p95 cached response ≤250 ms;
- p95 uncached composition ≤2 s;
- hard server deadline 5 s;
- one in-flight computation per deterministic cache key;
- bounded memory with expiry after a small number of bars.

Do not cache a source disconnection or repository error as a healthy snapshot. Freshness is evaluated at response time even when deterministic outputs are cached.

## 22. Live-vs-Replay Equivalence Test Plan

For identical chronological MarketState fixtures and identical definitions:

1. Run `build_replay_output_window`.
2. Run the proposed live composer.
3. Compare latest Rule output, Setup output, Market Context, Setup Interpretations, and Strategy Decision field-for-field.
4. Compare timestamps, identities, definition versions, and fingerprints.
5. Compare canonical serialized source projection and hash.

Fixtures:

- all session phases and DST boundaries;
- exactly 287/288/289 context bars;
- Rule windows at 19/20 bars;
- Setup combined windows at 20/21 bars;
- each setup detected/not detected/insufficient;
- strategy candidate/rejected/no-signal;
- context trusted/degraded/unknown;
- gaps, duplicates, out-of-order bars, forming latest bar;
- missing upstream session fields;
- invalid future timestamps;
- symbol/timeframe/fingerprint mismatch.

No live composer is accepted if it produces a value replay would not produce from the same inputs.

## 23. Unit, Integration, Contract, and Regression Tests

### Unit

- alignment and dependency invalidation;
- freshness boundaries, expected-close calendar, off-session behavior, clock skew;
- position flat/open/unknown/conflict;
- availability aggregation;
- evidence-reference constructors/resolvers;
- JCS canonicalization and golden SHA-256 vectors;
- exclusion of volatile fields;
- material-change classifier design helpers, if introduced;
- response validation and Decision Engine placeholder invariant.

### Domain reuse/equivalence

- live/replay equivalence for all fixtures in Section 22;
- exact strategy identity/version and coverage;
- typed upstream exception mapping without fallback.

### Repository/integration

- one 288-row newest-first read, correctly reversed;
- no data/partial history/full history;
- current trade and risk success/failure;
- multiple-open detection mechanism;
- transaction/snapshot consistency if chosen;
- cache coalescing and invalidation.

### API/contract

- exact GET route and query validation;
- 200 partial availability, 401, 422, 503, and safe 500 cases;
- no request body/side effects/AI calls;
- schema snapshots and runtime serialization;
- ETag behavior if implemented;
- rate-limit and security headers.

### BFF/frontend

- exact allowlist/method/query tests;
- server credential forwarding only;
- typed response validation;
- loading/partial/error states;
- zero direct backend browser requests;
- frontend does not recompute trust;
- all existing exact proxy-route regression tests.

### Full regression

- backend suite;
- frontend suite, TypeScript, ESLint, production build;
- existing Rule, Setup, Risk, Trades, AI, Research endpoints;
- production smoke tests only after separately authorized deployment.

## 24. Migration and Backward Compatibility

- add the endpoint; do not replace existing Rule, Setup, Risk, or Trades APIs;
- no database migration is required for the core 12B read path unless conflict detection reveals a missing invariant/query need;
- keep current frontend pages operational;
- introduce TraderNow behind its own client/query key;
- compare TraderNow sections with existing endpoints in staging/test;
- do not redirect routes or implement the Dashboard in 12B;
- schema is additive within `trader_now.v1`;
- any later Decision Engine fields move from `not_implemented` only under Sprint 14 approval and contract tests.

## 25. Implementation Sequence

1. Resolve Section 28 blocking decisions and approve thresholds.
2. Add transport-independent TraderNow types, availability vocabulary, and identity constants.
3. Add canonical serialization/hash and evidence-reference primitives with golden tests.
4. Add expected-close/freshness classifier with calendar tests.
5. Add latest-frame composition using existing services; prove replay equivalence.
6. Add position authority/conflict adapter and existing risk composition.
7. Add TraderNow orchestration, dependency invalidation, and trust aggregation.
8. Add bounded/coalesced cache and performance tests.
9. Add authenticated backend GET endpoint and contract tests.
10. Add exact BFF allowlist and typed frontend client; no Dashboard.
11. Run full regression/security/performance suite.
12. Stop at Sprint 12B implementation decision gate before Sprint 13.

Each step should remain reviewable and must not introduce Decision Engine state mapping.

## 26. Acceptance Criteria

- endpoint returns one aligned MNQU6/5m/strategy snapshot;
- all deterministic derived fields come from existing public services;
- 288-bar context and 20/21-bar Rule/Setup requirements are handled honestly;
- live output equals replay output for identical fixtures;
- candidate never becomes `ENTER`;
- decision is always `not_implemented`;
- open position never defaults to `HOLD`;
- position conflict/unknown prevents workflow selection;
- server owns versioned trust/freshness;
- all mismatch cases fail explicitly;
- context quality remains distinct from freshness;
- typed evidence references resolve within the same snapshot;
- hash is reproducible and excludes volatile response metadata;
- no polling response or pseudo-transition is persisted;
- authentication/BFF boundary matches existing security architecture;
- performance targets are met or the implementation returns to design review;
- existing endpoints and clients pass regression tests;
- no AI call or execution side effect exists on the request path.

## 27. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| full 288-frame replay composition is slow per poll | latency/load | benchmark, cache, then optimize with equivalence-proven latest composer |
| exchange-close schedule is wrong around holidays/DST | false stale/current status | use versioned exchange calendar and boundary fixtures |
| repository latest history races ingestion | incoherent snapshot | one ordered query; optional repeat/latest identity check or transaction policy |
| risk/trade lack common bar timestamp | false alignment claim | separate `observed_at`; never claim bar-coherent risk |
| multiple open rows are hidden by `get_open_trade` | wrong workflow | explicit conflict query/invariant |
| partial response masks internal defect | false trust | typed dependency invalidation; 500 invariant faults initially |
| strategy coverage appears broader than reality | unsafe product interpretation | explicit one-setup coverage metadata |
| canonical float/timestamp differences break hashes | non-reproducible audit | JCS profile, normalized domain serialization, golden vectors |
| evidence refs become schema-path coupling | broken deep links | typed locator and digest, resolver tests |
| client retains old freshness heuristic | conflicting truth | server classification authoritative; frontend tests prohibit override |
| cache serves stale position/risk | misleading Dashboard | split deterministic and response caches; short TTL/re-read |
| sensitive trade/risk data leaks into logs | security/privacy | structured metadata-only logging and tests |
| 12B accidentally implements policy | scope/safety breach | invariant: decision always `not_implemented`; tests reject states |

## 28. Open Engineering Decisions

### Blocking before implementation

1. **Exact symbol:** confirm `MNQU6` remains the supported contract symbol for the approved MNQ product scope, and define the rollover procedure/versioning.
2. **Expected-close calendar:** choose implementation source for holidays, maintenance windows, DST, and early closes.
3. **Freshness thresholds:** approve or adjust 90s/390s bar lateness, 2s/5s generation thresholds, and 5s future-skew tolerance.
4. **Position conflict detection:** repository query versus database uniqueness invariant; define invalid row criteria.
5. **Risk observation:** decide how to timestamp/version RiskSnapshot configuration and whether one transaction is required with position read.
6. **Composer shape:** reuse full replay composer initially versus implement an equivalence-tested latest-only composer.
7. **Hash profile:** exact timestamp/decimal normalization and digest encoding.
8. **Evidence syntax:** exact compact ref/URL syntax and snapshot-resolution retention.
9. **Cache implementation:** process-local versus shared; TTL, capacity, and deployment topology.
10. **Partial-failure HTTP policy:** which internal alignment failures return partial 200 versus 500 during rollout.

### Non-blocking/future

- ETag/304 support;
- long-term snapshot reconstruction after cache expiry;
- adding more instruments, timeframes, or strategies;
- Decision Trace storage schema;
- Dashboard/Market deep-link URL shape.

## 29. Explicit Non-Goals

- No Decision Engine policy or state.
- No `WAIT`, `PREPARE`, `ENTER`, `HOLD`, `REDUCE`, or `EXIT` output.
- No mapping from strategy candidate to entry qualification.
- No LLM call, narrative generation, or citation generation.
- No order, broker, relay, webhook, or execution change.
- No duplicate Market Context, Setup Interpretation, Strategy, Rule, or Setup logic.
- No in-position management policy.
- No full trade-update history work.
- No multi-instrument, multi-timeframe, or multi-strategy framework.
- No Dashboard or Market UI implementation.
- No route consolidation.
- No persistence of polling responses.
- No Railway, infrastructure, credential, or deployment change under this planning task.
- No code, commit, push, or deployment under this planning task.

## 30. Final GO / NO-GO Recommendation

**Recommendation: GO WITH PREREQUISITES for Sprint 12B implementation.**

The repository already contains the deterministic domain services needed for composition, including a pure aligned replay path and strict Strategy Engine identity/fingerprint checks. A read-only TraderNow resource is therefore technically justified and avoids duplicate engines.

Implementation is not yet an unconditional GO. Before code begins, engineering/product must close the ten blocking decisions in Section 28 and approve the freshness thresholds. The design should return to review if:

- the approved MNQ symbol/rollover identity cannot be made explicit;
- a reliable expected-close calendar cannot be selected;
- position conflicts cannot be detected;
- live/replay equivalence fails;
- uncached composition cannot meet the approved latency budget without duplicating domain logic;
- canonical hashes cannot be reproduced;
- any implementation proposal maps strategy output to a Decision Engine state.

Once those prerequisites are resolved, implementation should follow Section 25 and stop at its own decision gate before Sprint 13.

## Repository Evidence Index

- `live/atlas/market_engine/models.py`
- `live/atlas/market_engine/ports.py`
- `live/atlas/market_engine/repositories/postgres.py`
- `live/atlas/rule_engine/models.py`
- `live/atlas/rule_engine/registry.py`
- `live/atlas/rule_engine/service.py`
- `live/atlas/setup_engine/models.py`
- `live/atlas/setup_engine/registry.py`
- `live/atlas/setup_engine/service.py`
- `live/atlas/api/v1/setup_engine.py`
- `live/atlas/market_context/models.py`
- `live/atlas/market_context/definitions.py`
- `live/atlas/market_context/service.py`
- `live/atlas/setup_interpretation/models.py`
- `live/atlas/setup_interpretation/definitions.py`
- `live/atlas/setup_interpretation/service.py`
- `live/atlas/replay_engine/models.py`
- `live/atlas/replay_engine/service.py`
- `live/atlas/strategy_engine/models.py`
- `live/atlas/strategy_engine/service.py`
- `live/atlas/strategy_engine/strategies/displacement_volume_context.py`
- `live/atlas/risk.py`
- `live/atlas/api/v1/risk.py`
- `live/atlas/api/v1/trades.py`
- `live/atlas/repositories/base.py`
- `live/atlas/main.py`
- `live/atlas/api/security.py`
- `frontend/src/lib/freshness.ts`
- `frontend/src/lib/proxyAllowlist.ts`
- `frontend/src/lib/proxyClient.ts`

Claims labeled existing refer to repository code, not necessarily a currently deployed or user-facing capability.
