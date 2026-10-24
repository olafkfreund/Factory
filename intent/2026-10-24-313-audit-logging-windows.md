---
status: approved
issue: 313
author: olafkfreund
---
# Intent: per-framework audit retention windows in audit-logging.md

**Problem:** `audit-logging.md` gap 4 says nothing maps retention windows to PCI 12m/3m hot and AU-11, and does not state the OpenObserve window (Factory#313).
**Outcome:** The policy maps PCI 10.5.1 and AU-11 to Postgres 395 days, OpenObserve (pinned to 3650 days in factory-gitops, pending its PR) and MinIO, and says which windows meet which framework. Part of #313.
**Affected:** Factory `docs/compliance/policies/audit-logging.md`.
**Constraints:** Claim only what code and manifests show; MinIO 30-day log expiry stays flagged as below PCI.
**Open questions:** None.
