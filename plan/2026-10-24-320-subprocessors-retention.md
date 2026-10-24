---
status: approved
issue: 320
spec: spec/2026-10-24-320-subprocessors-retention.md
---

# Plan: sub-processors, data residency, Postgres retention

Decisions: add sub-processor and Postgres retention subsections to `data-governance.md`; residency recorded as-is; no new retention numbers; point line 48 of the classification policy at them; part of #320, does not close it.

## Steps

1. `data-governance.md`: insert "Sub-processors" and "Postgres retention schedule" before "What is missing". Verify: `grep -n "^### " docs/compliance/policies/data-governance.md`.
2. Same file, "What is missing": reword the Postgres-retention and residency sentences to point at the new sections. Verify: no sentence still says residency or Postgres retention is undocumented.
3. `data-classification-and-handling-policy.md` line 48: point at the schedule. Verify: `git diff` shows one changed sentence.
   Traps: key names only, never values; no org or person names.

## Tests

Pre-commit hooks pass; every cited file:line resolves at its pinned commit.

## Rollback

Revert the commit.

Deviation (review round 1): added Context7 and RapidAPI rows (CONTEXT7_KEY, RAPIDAPI_KEY injected from factory-secrets).
