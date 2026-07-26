# Phase 17F-5B local preflight

- Certification phase: `17F-5B.0` and `17F-5B.1`
- Subject branch: `codex/phase-17f-semantic-mvp`
- Frozen subject revision: `9b0d78af5c8c1477ab898bb2a66e0c021a34270d`
- Relevant implementation range: `e04ced4..9b0d78a`
- Completed at: `2026-07-26T08:06:26Z`
- Deployment performed: no
- Railway or infrastructure mutation: no

## Local results

| Gate | Command or method | Result |
| --- | --- | --- |
| TypeScript | `npm.cmd run typecheck` | PASS |
| ESLint | `npm.cmd run lint` | PASS |
| Unit, contract, BFF, navigation, race, integrity, semantic, security, and accessibility suite | `npm.cmd test` | PASS — 14 files, 100 tests |
| Production build | `npm.cmd run build` | PASS |
| Phase 17E frozen-tool regressions | configured Python 3.12 `pytest` on the probe and capture-service files | PASS — 32 tests |
| Source hygiene | bounded pattern scan excluding fixtures/tests | PASS |
| Browser bundle server-secret scan | bounded scan of `.next/static` | PASS |
| Tracked synthetic-secret scan | bounded tracked-file pattern scan | PASS |
| Patch hygiene | `git diff --check` | PASS |

The system `npm.ps1` shim was blocked by local PowerShell execution policy
before npm started. This was not a gate execution or test failure; the approved
commands were executed successfully through `npm.cmd`.

The system `python` command selected legacy Python 2.7 and could not import
pytest. This was not a test execution or failure; the same focused tests passed
using the configured Python 3.12 runtime.

## Contract consistency

The frozen reader contract references Snapshot API revision `d14b930`. The
intervening API change through `b2ba490` only introduced sanitized reader
connection assembly and enforced the existing PostgreSQL read-only session
setting through that assembly. It did not change transport schemas, routes,
headers, status codes, authentication, error envelopes, response limits,
timeouts, or semantic content.

Decision: **contract-equivalent for local certification; live equivalence
remains required during separately authorized deployment certification.**

## Deployment evidence placeholders

Deployment identifiers, private connectivity results, live contract results,
logs/metrics review, accessibility smoke results, and feature-rollback results
are intentionally absent. They may be appended only after explicit deployment,
connection, feature-enablement, live-request, inspection, and rollback
authorization.

## Phase 17E exclusions

Phase 17E engineering certification is PASS. Phase 17E operational
certification remains BLOCKED BY ENVIRONMENT. This preflight does not certify
backup, restore, disaster recovery, database rollback, final public TCP proxy
disposition, full platform production readiness, or real-money trading.
