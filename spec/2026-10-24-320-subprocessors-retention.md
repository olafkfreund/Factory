---
status: approved
issue: 320
intent: intent/2026-10-24-320-subprocessors-retention.md
---

# Spec: sub-processors, data residency, Postgres retention

## Design

Two new subsections in `docs/compliance/policies/data-governance.md`, placed after "Retention":
1. Sub-processors: one table of every provider the fleet can egress to, from AIFactory `providers/factory.py` registries and the `factory-secrets` key names in factory-gitops. Columns: provider, what is sent, key name only, residency. Residency is stated as recorded: hosted providers follow their own terms and the fleet neither enforces nor records a region; local Ollama stays on its host; the cluster is where the operator runs it (the DPIA already says routing is the operator's).
2. Postgres retention schedule: per table group, the retention the code applies, with file:line. Audit rows 395 days (stamped at write, deleted by `jobs/audit_retention.py`, which no manifest schedules); PFactory task logs 90 days by env; expiring auth state; everything else "kept until deleted", flagged.
Edit "What is missing" and `data-classification-and-handling-policy.md` line 48 to point at them.

## Alternatives rejected

Propose retention numbers for the unbounded tables: an owner decision (intent default). Fix PII scrubbing default: out of scope (R-004).

## Risks

A provider list drifts as providers are added; the page names the registry file as the source.

## Verification

Each cited path:line re-read on the pinned commits; no secret values in the diff (key names only).
