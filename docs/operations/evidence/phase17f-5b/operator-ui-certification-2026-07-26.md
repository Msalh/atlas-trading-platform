# Phase 17F-5B operator UI certification

- Certification phase: `17F-5B`
- Subject branch: `codex/phase-17f-semantic-mvp`
- Frozen subject revision: `9b0d78af5c8c1477ab898bb2a66e0c021a34270d`
- Execution date: `2026-07-26`
- Execution timestamps: not supplied
- Certification method: operator-attested UI exercise in a normal authenticated
  browser
- Automated browser certification: no
- Final verdict: **PHASE 17F-5B NOT FULLY CERTIFIED — OPERATOR-TESTED UI WITH
  RESIDUAL VERIFICATION GAP**

## Deployment record

| Stage | Deployment | Result |
| --- | --- | --- |
| Disabled baseline | `d0b255d2-4ca9-45e4-bc57-04f619a08f69` | PASS |
| Bounded enablement | `9c19eac9-96f5-4174-bc71-f8136a69aa5e` | PASS |
| Mandatory rollback | `0d4e863a-5315-41ef-9723-96de3e5a149c` | PASS |

The certification window changed only the Evidence Browser feature state.
Rollback restored `EVIDENCE_BROWSER_ENABLED=false`.

## Operator-attested results

| Check | Result |
| --- | --- |
| Evidence page and snapshot list rendering | PASS |
| Snapshot selection and detail rendering | PASS |
| Dedicated integrity gate | PASS |
| Structured semantic presentation | PASS |
| Manual refresh behavior | PASS |
| Sanitized not-found presentation | PASS |
| Visible keyboard focus | PASS |
| Full accessibility-tree evidence | NOT COMPLETED |
| Browser console hygiene evidence | NOT COMPLETED |
| Browser Network hygiene evidence | NOT COMPLETED |

The incomplete checks are a residual certification gap. They are not recorded
as application defects, and this record does not upgrade the result to full
17F-5B certification.

## Correlation with server-side certification

The operator-attested UI results are consistent with the separately completed
server-side Phase 17F-5B checks:

- private Snapshot API connectivity and reader authentication passed;
- list, detail, metadata, and integrity responses conformed to
  `snapshot_private_api.v1`;
- snapshot identity and evidence-digest agreement passed;
- the integrity response was verified;
- correlation propagation and sanitized invalid-request handling passed;
- browser bundle and server-only configuration hygiene passed.

The operator exercise does not replace those checks, and the server-side checks
do not substitute for the incomplete accessibility-tree, Console, or Network
evidence.

## Rollback evidence

After deployment `0d4e863a-5315-41ef-9723-96de3e5a149c`:

- `EVIDENCE_BROWSER_ENABLED=false`;
- the Operations Dashboard reported healthy;
- `/evidence` returned `404`;
- `/api/evidence/snapshots?limit=25` returned
  `evidence_browser_disabled`.

No claim is made here about continuing traffic beyond the operator-observed
rollback checks.

## Browser-certification limitation

Rendered UI and accessibility results are operator-attested. Codex in-app
Browser navigation was blocked by `ERR_BLOCKED_BY_CLIENT`, so no automated
browser certification is claimed.

## Phase 17E exclusions

Phase 17E engineering certification remains PASS. Phase 17E operational
certification remains BLOCKED BY ENVIRONMENT because the Railway Hobby
environment cannot provide the required backup and restore certification.

This record does not certify:

- Snapshot backup schedules or a valid recovery point;
- isolated restore or disaster recovery;
- database rollback dependent on a recovery point;
- final public TCP proxy disposition;
- full platform production readiness;
- real-money trading.
