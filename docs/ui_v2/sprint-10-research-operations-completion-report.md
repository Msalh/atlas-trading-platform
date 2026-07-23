# Sprint 10 — Research Operations Integration: Completion Report

Status: all seven slices (A, A.1, B, C, D, E, E.1, F, G) certified. This document is the final Sprint 10 certification candidate, produced at the end of Slice G per its own kickoff.

## 1. Final architecture summary

Sprint 10 built a read-only operator UI on top of the Research Engine's existing Ledger and Promotion subsystems (Sprints 8.2/9), following one architecture end to end:

```
Browser → Next.js BFF (src/app/api/proxy/[...path]/route.ts) → Atlas Backend (FastAPI)
```

The BFF is a policy-aware boundary, not a generic reverse proxy: a closed, hand-authored, method-aware allowlist (`proxyAllowlist.ts`) decides which paths and HTTP methods are reachable at all; GET requests get shape-only query-param projection, POST requests get shape-only body-field projection (never business validation — that stays backend-side); there is no orchestration in the proxy layer (composition happens backend-side, e.g. `GET /research/lineage`); no caching, no persistence; lightweight access logging (`proxyAccessLog.ts`) distinct from the permanent, backend-side PromotionRecord audit trail.

Every page in the new `atlas.research_ops` frontend domain talks only to this proxy, never directly to the Atlas backend, and never through the older, insecure `NEXT_PUBLIC_API_KEY` pattern some pre-existing pages still use (a disclosed, pre-existing inconsistency, not extended by this sprint).

**Net new backend API surface added by Sprint 10: one endpoint.** `GET /research/lineage` (Slice A) — a composed, read-only walk from a PromotionRecord or ValidationResult back through the Ledger's other five stores, built because the Sprint 10 architecture review concluded that composition belongs backend-side, not assembled from several BFF calls. Every other endpoint the six pages use (`/status`, `/research/leaderboard`, `/research/promotion`, `/research/promotion/candidates`) already existed from Sprints 8.2/9 before Sprint 10 began; Sprint 10's job for those was BFF-allowlisting plus a typed frontend client, not new backend work.

## 2. Page map

Six pages under `/research-ops`, all reachable from the global nav and from each other via a consistent "Next" affordance, in the workflow order below:

| Page | Route | Slice | Answers |
|---|---|---|---|
| Research Overview | `/research-ops` | B | Is the engine/ledger healthy? Latest snapshot/validation? How many promotions? |
| Leaderboard | `/research-ops/leaderboard` | C | Which hypotheses currently rank highest, and what's their promotion status? |
| Snapshot Explorer | `/research-ops/snapshot` | D | For one ranked entry, what's its complete Hypothesis→Realization→Experiment→Evidence→Validation→Promotion lineage? |
| Promotion Queue | `/research-ops/promotion/queue` | E | What still requires review? |
| Promotion History | `/research-ops/promotion/history` | E | What decisions have already been made? |
| Run Center | `/research-ops/run-center` | F | Is the engine operational, what operations exist, which are available now? |

`/research` (RE-1/RE-2 statistical baseline, a separate, frozen, pre-Phase-N4 backend subsystem) is unrelated to this workflow; Slice G relabeled its nav entry from "Research Overview" (a name collision with the new Overview page) to **"Statistical Baseline"** — no code, route, or backend change to that page itself.

**Workflow order** (Overview → Leaderboard → Snapshot Explorer → Promotion Queue → Promotion History → Run Center): reviewed in Slice G against the kickoff's own instruction to change it only if objectively better. Kept as specified — it reads as "current state → deep understanding of one entry → what needs a decision → what's already been decided → how new data gets produced," a coherent narrative with no rival ordering I could defend as more objectively correct rather than merely different.

