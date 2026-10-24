---
status: approved
issue: 315
intent: intent/2026-10-24-315-risk-acceptance.md
---

# Spec: manual rotation risk acceptance (#315)

## Design
Decided (lead, user-approved 2026-10-24): add rotation runbook + cadence to policies/encryption-key-mgmt.md, risk R-014 plus acceptance-log entry in risk-register.md, update control-matrix row. Cite gitleaks required check and factory-gitops docs/secrets-management.md.
## Alternatives rejected
Automated rotation (ESO/Vault/sealed-secrets): out of scope now; revisit at review.
## Risks
Stale secrets between rotations; relies on operator discipline. Compensating: gitleaks, gitops "no literal secrets in manifests" check.
## Verification
Links resolve; cited checks confirmed via branch protection API and secret-scan.yml.
