# Phase 18E Operator Checklist — Evidence Collection Only

This checklist cannot approve enablement. Checked items indicate only that the
corresponding owner attestation is recorded in the evidence package; unresolved
items remain unchecked, and unknown ownership is a blocker.

- [x] Personal Project Owner records Railway Variables as the future store,
      backend-service-only injection, 90-day rotation, incident triggers, and a
      one-hour revocation SLA. Record no secret value; deployment must still
      verify service scope and permissions.
- [ ] Personal Project Owner confirms current model entitlement and rate/usage
      limits for the personal account/project.
- [x] Personal Project Owner records the supplied pricing and USD 0.12 ceiling;
      revalidate no later than 2026-09-05 or on any pricing-policy change.
- [x] Personal Project Owner records dated acceptance of provider default
      retention/data-use behavior, deletion, caching, and incident handling;
      retain metadata no more than 30 days and do not claim ZDR.
- [ ] Before any go/no-go, record the non-secret model-entitlement/limits check:
      pass/fail, timestamp, owner role, model, and sanitized suitability only.
- [x] Personal Project Owner records self-review and risk acceptance for the
      committed security/privacy controls.
- [ ] Release/Platform records target environment, change window, approvers,
      pre-deployment checks, and an explicit go/no-go decision.
- [x] Personal Project Owner assigns sanitized-counter alert thresholds, maximum
      30-day retention, and forbidden-field policy: alert at USD 0.10, hard-stop
      at USD 0.12, and on transport/rejection/count/teardown/authority violations.
- [ ] Runtime owner rehearses disablement/rollback and confirms the public
      unavailable behavior and deterministic trading authority remain unchanged.
- [ ] Confirm the adapter remains default-disabled until every blocking item is
      approved independently.

No checklist completion is implied by the successful one-shot metadata.
