# Phase 17F-5B certification evidence

This directory contains sanitized certification metadata for the Evidence
Browser deployment gate. Evidence records are documentation artifacts and are
not application release inputs.

Each certification manifest must identify:

- the exact immutable revision under test;
- the branch and relevant commit range;
- UTC execution timestamps;
- commands executed and concise pass/fail/skip summaries;
- sanitized artifact filenames;
- deployment identifiers only after deployment is separately authorized;
- all unresolved Phase 17E exclusions.

Never store:

- secrets, tokens, passwords, cookies, or authorization headers;
- DSNs, private hosts, or environment-variable values;
- canonical evidence, semantic evidence payloads, or database contents;
- customer data, raw logs, stack traces, or infrastructure exceptions.

Only sanitized summaries required to reproduce or audit the certification are
retained in Git. Voluminous local command output and build artifacts remain
untracked and must be deleted after their summarized result is reviewed.

Phase 17E engineering certification is PASS. Phase 17E operational
certification remains BLOCKED BY ENVIRONMENT. No record in this directory may
claim certified backup, restore, disaster recovery, database rollback, final
public TCP proxy disposition, full platform production readiness, or
real-money-trading authorization.
