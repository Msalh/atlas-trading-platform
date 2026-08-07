# Phase 18 Manual AI One-Shot CLI

This internal operator command runs the default-disabled manual advisory path
once and emits one bounded JSON diagnostic object. It does not start FastAPI,
the dashboard, a worker, or any public diagnostics endpoint.

## Preconditions

- Run from `C:\Projects\Trading-phase18-clean\live` on the reviewed commit.
- Use the exact approved development provider configuration.
- Keep `ATLAS_AI_PROVIDER_API_KEY` server-only and non-empty.
- Do not redirect stdout to a persistent log containing anything except the
  bounded report.
- Run preflight first. Do not run the live command when preflight exits nonzero.

## Boolean-only preflight

```powershell
Set-Location 'C:\Projects\Trading-phase18-clean\live'
python -m atlas.manual_ai_smoke --preflight
$LASTEXITCODE
```

Preflight constructs no runtime and performs zero provider attempts. Its JSON
values are booleans only. It checks fixed configuration shape, credential
presence, canonical-input presence, and the fixed no-retry policy without
printing configuration or credential values.

## One-shot command

After a successful preflight, the complete invocation is:

```powershell
python -m atlas.manual_ai_smoke
```

The module loads only
`specs/trader_now_snapshot/v1/golden/complete-current-candidate.canonical.json`,
calls `build_manual_ai_one_shot_runner()`, invokes that runner once, snapshots
diagnostics before returning, and exits. It accepts no prompt, evidence,
endpoint, model, credential, payload, retry, or input-path argument.

The transport counter is incremented immediately before the sole
`client.send`. A count other than one makes the report `failed_closed`.
Provider/orchestrator retries are absent, HTTP uses
`HTTPTransport(retries=0)`, redirects are disabled, and there is no fallback
provider.

## Output and exit codes

Normal mode writes exactly one `manual_ai_one_shot_diagnostic.v1` JSON object
using the fixed `OneShotDiagnosticReport.to_dict()` schema. It never includes
prompts, payloads, provider response content, evidence, credentials, headers,
request IDs, exception text, stack traces, or arbitrary validator messages.

| Exit code | Meaning |
|---:|---|
| `0` | Completed analysis; all 11 output fields passed authoritative validation. Also used by successful boolean-only preflight. |
| `2` | Public result is `analysis_unavailable` with a complete, coherent sanitized diagnosis. |
| `3` | Boolean-only preflight blocked execution. No runtime or provider attempt was made. |
| `4` | Internal fail-closed outcome, including construction, canonical-input, attempt-count, snapshot, or serialization failure. Do not retry automatically. |

Always inspect `$LASTEXITCODE`. Regardless of the result, do not repeat the
live command without separate authorization.
