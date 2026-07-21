# Sprint 31 Task 8 — Exact Sprint 26 Phase 3/4 Commands

Only executable once `DATABASE_URL` (Phase 3) and API access to whatever database it points at
(Phase 4) are available. Nothing here has been run — every command below is unexecuted, ready to
copy-paste. All reuse existing tooling; nothing new was built to produce this list.

Expected canonical range after `--assume-bar-open-time` shifts the source CSV's bar-open
timestamps (`2026-07-13T13:00:00Z` → `2026-07-17T20:55:00Z`) forward by one bar (5 minutes) to
bar-close: **`2026-07-13T13:05:00Z` → `2026-07-17T21:00:00Z`**, 1200 rows.

## Phase 3 — Historical Import Execution

**Dry run** (no `DATABASE_URL` required — safe to run any time, included here for completeness):
```
python scripts/import_historical_market_state_csv.py \
  "data/CME_MINI_MNQ1!, 5_504af.csv" \
  --symbol "MNQ1!" --timeframe 5m --assume-bar-open-time
```
Expect: `Total data rows: 1200`, `Skipped: 0`, `Malformed: 0`, `Valid: 1200` (matches Sprint 31
Task 4's certification — zero hard failures on this dataset).

**Apply** (writes to the database `DATABASE_URL` points at):
```
DATABASE_URL=postgres://... python scripts/import_historical_market_state_csv.py \
  "data/CME_MINI_MNQ1!, 5_504af.csv" \
  --symbol "MNQ1!" --timeframe 5m --assume-bar-open-time --apply
```
Expect: `Valid: 1200`, `Inserted: 1200`, `Duplicate: 0` on a first run against an empty table.

## Phase 4 — Post-Import Audit

All six reuse `GET /api/v1/market-state/export` (limit ceiling 50000 — the only read endpoint
that can cover all 1200 rows in one call; `/history` and `/integrity` cap at 1000 and cannot).

**1. Row-count audit**:
```
curl -s 'https://<real-domain>/api/v1/market-state/export?symbol=MNQ1!&timeframe=5m&start=2026-07-13T00:00:00Z&end=2026-07-18T00:00:00Z&limit=50000' \
  -H "Authorization: Bearer $API_KEY" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])"
```
Expect: `1200`, matching Phase 3's own reported `Inserted` count exactly.

**2. Timestamp-range audit**: from the same response, confirm the first and last `data[]` entries'
`timestamp` fields are `2026-07-13T13:05:00+00:00` and `2026-07-17T21:00:00+00:00` — proving the
bar-close shift landed correctly in storage, not just in the importer's own pre-write output.

**3. Duplicate audit** (re-run Phase 3's apply command a second time, unchanged):
```
DATABASE_URL=postgres://... python scripts/import_historical_market_state_csv.py \
  "data/CME_MINI_MNQ1!, 5_504af.csv" \
  --symbol "MNQ1!" --timeframe 5m --assume-bar-open-time --apply
```
Expect: `Valid: 1200`, `Inserted: 0`, `Duplicate: 1200` — proves the existing
`UNIQUE(symbol, timeframe, event_id)` idempotency guarantee holds against the real database, not
just `InMemoryMarketStateRepository` (already proven in-memory, Sprint 31 Task 6's
`TestDuplicateRerunBehavior`).

**4. Gap audit**: from audit #1's response, check `gap_count` and `gaps`. Expect `gap_count: 4`,
matching Sprint 31 Task 4's certification exactly (four ~65-minute gaps at `20:55→22:00 UTC`
daily — the same CME daily-maintenance pattern already found and explained in that report).

**5. Exact sample read-back audit** (reusing Task 3's own `start==end` single-event lookup — pick
any 3-5 real timestamps from the CSV, e.g. the same three Task 3 already used):
```
curl -s 'https://<real-domain>/api/v1/market-state/export?symbol=MNQ1!&timeframe=5m&start=2026-07-13T13:05:00Z&end=2026-07-13T13:05:00Z' \
  -H "Authorization: Bearer $API_KEY"
```
Expect: `count: 1`, and the returned OHLC/vwap/etc. match the CSV's `2026-07-13T13:00:00` row
(bar-open label) exactly — the same field-by-field check
`scripts/verify_historical_live_equivalence.py` already performs, reusable here directly against
this newly-imported data instead of live production.

**6. VWAP precision audit**: from audit #5's response, confirm `vwap` carries genuine
multi-decimal precision (not tick-rounded, not truncated) and matches the source CSV's
`export_vwap` column for that row exactly — the same check Sprint 31 Task 2 already proved
against live-ingested data, now proved against historically-imported data too.

## Notes

- Every command above is read-only except the two Phase 3 invocations, both already idempotent
  and safe to re-run (audit #3 relies on exactly this).
- No new script or endpoint was built to produce this list — all six audits reuse
  `GET /market-state/export`, the existing importer, and the existing equivalence-check pattern
  from Sprint 31 Task 3.
