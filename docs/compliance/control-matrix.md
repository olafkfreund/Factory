# Control-to-Framework Matrix

Implements Factory#324. One row per control domain, mapped to each in-scope
framework's requirement, with current status and the child issue that drives it.
This is the artifact an assessor uses to trace every framework requirement to a
control and its evidence.

The domains have machine-readable ids in `apis/control-catalog.json`, which the
PFactory run signature uses for its `controls` field (#1961).

Status legend:

- **Strong** — implemented and evidenced; credit-worthy today.
- **Partial** — a real control exists but has coverage, enforcement, or
  evidence gaps.
- **Gap** — not implemented; remediation planned in the domain document.

PCI DSS is scoped out (no cardholder data). FedRAMP is deferred; where a control
maps to a NIST 800-53 family it is noted for future ConMon. FFIEC is mapped at
booklet level only (IT Examination Handbook); whether it applies is an open
owner decision (Factory#3697).

## Framework mapping

| Domain | ISO 27001:2022 | SOC 2 (TSC) | SOX ITGC | NYDFS 500 | FFIEC IT Handbook (booklet) | SEC | 800-53 (FedRAMP) | Status |
|---|---|---|---|---|---|---|---|---|
| Governance / ISMS (#311) | Cl. 4-10, A.5.1-.4 | CC1-CC5 | Control env. | 500.2-.4 | Management | Risk-mgmt disclosure | PM, CA | Partial |
| IAM & access control (#312) | A.5.15-.18, A.8.2-.5 | CC6.1-.3 | Access to programs/data | 500.7, 500.12 | Information Security | - | AC, IA | Partial |
| Audit logging & retention (#313) | A.8.15-.16 | CC7.2-.3 | Monitoring | 500.6 | Information Security; Audit | - | AU | Partial |
| Encryption at rest & KMS (#314) | A.8.24 | CC6.1 | - | 500.15 | Information Security | - | SC-12/-13/-28 | Partial (MinIO SSE-S3; Postgres risk-accepted R-014) |
| Secrets management (#315) | A.8.24, A.5.17 | CC6.1 | Access to programs | 500.15 | Information Security | - | IA-5 | Partial (manual rotation accepted, R-016) |
| Change mgmt & SoD (#316) | A.8.32 | CC8.1 | Change mgmt, SoD | 500.3 | Development and Acquisition | - | CM | Partial |
| Vuln & patch mgmt (#317) | A.8.8 | CC7.1 | - | 500.5 | Information Security | - | RA-5, SI-2 | Partial |
| Supply-chain integrity (#318) | A.5.19-.23, A.8.30 | CC7, CC9 | - | 500.11 | Outsourcing Technology Services | Supply-chain risk | SR | Partial (SLSA Build L2 target) |
| Incident response (#319) | A.5.24-.28 | CC7.3-.5 | - | 500.17 (72h) | Information Security | Item 1.05 (4-day) | IR | Partial |
| Data governance & PII (#320) | A.5.9-.14, A.8.10-.12 | C1, P-series | - | 500.13 | Information Security | - | MP, SC | Partial |
| Business continuity / DR (#321) | A.5.29-.30, A.8.13-.14 | A1.2-.3 | Backup/recovery | - | Business Continuity Management | - | CP | Partial |
| Runtime isolation (#322) | A.8.22, A.8.9 | CC6.6, CC6.8 | - | - | - | - | SC-7/-39, CM-6 | Accepted risk (AR-001, review 2027-04-24) |
| Agentic-AI governance (#323) | A.5.23 | CC-series | - | - | - | - | SA, RA | Strong (partial) |
| Evidence & audit-readiness (#324) | Cl. 9.1, A.5.36 | CC4.1 | Evidence | 500.2 | Audit | - | CA-2, CA-7 | Partial |

Note: ISO/IEC 42001, the NIST AI RMF, and the EU AI Act also apply to the
agentic-AI domain (#323); they are tracked in that domain document rather than
as separate columns here.

## Status, evidence, and driving issue

| Domain | Implementing control (cited in domain doc) | Top gap | Issue |
|---|---|---|---|
| Governance / ISMS | Policy set under [policies/](policies/); [risk register](risk-register.md); [SoA](statement-of-applicability.md); [roles.md](roles.md) names the Security Owner and domain owners | No management review held and no independent review performed (Factory#3694); no recorded awareness cadence (Factory#3693); no documented security objectives or fraud-risk assessment (Factory#3699); deputy owner not named | #311 (closed), #3693, #3694, #3699 |
| IAM & access control | Scoped `acw_` keys, org RBAC, `access_review.py`, cred-broker (#292) | Shared wildcard `APP_API_TOKEN` grants `is_service=True` fleet-admin bypass | #312 |
| Audit logging | Hash-chain + daily signed anchor + air-gapped verifier | No paging; no alert rules for auth-failure or egress anomalies | #313 |
| Encryption at rest | TLS at Cloudflare edge; agenix host key | Postgres PV not encrypted (R-014, accepted to 2027-04-24); no KMS; cluster-internal cleartext | #314 |
| Secrets management | agenix + cred-broker rotation; `scan_secrets.py`; gitleaks required check | Manual agenix rotation accepted (R-016, review 2027-04-24); runbook in encryption-key-mgmt.md; inventory in factory-gitops docs/secrets-management.md; SOPS claim not real | #315 |
| Change mgmt & SoD | PR flow, CI gates, Fides change-gate (built); merge autonomy: [generated autonomy matrix + control mapping](https://aifactory.freundcloud.com/compliance/autonomy-matrix) (#1962) | Direct-to-main gitops auto-deploy; branch protection with required checks on all four service repos (and factory-gitops); `enforce_admins` is on for `main` in the four service repos and Factory since 2026-10-22, but off on every `dev` branch and on factory-gitops `main`, where an admin can still merge past a red check via the API (#943, AIFactory#2014); Fides unwired | #316 |
| Vuln & patch mgmt | CodeQL x5, Trivy P0 gate, Dependabot base-image updates x4; remediation SLA + vulnerability register documented | CFactory Trivy gate live (`image-build.yml:164,199,233`, CFactory#191 merged); external pen test not run, accepted risk R-015 (review 2027-04-24); factory-gitops agent-CLI pins unmanaged (#436 gap #7) | #317 |
| Supply-chain integrity | Cosign + dual SBOM on all four image repos; Kyverno Enforce admission gate; SLSA Build L2 target | Admission is failurePolicy Ignore, tag-based, no SBOM-attestation rule; deploy-path provenance mode not explicit; signed commits; no L3 claim | #318 |
| Incident response | [IR policy](policies/incident-response-policy.md) and [runbook](policies/incident-response.md) (SoA A.5.24-A.5.28 Implemented); SECURITY.md disclosure; audit chain for forensics | Runbook untested (no tabletop); no paging; an audit-chain alert exists (CronJob `audit-anchor-alert`, daily); no authority contact list (Factory#3698) | #319 (closed), #3688, #3698 |
| Data governance | Four-tier [classification policy](policies/data-classification-and-handling-policy.md); redactor `llm_pii_redactor.py`, outbound scrub on by default and mandatory for regulated projects; retention jobs and MinIO ILM; local-Ollama egress option | Two direct CLI spawns unscrubbed (R-004); no labelling of stored artifacts (A.5.13); no asset inventory register (A.5.9); no content DLP (A.8.12); DSAR deferred by decision 2026-10-24; evidence ILM below the 13-month floor (Factory#3692) | #320 (closed), #3692 |
| Business continuity / DR | Nightly `pg_dumpall` (CronJob `postgres-backup`, last success 2026-11-07); MinIO versioning (`minio-create-bucket`, 2026-10-22); restore drill 2026-08-10 ([dr-runbook.md](dr-runbook.md)) | Single failure domain, no off-cluster copy (Factory#3681); MinIO is not backed up; single instance (`replicas: 1`) | #321, #3681 |
| Runtime isolation | bwrap sandbox (#363), Job NetworkPolicy + non-root (default-on) | No microVM (accepted, AR-001); coarse 443 egress; no PodSecurity Admission; CIS baseline not assessed (kube-bench is the revisit action) | #322 |
| Agentic-AI governance | Signed contracts, injection/egress guards, RFC-0001a/0006/0012 gates; merge autonomy: [generated autonomy matrix + control mapping](https://aifactory.freundcloud.com/compliance/autonomy-matrix) (#1962) | No model registry/eval gate; no output DLP; trusted-plan key no rotation | #323 |
| Evidence & audit-readiness | This directory; daily evidence-collector CronJob (factory-gitops#74) snapshots audit anchor, running-image digests and backups index to `factory-evidence/<date>/`; access-review NDJSON push (AIFactory#1018); [SOC 2 gap assessment](soc2-gap-assessment.md) | Code-scanning snapshot blocked on a new `evidence-github-token` secret (security_events:read); per-framework residual-risk sign-off not yet given | #324 |

## Statement of Applicability

The ISO 27001:2022 Annex A Statement of Applicability (all 93 controls, marked
implemented / planned / not-applicable with cited evidence) is authored under
the governance domain — see
[policies/governance-isms.md](policies/governance-isms.md). This matrix is the
cross-framework view; the SoA is the ISO-specific control-by-control view. Both
draw evidence from the same domain documents.

## Automated evidence collection

A daily CronJob (`apps/evidence-collector` in factory-gitops, 03:00 UTC)
snapshots what the cluster can produce on its own into the versioned
`factory-evidence` MinIO bucket, one dated prefix per run: the audit-chain
head and verdict, the image digests actually running, and the Postgres
backup objects present. A control-plane job pushes the fleet access review
as NDJSON to `factory-evidence/control-plane-push/access-review/<date>.ndjson`
(AIFactory#1018). The operator and assessor guide is
`factory-gitops/docs/evidence-collection.md`. Still missing: the
code-scanning (CodeQL) snapshot, which needs a read token the collector does
not have (#324). Until then, each repo's weekly CodeQL ratchet job reports
its alert count.
