---
status: draft
issue: 322
spec: spec/2026-10-24-322-risk-acceptance.md
---
# Plan: record accepted risk for runtime isolation (#322)
Decided (lead, user-approved 2026-10-24): accept baseline; triggers = multi-tenant untrusted workloads, runsc nix support; CIS "not assessed", revisit action kube-bench.
## Steps
1. docs/compliance/risk-register.md R-012 row + Risk-acceptance log: add AR-001 (accepted 2026-10-24, review 2027-04-24, compensating controls with file:line) -> grep AR-001
2. docs/compliance/control-matrix.md lines 36, 59: status "Accepted risk (AR-001)", CIS not assessed -> grep AR-001
3. docs/compliance/policies/runtime-isolation.md gaps 1 and 7 + acceptance boxes: record decision and triggers -> grep AR-001
## Tests
`git diff --stat` shows only docs/compliance and the three artifacts.
## Rollback
Revert the PR.
