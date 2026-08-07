# Phase 18E Dependency Security Review

Status: technical assessment only; no risk acceptance or remediation approval is
recorded by this document.

## Scope and evidence

- Audit date: 2026-08-07 UTC.
- Command: `npm.cmd audit --json`, run from the integrated `frontend` directory.
- Audit result: six high-severity vulnerability entries; no dependency changes
  or remediation were performed.
- The production parent and Phase 18 parent have identical `frontend/package.json`
  and `frontend/package-lock.json` objects. The integrated tree retains those
  exact files. The findings are therefore pre-existing in both parents, not
  introduced by Phase 18 and not created by merge resolution.
- The installed tree was created from the committed lockfile solely for offline
  verification. It is not staged and is not a deployment artifact.

## Findings and lineage

| Package | Installed version and path | Parent lineage | Exposure | Fixed version or action | Impact |
|---|---|---|---|---|---|
| `next` | `16.2.10`, direct dependency | Present at the same version in production and Phase 18 parents | Production runtime/framework | Upgrade to at least `16.2.11` for the reported range; audit reports `16.3.0` as an available fix | High findings include middleware/proxy bypass, SSRF, and denial-of-service conditions; deployment remains blocked |
| `sharp` | `0.34.5`, transitive under `next` | Pre-existing and unchanged in both parents | Production runtime image-processing dependency | Upgrade through a compatible Next/sharp update to `0.35.0` or later | High libvips findings; deployment remains blocked |
| `postcss` | `8.4.31` under `next`; `8.5.20` in the development tree | Pre-existing dependency tree in both parents | Primarily build-time; the vulnerable nested Next copy is not application source | Upgrade the Next dependency tree; do not alter it in this integration | High path-disclosure/path-traversal advisories require security review before deployment |
| `brace-expansion` | `5.0.7` under `@typescript-eslint/typescript-estree` and `1.1.15` under ESLint minimatch | Pre-existing development dependency tree | Development tooling only | Upgrade ESLint/typescript-eslint dependency tree when authorized | High denial-of-service advisories; not part of the production bundle |
| `js-yaml` | `4.3.0` under ESLint | Pre-existing development dependency tree | Development tooling only | Upgrade ESLint dependency tree when authorized | High parser denial-of-service advisory; not part of the production bundle |
| `undici` | `7.28.0` under jsdom | Pre-existing development/test dependency tree | Development/test tooling only | Upgrade jsdom dependency tree when authorized | High parser/cache-related advisories; not part of the production bundle |

The audit reports the vulnerable ranges as follows: `next >=16.0.0 <16.2.11`,
`sharp <0.35.0`, `postcss <=8.5.22`, `js-yaml >=4.0.0 <4.3.1`,
`undici >=7.0.0 <7.29.0`, and the reported vulnerable `brace-expansion`
ranges `<=1.1.17` and `>=4.0.0 <5.0.9`.

## Commit and deployment impact

The findings do not represent a Phase 18 source regression and do not require a
dependency change to preserve this integration. The staged merge can be reviewed
independently of dependency remediation.

The direct `next` and transitive `sharp` findings affect the production runtime
and continue to block deployment. The build-time and development-only findings
remain security follow-ups and do not affect the Phase 18 merge behavior.

## Remediation and verification plan

Dependency remediation requires a separately authorized lockfile update, followed
by `npm.cmd ci`, `npm.cmd audit --json`, frontend tests, lint, typecheck, and
production build. No `npm audit fix`, `npm update`, or version change is authorized
by this record. A compatible Next upgrade may be breaking and requires an explicit
review of the proxy, route-handler, and build contracts.

The Personal Project Owner is the recorded decision owner. This document does not
constitute owner acceptance of the findings, a waiver, deployment approval, or a
security-risk acceptance.

## Isolated production-remediation verification

- Verification date: 2026-08-07 UTC.
- Base commit: `822e9c51027af2eb7638178ba7562a4825a0821f`.
- Isolated branch/worktree: `codex/frontend-security-remediation`.
- Only the direct `next` and `eslint-config-next` versions were changed, using:
  `npm.cmd install --save-exact next@16.3.0 eslint-config-next@16.3.0`.
- Resulting versions: `next@16.3.0`, `eslint-config-next@16.3.0`, and transitive
  `sharp@0.35.3`.
- All resolved PostCSS installations were `8.5.23`; no vulnerable Next-owned
  PostCSS path remained.
- `npm.cmd audit --omit=dev --json` returned zero vulnerabilities. The full audit
  returned three high development-tooling findings: `brace-expansion`, `js-yaml`,
  and `undici`; those findings were not changed by this remediation.
- Targeted frontend tests passed: 131 tests in 5 files. The full frontend suite
  passed: 464 tests in 59 files. Lint, TypeScript, and production build passed.
- Backend read-only/manual-advisory regression tests passed: 50 tests.
- No source, route, provider, trading, Railway, or deployment configuration was
  changed. No provider call, push, deployment, or risk acceptance occurred.
- The dependency update was independently reviewed and committed locally as
  `4a60e3360251df34dfce6dc32e1f0972fad9ad09`. It has not been pushed, merged, or
  deployed; those actions remain subject to separate review and authorization.

## Clean Node 22 reproducibility verification

- Verification date: 2026-08-07 UTC.
- Runtime: official Node.js `v22.19.0` Windows x64 portable ZIP from `nodejs.org`,
  verified against the matching `SHASUMS256.txt`; npm was `10.9.3`.
- In a disposable directory, `npm.cmd ci` exited 0 without an install-script
  approval warning or manual script execution. The optional Windows x64 binding
  `@unrs/resolver-binding-win32-x64-msvc@1.12.2` and `unrs-resolver@1.12.2`
  loaded successfully.
- `npm.cmd run lint`, Node 22 TypeScript checking, `npm.cmd test` (59 files,
  464 tests), and `npm.cmd run build` all exited 0.
- `npm.cmd audit --omit=dev --json` exited 0 with zero vulnerabilities. The
  approved production tree remained `next@16.3.0`, `eslint-config-next@16.3.0`,
  `sharp@0.35.3`, and `postcss@8.5.23` at every resolved path.
- Both manifests remained byte-identical after `npm ci`. Disposable
  `node_modules`, `.next`, TypeScript build metadata, and the portable runtime
  were deleted after verification.
- This result establishes clean Node 22 reproducibility for the lockfile. It does
  not constitute risk acceptance, deployment approval, or a push; the remediation
  remains subject to independent review and a separate release decision.
