---
status: approved
issue: 317
spec: spec/2026-10-24-317-risk-acceptance.md
---

# Plan: accept the external pen test residual

Decided (lead, user-approved 2026-10-24): accept R-014, review 2027-04-24, compensating controls as in spec.

## Steps
1. docs/compliance/risk-register.md: add R-014 row and acceptance-log entry -> grep R-014
2. docs/compliance/policies/vuln-patch-management.md: gap 3, Phase 4, criterion -> grep 2027-04-24
3. docs/compliance/vulnerability-register.md: pen test section; control-matrix.md row 54 -> grep 2027-04-24

## Tests
grep 2027-04-24 across docs/compliance returns all four files.

## Rollback
Revert the PR.
