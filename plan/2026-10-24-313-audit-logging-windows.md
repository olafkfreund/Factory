---
status: draft
issue: 313
spec: spec/2026-10-24-313-audit-logging-windows.md
---

# Plan: audit retention windows

Decisions: one table in gap 4 mapping each store's window to PCI 10.5.1 and AU-11; OpenObserve stated as 3650 days (pending its PR); MinIO 30 days flagged.

## Steps

1. `docs/compliance/policies/audit-logging.md` Retention bullet (~line 89): add the OpenObserve window. Verify: re-read.
2. Same file, gap 4 (~line 126): add the window table. Verify: rows match code and manifests.
   Traps: no org or person names.

## Tests

Pre-commit hooks pass.

## Rollback

Revert the commit.
