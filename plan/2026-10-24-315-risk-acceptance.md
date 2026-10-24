---
status: approved
issue: 315
spec: spec/2026-10-24-315-risk-acceptance.md
---

# Plan: manual rotation risk acceptance (#315)

Decided (lead, user-approved 2026-10-24): accept manual agenix rotation; 90d tokens, 365d keys, immediate on exposure; review 2027-04-24.
## Steps
1. docs/compliance/policies/encryption-key-mgmt.md: add rotation runbook section -> grep section
2. docs/compliance/risk-register.md: add R-014 and acceptance-log entry -> grep R-014
3. docs/compliance/control-matrix.md: update secrets rows (lines 29, 52) -> grep
## Tests
Markdown only; pre-commit hooks. Rollback: revert the PR.
