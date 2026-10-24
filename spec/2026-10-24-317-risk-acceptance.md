---
status: draft
issue: 317
intent: intent/2026-10-24-317-risk-acceptance.md
---

# Spec: accept the external pen test residual

## Design
Decided (lead, user-approved 2026-10-24): accept as risk R-014 in docs/compliance/risk-register.md, with a log entry in the Risk-acceptance log, review 2027-04-24 (six months), or earlier on a contract/audit trigger.
Compensating controls: Trivy P0 required gate, CodeQL ratchet (codeql-ratchet.yml, Factory#813), Dependabot (.github/dependabot.yml), gitleaks (secret-scan.yml:13).
Update vuln-patch-management.md (gap 3, Phase 4, criterion) and vulnerability-register.md (pen test section) and the control-matrix row.

## Alternatives rejected
Commission a test now: cost with no contractual driver. Leave as open gap: unowned and undated.

## Risks
Unfound logic and agent-surface flaws (prompt injection, egress). Reopens on any trigger.

## Verification
Links resolve; cited files exist; review date present in each doc.
