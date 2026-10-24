---
status: approved
issue: 313
intent: intent/2026-10-24-313-audit-logging-windows.md
---

# Spec: audit retention windows

## Design

Add a table under "Retention-policy formalisation" in `audit-logging.md`: store, window, source, PCI 10.5.1 (12m, 3m hot), FedRAMP AU-11 (90d online). Postgres `audit_logs`: 395 days (meets both). OpenObserve: 3650 days via `ZO_COMPACT_DATA_RETENTION_DAYS` (factory-gitops PR, v0.90.3 default pinned; meets both). MinIO `role=log`: 30 days (meets AU-11 online window only if it is the only copy; below PCI). Update the Retention bullet to name the OpenObserve window.

## Alternatives rejected

Recommend one fleet window now: needs the owner; the table only states what exists.

## Risks

The OpenObserve row is true only once the factory-gitops PR syncs; the text says so.

## Verification

Each row traced to a file; `git diff` touches one file.
