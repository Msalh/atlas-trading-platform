# Frontend CSP Tradeoff: `script-src 'unsafe-inline'`

## What happened

The Sprint 9 frontend CSP (`frontend/next.config.ts`) originally shipped with
`script-src 'self'` - no `unsafe-inline`. The first real staging deploy to Vercel/
Railway hung on the initial "Loading" state indefinitely, with the browser console
showing:

```
Executing inline script violates Content Security Policy directive: script-src 'self'
```

This is exactly the risk flagged (but not yet verified) in
`docs/sprint9/security-notes.md`'s Remaining Risks #4 and
`docs/sprint10/deployment-runbook.md`: CSP behavior that only surfaces against a real
production Next.js runtime, not `next dev` (this CSP is deliberately only applied to
production builds) and not a local `next build && next start` smoke test either, since
the failure depends on exactly which inline script tags Next.js's App Router emits at
runtime.

## Root cause

Next.js's App Router bootstraps client-side hydration via an inline `<script>` tag
embedded directly in the server-rendered HTML (this is how React "wakes up" the
static markup into an interactive app). A bare `script-src 'self'` blocks that inline
script outright - the browser refuses to execute it, hydration never happens, and the
page stays exactly as the server rendered it (the loading skeleton), forever, with no
further errors beyond the one CSP violation line.

## The fix

`script-src 'self' 'unsafe-inline'` - see `frontend/next.config.ts`. This is a
deliberate, scoped tradeoff, not a general loosening:

- It applies **only to the frontend's own CSP header** (`frontend/next.config.ts`).
  The **backend's CSP stays `default-src 'none'`, unchanged** - `atlas/main.py`'s
  `_security_headers` middleware serves no HTML at all (JSON and SSE only, since the
  legacy dashboard was removed in Sprint 9), so there is no inline-script surface for
  `unsafe-inline` to weaken there. Backend authentication (`API_KEY` on every
  non-webhook endpoint), the webhook secret scheme, and kill-switch enforcement are
  completely untouched by this fix - none of those live in `next.config.ts`.
- It only affects `script-src`, not the other CSP directives -
  `frame-ancestors 'none'`, `base-uri 'self'`, and the `default-src 'self'` fallback
  all stay exactly as strict as before.
- `style-src 'self' 'unsafe-inline'` was already accepted in Sprint 9 for the same
  class of reason (Next.js may inject inline styles); `script-src` needed the same
  allowance, just not discovered until a real deploy exercised it.

## What this actually costs

`unsafe-inline` on `script-src` means the CSP no longer blocks an attacker-injected
`<script>` tag from executing, if one ever got into the page (e.g. via a future XSS
bug in some part of the frontend that renders unsanitized user/API content). This is a
real, non-zero reduction in defense-in-depth - it is not free, and it should not be
treated as "fine forever." It is, however, a narrower risk than it sounds for this
specific app today: every backend response is JSON (React's default rendering already
escapes it; nothing in this codebase uses `dangerouslySetInnerHTML` - confirmed during
the Sprint 8 audit), so there is no known injection point this CSP relaxation is
currently covering for. The tradeoff is "removes a safety net for a bug that doesn't
exist yet," not "there's a known hole here."

## Future improvement path: nonces or hashes

The correct, non-`unsafe-inline` fix is a per-request CSP nonce:

1. Generate a random nonce per request (e.g. in Next.js middleware, `crypto.randomUUID()`
   or similar).
2. Pass it to Next.js so it attaches the nonce to every script tag it renders (Next.js
   has built-in support for this via the `nonce` prop pattern in recent versions -
   check the version in `frontend/package.json` against Next.js's current CSP/nonce
   documentation, since this API has changed across major versions).
3. Set `script-src 'self' 'nonce-<value>'` in the CSP header instead of
   `'unsafe-inline'`, generating the header value dynamically per-request (this
   requires moving the CSP header out of the static `next.config.ts` `headers()`
   config, which only supports static values, and into middleware instead).

This is real, non-trivial work (dynamic per-request headers, wiring the nonce through
every layout/page that renders a script tag) - explicitly deferred per this fix's own
scope ("if implementing nonces is too large, `unsafe-inline` is acceptable for
staging"). Revisit before this moves from staging to handling a real funded account,
alongside the other Sprint 8 audit items still open (frontend CSP was explicitly
called out there as unverified against a real deployment - it now is, and this is the
result).
