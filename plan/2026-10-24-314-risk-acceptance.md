---
status: draft
issue: 314
spec: spec/2026-10-24-314-risk-acceptance.md
---

# Plan: Postgres at-rest risk acceptance
Decided (lead, user-approved 2026-10-24): host disk unencrypted, so accept R-014 until a regulated tenant; review 2027-04-24.
## Steps
1. docs/compliance/risk-register.md: add R-014 row and acceptance-log entry → grep R-014
2. docs/compliance/control-matrix.md:28,51: Gap to Partial, note MinIO SSE-S3 and Postgres accepted → grep
3. docs/compliance/policies/encryption-key-mgmt.md: add host-disk finding under Data at rest → grep
## Tests
git diff shows docs only.
## Rollback
Revert the PR.
