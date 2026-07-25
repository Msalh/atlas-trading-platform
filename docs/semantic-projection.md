# Evidence Browser semantic projection

This document records the frozen Increment 17F-3B behavior. It does not
redefine the Snapshot contracts or subsystem architecture.

## Supported schema

The browser explicitly supports `trader_now_snapshot.v1`. Any other snapshot
schema is rejected as unsupported. The browser does not partially render,
infer, reinterpret, or synthesize fields from an unsupported schema.

## Projection and rendering invariants

The semantic presentation is produced by a typed, allowlisted projection of a
validated `snapshot_private_api.v1` detail response. The requested snapshot ID,
response snapshot ID, supported schema, evidence profile, canonicalization
profile, and approved transport shape must agree before projection succeeds.
Unknown top-level snapshot or evidence fields fail closed.

Raw transport objects are never passed through the component tree or rendered
directly. Focused presentation components receive only the typed projection.
Values remain source values: the browser does not derive trading conclusions,
repair values, interpret Markdown, linkify URLs, or execute HTML. Bidirectional
controls are made visible in structured text, and React text rendering provides
the content-isolation boundary.

The projection enforces these limits before rendering:

| Limit | Value |
| --- | ---: |
| Maximum nesting depth | 12 |
| Maximum items in one array | 500 |
| Maximum string length | 20,000 characters |
| Maximum traversed nodes | 5,000 |
| Maximum formatted JSON output | 524,288 characters |

Exceeding a limit suppresses all semantic presentation and produces a safe
content-limit state. Malformed shapes, cycles, non-finite numbers, identity
disagreement, profile disagreement, and unexpected scalar types also fail
closed. Unsupported schema remains distinct from malformed or integrity-related
failure.

## Authority boundaries

The Evidence Browser preserves four separate visual and model boundaries:

1. **Snapshot header** contains only approved authoritative identity/header
   fields.
2. **Indexed metadata** is derived, non-authoritative information used only for
   lookup and display.
3. **Structured semantic evidence** is a human-readable projection of the
   semantic transport response.
4. **Semantic snapshot JSON** is bounded, formatted plain text created from the
   validated semantic transport response.

The semantic JSON is not canonical bytes, is not the stored canonical payload,
and is not proof of byte-level equality. The browser neither regenerates nor
claims to expose `atlas-jcs.v1` canonical evidence. Indexed metadata remains
non-authoritative even when it agrees with semantic evidence; disagreement is
never silently normalized.
