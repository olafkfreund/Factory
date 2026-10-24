---
status: approved
issue: 315
author: olafkfreund
---

# Intent: accept manual agenix rotation for factory-secrets (#315)

## Problem
Long-lived secrets (factory-secrets, minio-creds) have no automated rotation, cadence or runbook.
## Proposed outcome
Manual agenix rotation is the documented, accepted control: runbook, cadence, register entry, review date.
## Affected users and systems
Operator on p510; factory-gitops `factory-secrets`, `minio-creds`; docs/compliance.
## Constraints
Docs only. No claim without evidence. Cadence: 90d API tokens, 365d keys, immediately on suspected exposure.
## Open questions
Decided (lead, user-approved 2026-10-24): accept manual rotation. Review 2027-04-24.