**No orphan pages remain.** Before Slice G, all six pages were reachable only by direct URL (each slice's own kickoff explicitly excluded navigation work). Slice G added: (a) all six to the global top nav, (b) a `NextStepLink` on each non-terminal page pointing to the next page in the stated order (Run Center, the last stop, has none).

## 3. Component map

`frontend/src/components/ResearchOps/` (one feature-scoped namespace, distinct from app-wide components and single-page-scoped ones):

| Component | Introduced | Reused by |
|---|---|---|
| `StatCard` | Slice B | Overview, Leaderboard, Snapshot Explorer, Promotion Queue, Promotion History, Run Center — every page |
| `ReadinessCard` | Slice B | Overview, Run Center |
| `LeaderboardTable` | Slice C | Leaderboard |
| `PromotionStatusBadge` | Slice C | Leaderboard, Promotion Queue (with a Slice E.1 `label` override), Promotion History |
| `LineageChain` | Slice D | Snapshot Explorer |
| `PromotionQueueTable` | Slice E | Promotion Queue |
| `PromotionHistoryTable` | Slice E | Promotion History |
| `OperationCard` | Slice F | Run Center |
| `SectionLoading` | **extracted in Slice G** | all six pages (previously six identical local copies) |
| `EmptyPanel` | **extracted in Slice G** | Leaderboard, Snapshot Explorer, Promotion Queue, Promotion History (previously four identical local copies; also absorbed the primary-content-area "Loading…" div each of those four pages separately duplicated) |
| `NextStepLink` | **new in Slice G** | Overview, Leaderboard, Snapshot Explorer, Promotion Queue, Promotion History |

`frontend/src/lib/researchOpsLedgerChecks.ts` (**new in Slice G**): `buildLedgerChecks()`, extracted from byte-identical `LEDGER_CHECK_ORDER`/`LEDGER_CHECK_LABELS` constants and derivation logic duplicated between Overview and Run Center.

**Deliberately not force-reused**: `PromotionStatusBadge` and `LineageChain` on the Run Center page (Slice F) — the first is typed to a promotion decision, which nothing on that page is; the second renders realized-instance provenance chains, not a catalog of operation types. Reviewed, documented, not applied, per each slice's own kickoff instruction to justify reuse rather than force it.

## 4. API usage map

| Endpoint | Backend origin | BFF-allowlisted | Consuming pages |
|---|---|---|---|
| `GET /status` | pre-existing (`/status`) | Slice B | Overview, Run Center |
| `GET /research/leaderboard` | Sprint 8.2 | Slice B | Overview, Leaderboard, Snapshot Explorer, Promotion Queue (timestamp reconciliation), Run Center |
| `GET /research/promotion` | Sprint 9 | Slice B | Overview, Leaderboard, Promotion History |
| `GET /research/promotion/candidates` | Sprint 9 | **Slice E** | Promotion Queue, Run Center |
| `GET /research/lineage` | **Slice A (new)** | Slice A | Snapshot Explorer |
| `POST /research/promotion/decide` | Sprint 9 | **never allowlisted** | none — Slice A originally added it as an early POST proof, removed in Slice A.1 as scope leakage; still fully supported by the BFF's POST mechanics (tested against a fixture path), just not wired to any real route until an actual decision-making UI is reviewed |
| `POST /research/run` | Sprint 8.2 | never allowlisted | none — Run Center is read-only by design; described, never called |

Every GET path above is read via `proxyGet()` with a hand-written runtime type guard (`researchOpsApi.ts`) — a backend shape drift fails loudly as a typed `ApiFetchError`, never an unchecked cast.

## 5. Backend impact

One new file: `live/atlas/api/v1/research_lineage.py` (Slice A, hardened in A.1 for read-count efficiency — one `.all()` per touched store instead of up to 9 full JSONL re-scans per request). No other backend file was modified by Sprint 10 except router registration. Every other backend capability Sprint 10's UI surfaces (`/status`, `/research/leaderboard`, `/research/promotion`, `/research/promotion/candidates`) was written in Sprints 8.2/9 and simply had no consuming UI until now.

**Zero backend changes** in Slices B, C, D (uses Slice A's endpoint), E, E.1, F, G — six of Sprint 10's nine total slices touched no backend file at all.

## 6. Frontend impact

- `frontend/src/lib/researchOpsApi.ts`: one typed client module, additive across every slice (new interfaces/guards/fetch functions per slice, only Slice E.1/C extended existing interfaces with new required fields, each time updating every existing test fixture that constructed one).
- `frontend/src/lib/proxyAllowlist.ts` / `proxyClient.ts`: extended once for method-aware routing + POST support (Slice A/A.1); one new GET entry (Slice E).
- `frontend/src/lib/researchOpsLedgerChecks.ts`: new, Slice G.
- 11 components, 6 pages, all under the dedicated `ResearchOps`/`research-ops` namespaces — nothing outside those namespaces was modified except `layout.tsx` (nav) and the shared BFF/proxy files above.
- `frontend/src/app/layout.tsx`: nav extended (Slice G) — 6 new links added, 1 existing link relabeled, 0 removed.

## 7. Dependency review

**Zero new npm dependencies** introduced across all of Sprint 10. Every page/component uses only what was already in the project: `@tanstack/react-query` (already the app's data-fetching layer since UI v2), `next/link`, Tailwind utility classes matching the existing design tokens (`--muted`, `--ok`, `--warn`, `--danger`, `--border`, `--surface`). No chart library, no state-management library, no UI-kit dependency added.

## 8. Railway impact

**None, for the entire sprint.** No new environment variable, no new Volume, no new startup check, no new migration, no config change. The one new backend endpoint (`/research/lineage`) reads the same Ledger Volume every other Sprint 8.2/9 endpoint already reads; it required no deployment-shape change to expose.

## 9. Total test counts

| Suite | Before Sprint 10 | After Sprint 10 | Delta |
|---|---|---|---|
| Frontend (Vitest) | ~200 (pre-existing UI v2 suite, from context prior to Sprint 10) | **314 passed, 48 files** | +114 across Slices A–G |
| Backend (pytest) | 2079 passed, 1 skipped (unchanged since Sprint 9) | **2079 passed, 1 skipped** | 0 — Sprint 10 added one backend test file (`test_research_lineage_api.py`, 10 tests, Slice A) which is included in that 2079; no regression, no new failures |

Every commit-worthy state in this sprint passed: frontend suite, ESLint, TypeScript, production build, backend suite — run fresh at the end of every slice, not just at the end.

## 10. Technical debt intentionally deferred

Each item below was identified during a slice, evaluated against that slice's own "STOP and explain" bar, and deliberately not built — documented here as the single consolidated list:

1. **Hypothesis entity unavailable from `/research/lineage`** (Slice D). The endpoint returns only `hypothesis_id`, never the full entity, because the real pipeline never persists `Hypothesis` objects to the Ledger's `HypothesisRegistry` at all (a Sprint 9 finding, not new). Extending the endpoint today would return `null` for every real hypothesis. Blocked on the pipeline itself persisting Hypotheses — a pipeline change, not a UI one.
2. **No discovery endpoint for the Run Center's operation catalog** (Slice F). The five-operation catalog is a frontend-declared constant pinned to `research_pipeline.py`'s own `_RUN_MODES`/`_IMPLEMENTED_MODES`. Acceptable for Sprint 10 per Slice F's own certification; a `GET /research/operations` endpoint would remove the hand-maintained duplication if the catalog ever needs to grow independently.
3. **Promotion decision actions** (Approve/Reject/Defer buttons). Explicitly out of scope for all of Sprint 10 — the Queue/History pages are inspection-only by design; `POST /research/promotion/decide` exists backend-side and in the BFF's tested-but-unwired POST mechanics, waiting for its own dedicated review.
4. **Run Center execution** (actually running Replay/Benchmark/Research Run from the UI). Explicitly out of scope — Run Center is a dashboard, never an executor, by every slice's own repeated instruction.
5. **Flat top-nav may not scale** (Slice G). The nav now carries 18 links in one flat, wrapping row. Reused the existing pattern (no new UI mechanics) rather than introduce a dropdown/grouped nav component this codebase has never had; noted as a candidate if more sections are added later.
6. **Live browser verification gap** (Slices D, E, F). A Browser-pane/environment issue (not an application bug — verified via direct console instrumentation showing the query/error chain resolving correctly, and by reproducing the identical symptom on an already-certified, unmodified page after a full dev-server restart) intermittently prevented observing the settled (non-loading) render of query-driven summary cards in the live preview across several slices. Automated tests (real React Testing Library renders, not mocked components) cover every one of those same states and pass. Disclosed transparently in each affected slice's own report rather than worked around with a fabricated screenshot.
7. **`Statistical Baseline` (`/research`) and Dataset Health remain visually ungrouped from Research Operations in the nav** — both frozen/pre-Phase-N4, placed adjacently but not visually separated from the six new links beyond the existing `|` separator convention. A cosmetic grouping improvement, not pursued to avoid introducing new nav mechanics for a single-sprint's worth of pages.

## 11. Recommendations for Sprint 11

1. **Decide the Promotion decision workflow's own scope and review it properly** before building Approve/Reject/Defer actions — the single largest remaining gap between "operator can see everything" (done) and "operator can act" (not started). `record_decision()`/`POST /research/promotion/decide` already exist and are already tested; the work is UI + a fresh architectural review of the action's own safety/audit requirements, not new backend plumbing.
2. **If Replay or Benchmark modes get built backend-side**, the Run Center's `OperationCard` component and `OPERATIONS` catalog are already shaped to accept that with a small data change — no redesign needed, just updating `kind: "not_implemented"` → `"implemented"` and adding real prerequisites/state logic once those modes exist.
3. **Revisit the flat top-nav** if Sprint 11 adds more page groups — 18 links in one row is at the edge of what a flat pattern comfortably carries; a grouped/dropdown treatment would be the natural next step, deferred deliberately this sprint (see debt item 5).
4. **Consider the `GET /research/operations` discovery endpoint** (debt item 2) only if the operation catalog is expected to change frequently; not worth it for occasional, deliberate additions.
5. **The Hypothesis-persistence gap** (debt item 1) is a pipeline-level decision, not a UI one — worth a dedicated small sprint if the full Hypothesis entity (statement/author/dataset) becomes operationally important to show in the Snapshot Explorer.

---

*Certified slices: A, A.1, B, C, D, E, E.1, F, G. This report is the final Sprint 10 certification candidate per Slice G's own kickoff — awaiting review.*
