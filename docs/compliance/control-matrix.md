# Control-to-Framework Matrix

Implements Factory#324. One row per control domain, mapped to each in-scope
framework's requirement, with current status and the child issue that drives it.
This is the artifact an assessor uses to trace every framework requirement to a
control and its evidence.

Status legend:

- **Strong** — implemented and evidenced; credit-worthy today.
- **Partial** — a real control exists but has coverage, enforcement, or
  evidence gaps.
- **Gap** — not implemented; remediation planned in the domain document.

PCI DSS is scoped out (no cardholder data). FedRAMP is deferred; where a control
maps to a NIST 800-53 family it is noted for future ConMon.

## Framework mapping

| Domain | ISO 27001:2022 | SOC 2 (TSC) | SOX ITGC | NYDFS 500 | SEC | 800-53 (FedRAMP) | Status |
|---|---|---|---|---|---|---|---|
| Governance / ISMS (#311) | Cl. 4-10, A.5.1-.4 | CC1-CC5 | Control env. | 500.2-.4 | Risk-mgmt disclosure | PM, CA | Gap |
| IAM & access control (#312) | A.5.15-.18, A.8.2-.5 | CC6.1-.3 | Access to programs/data | 500.7, 500.12 | - | AC, IA | Partial |
| Audit logging & retention (#313) | A.8.15-.16 | CC7.2-.3 | Monitoring | 500.6 | - | AU | Partial |
| Encryption at rest & KMS (#314) | A.8.24 | CC6.1 | - | 500.15 | - | SC-12/-13/-28 | Gap |
| Secrets management (#315) | A.8.24, A.5.17 | CC6.1 | Access to programs | 500.15 | - | IA-5 | Partial |
| Change mgmt & SoD (#316) | A.8.32 | CC8.1 | Change mgmt, SoD | 500.3 | - | CM | Partial |
| Vuln & patch mgmt (#317) | A.8.8 | CC7.1 | - | 500.5 | - | RA-5, SI-2 | Partial |
| Supply-chain integrity (#318) | A.5.19-.23, A.8.30 | CC7, CC9 | - | 500.11 | Supply-chain risk | SR | Partial |
| Incident response (#319) | A.5.24-.28 | CC7.3-.5 | - | 500.17 (72h) | Item 1.05 (4-day) | IR | Gap |
| Data governance & PII (#320) | A.5.9-.14, A.8.10-.12 | C1, P-series | - | 500.13 | - | MP, SC | Gap |
| Business continuity / DR (#321) | A.5.29-.30, A.8.13-.14 | A1.2-.3 | Backup/recovery | - | - | CP | Gap |
| Runtime isolation (#322) | A.8.22, A.8.9 | CC6.6, CC6.8 | - | - | - | SC-7/-39, CM-6 | Partial |
| Agentic-AI governance (#323) | A.5.23 | CC-series | - | - | - | SA, RA | Strong (partial) |
| Evidence & audit-readiness (#324) | Cl. 9.1, A.5.36 | CC4.1 | Evidence | 500.2 | - | CA-2, CA-7 | Gap |

Note: ISO/IEC 42001, the NIST AI RMF, and the EU AI Act also apply to the
agentic-AI domain (#323); they are tracked in that domain document rather than
as separate columns here.

## Status, evidence, and driving issue

| Domain | Implementing control (cited in domain doc) | Top gap | Issue |
|---|---|---|---|
| Governance / ISMS | RFCs, SECURITY.md, CODEOWNERS (uneven) | No ISMS: no policy set, risk register, SoA, or named CISO/owners | #311 |
| IAM & access control | Scoped `acw_` keys, org RBAC, `access_review.py`, cred-broker (#292) | Shared wildcard `APP_API_TOKEN` grants `is_service=True` fleet-admin bypass | #312 |
| Audit logging | Hash-chain + daily signed anchor + air-gapped verifier | Background/WS events unchained; no SIEM forward; no security alerting | #313 |
| Encryption at rest | TLS at Cloudflare edge; agenix host key | No at-rest encryption on DB/MinIO; no KMS; cluster-internal cleartext | #314 |
| Secrets management | agenix + cred-broker rotation; `scan_secrets.py` | Rotation one credential deep; no inventory; SOPS claim not real | #315 |
| Change mgmt & SoD | PR flow, CI gates, Fides change-gate (built) | Direct-to-main gitops auto-deploy; no branch protection; Fides unwired | #316 |
| Vuln & patch mgmt | CodeQL x5, Trivy P0 gate, Renovate x5 | CFactory unscanned; no remediation SLA; no pen test | #317 |
| Supply-chain integrity | Cosign + dual SBOM on PFactory/AIFactory/TFactory | CFactory unsigned; no signature-verification admission gate | #318 |
| Incident response | SECURITY.md disclosure; audit chain for forensics | No IR runbook wired to alerting; untested; no paging | #319 |
| Data governance | Redactor `llm_pii_redactor.py`; local-Ollama egress option | PII egress to LLM providers default-on; no classification/retention | #320 |
| Business continuity / DR | Cred-broker CronJob only | Zero backups for Postgres/MinIO; no tested restore; RPO unbounded | #321 |
| Runtime isolation | bwrap sandbox (#363), Job NetworkPolicy + non-root (default-on) | No microVM; coarse 443-to-any egress; no PodSecurity Admission | #322 |
| Agentic-AI governance | Signed contracts, injection/egress guards, RFC-0001a/0006/0012 gates | No model registry/eval gate; no output DLP; trusted-plan key no rotation | #323 |
| Evidence & audit-readiness | This directory (Wave 0) | No automated evidence collection; no per-framework gap sign-off | #324 |

## Statement of Applicability

The ISO 27001:2022 Annex A Statement of Applicability (all 93 controls, marked
implemented / planned / not-applicable with cited evidence) is authored under
the governance domain — see
[policies/governance-isms.md](policies/governance-isms.md). This matrix is the
cross-framework view; the SoA is the ISO-specific control-by-control view. Both
draw evidence from the same domain documents.

## Automated evidence collection (planned)

Per Factory#324, evidence collection will be automated as scheduled jobs that
snapshot into the existing tamper-evident evidence store: access-review exports
(`access_review.py`), scan results (Trivy/CodeQL), backup-success and
restore-test logs, config baselines, and the audit-anchor verifier output. Until
then, evidence is collected on demand per the "Evidence artifacts" section of
each domain document.
