# Factory Compliance Program

This directory is the Factory fleet's security and compliance program: the
policy artifacts, control-to-framework mapping, and per-domain gap assessments
an assessor reads to judge audit-readiness against ISO 27001, SOC 2, SOX
(ITGC), PCI DSS, FedRAMP, FFIEC, NYDFS Part 500, and the SEC cyber rules.

It implements epic [Factory#310](https://github.com/olafkfreund/Factory/issues/310).
No one self-certifies these frameworks (ISO/FedRAMP need an accredited assessor,
SOC 2 a CPA, PCI a QSA); this program builds the provable control set and
evidence. Certification is a separate engagement.

## How this is organized

- [`control-matrix.md`](control-matrix.md) — the control-to-framework matrix
  (Factory#324): one row per control domain, mapped to every in-scope framework,
  with current status and the child issue that drives it. Start here.
- [`policies/`](policies/) — one grounded control document per domain. Each
  carries: purpose, current state (cited against real code and manifests),
  gaps, a phased remediation plan, acceptance criteria, and the evidence
  artifacts to collect.

## Control domains

| Domain | Document | Issue |
|---|---|---|
| Governance and ISMS | [governance-isms.md](policies/governance-isms.md) | [#311](https://github.com/olafkfreund/Factory/issues/311) |
| IAM and access control | [iam-access-control.md](policies/iam-access-control.md) | [#312](https://github.com/olafkfreund/Factory/issues/312) |
| Audit logging and retention | [audit-logging.md](policies/audit-logging.md) | [#313](https://github.com/olafkfreund/Factory/issues/313) |
| Encryption at rest and key management | [encryption-key-mgmt.md](policies/encryption-key-mgmt.md) | [#314](https://github.com/olafkfreund/Factory/issues/314) |
| Secrets management and rotation | [secrets-management.md](policies/secrets-management.md) | [#315](https://github.com/olafkfreund/Factory/issues/315) |
| Change management and separation of duties | [change-management-sod.md](policies/change-management-sod.md) | [#316](https://github.com/olafkfreund/Factory/issues/316) |
| Vulnerability and patch management | [vuln-patch-management.md](policies/vuln-patch-management.md) | [#317](https://github.com/olafkfreund/Factory/issues/317) |
| Supply-chain integrity | [supply-chain-integrity.md](policies/supply-chain-integrity.md) | [#318](https://github.com/olafkfreund/Factory/issues/318) |
| Incident response and breach notification | [incident-response.md](policies/incident-response.md) | [#319](https://github.com/olafkfreund/Factory/issues/319) |
| Data governance and PII egress | [data-governance.md](policies/data-governance.md) | [#320](https://github.com/olafkfreund/Factory/issues/320) |
| Business continuity and DR | [business-continuity-dr.md](policies/business-continuity-dr.md) | [#321](https://github.com/olafkfreund/Factory/issues/321) |
| Runtime isolation and hardening | [runtime-isolation.md](policies/runtime-isolation.md) | [#322](https://github.com/olafkfreund/Factory/issues/322) |
| Agentic-AI governance | [agentic-ai-governance.md](policies/agentic-ai-governance.md) | [#323](https://github.com/olafkfreund/Factory/issues/323) |
| Evidence and audit-readiness | [control-matrix.md](control-matrix.md) | [#324](https://github.com/olafkfreund/Factory/issues/324) |

## Framework scope

| Framework | In scope | Rationale |
|---|---|---|
| ISO 27001 / SOC 2 | Yes (foundational) | Baseline for any serious SaaS; do first. |
| SEC cyber rules | Conditional | Applies if operated by a public company (4-business-day incident disclosure). |
| NYDFS Part 500 / FFIEC | Conditional | Applies if you or your customers are regulated financial firms. |
| SOX ITGC | Conditional | Applies for a public company whose systems affect financial reporting. |
| PCI DSS | Scoped out | No cardholder data flows through the fleet today. Re-scope if payments are added. |
| FedRAMP | Deferred | Large lift (NIST 800-53 + 3PAO + ConMon); pursue only if US federal is a target. |

The program tracks one control domain per framework requirement, because the
eight frameworks overlap roughly 70 percent. Framework-specific divergences
(FedRAMP 800-53 baseline, PCI cardholder scope, SEC and NYDFS notification
timelines) are called out in the relevant domain document.

## Grounded posture (2026-07-24)

This assessment was produced by inspecting the live code and manifests, not the
marketing summary. Where reality diverged from the epic's original posture, the
program documents reality.

### Genuine strengths (credit where due)

- Tamper-evident HMAC audit hash-chain with a daily signed anchor and an
  air-gapped external verifier (#313).
- Cosign keyless signing plus dual SBOM (SPDX and CycloneDX) across PFactory,
  AIFactory, and TFactory — not AIFactory-only as first framed (#318).
- Signed task contracts (HMAC plan envelope), fail-closed prompt-injection /
  SSRF / egress guards, independent TFactory verification with evidence gates
  (RFC-0001a) and Verification Assurance Levels (RFC-0006) (#323).
- CodeQL on all five code repos, a Trivy P0 build gate, and Renovate fleet-wide
  (#317).
- Per-task Job NetworkPolicy and non-root securityContext, now shipped and
  default-on (AIFactory#812, TFactory#651) — the epic's original "no
  NetworkPolicy / no securityContext" gap is closed (#322).
- Scoped `acw_` keys, org RBAC, and an access-review exporter already exist as
  the target model to build on (#312).

### Corrections to the original posture

- The "SOPS-encrypted secrets in gitops" claim is not on disk (no `.sops.yaml`,
  no encrypted manifests). Real mechanism: host agenix plus out-of-band
  `kubectl create secret` (base64 in etcd, no EncryptionConfiguration).
  Independently confirmed by the #314 and #315 groundings.
- Latent evidence-durability bug: MinIO ILM expires objects at 30 days while
  comments claim 90-day evidence retention, so verification evidence can be
  purged before its claim closes — undermining the audit chain's survivability
  assumption. Independently surfaced by #313, #321, and #317.

## Remediation roadmap

Wave 0 is this change (documentation foundation). Waves 1 through 3 are
engineering, each shipped as its own small, scoped PR against the relevant repo
and tracked on its child issue. Sequence is highest risk-reduction first.

**Wave 0 — foundation (this PR, documentation):** ISMS policy skeleton, control
matrix, Statement of Applicability approach, incident-response runbook, data
classification scheme, and the per-domain gap assessments. Satisfies gap #6
("no compliance/policy artifacts") and gives an assessor one folder to open.

**Wave 1 — quick high-value fixes:**
- Fix the MinIO evidence-retention ILM rule (30d -> the intended 90d/13-month
  floor) so evidence survives its claim (#313, #321).
- Default the outbound PII scrub on for third-party LLM calls (#320).
- Apply branch protection as code across all repos, including AIFactory and
  factory-gitops (#316).
- Wire security alerting on anchor-failure, chain-break, and auth-failure spikes
  (#313, #319).

**Wave 2 — structural hardening:**
- Postgres and MinIO backups with a tested restore — the top gap, RPO is
  currently unbounded (#321).
- Retire the shared wildcard `APP_API_TOKEN` in favor of scoped `acw_`
  service credentials; remove the `is_service=True` blanket authz bypass (#312).
- Bring CFactory to parity: Trivy scan, dual SBOM, cosign signing, plus a
  fleet-wide signature-verification admission gate (#317, #318).

**Wave 3 — depth:**
- At-rest encryption for DB and object store, formal key management and rotation
  (#314, #315).
- Signed commits, Fides change-gate / four-eyes wiring, and deploy approvals
  (#316); HA Postgres with PITR (#321).
- Trusted-plan HMAC key rotation with key IDs and expiry, an approved-model
  registry with eval gates, and output-side DLP (#323).
- Per-destination egress allowlist and PodSecurity Admission on task namespaces;
  evaluate a microVM runtime where the substrate allows (#322).

## Next steps

1. Confirm the framework scope decisions above (ISO 27001 + SOC 2 first).
2. Adopt the Wave 0 artifacts and assign control owners per the ISMS document.
3. Schedule Wave 1 as individual PRs; each closes against its child issue with
   evidence attached.
