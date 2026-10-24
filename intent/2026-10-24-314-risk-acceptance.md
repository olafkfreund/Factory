---
status: approved
issue: 314
author: olafkfreund
---

# Intent: Postgres encryption at rest, risk acceptance

## Problem
MinIO SSE-S3 is on (factory-gitops#71, #310). Postgres (data-postgres-0) is on a plain local-path PV; the compliance docs still say no at-rest control exists.
## Proposed outcome
The docs record the verified host-disk state and a risk-register entry with owner, compensating controls and a review date.
## Affected users and systems
p620 k3d cluster; docs/compliance/{risk-register,control-matrix}.md, policies/encryption-key-mgmt.md.
## Constraints
Read-only verification; no invented controls; no closing #314 without evidence.
## Open questions
Decided (lead, user-approved 2026-10-24): if host disk is unencrypted, accept until a regulated tenant, review 2027-04-24.
