# Information Security Policy

- **Policy owner:** Security Owner (CISO function) — see [roles.md](../roles.md)
- **Approved by:** Factory maintainers via pull-request review (the merge of this
  document is its approval record; git history is the dated evidence)
- **Applies to:** All contributors, service accounts, and automated agents operating
  the Factory fleet
- **Review cadence:** Annually, and on any material change to scope, architecture, or
  risk posture
- **Frameworks:** ISO/IEC 27001:2022 Clause 5.2 and A.5.1; SOC 2 CC1/CC5; NYDFS 23
  NYCRR 500.3; SEC Reg S-K Item 106; FFIEC management booklet

This is the top-level policy of the Factory Information Security Management System
(ISMS). Every other policy in [`policies/`](.) sits beneath it, and every technical
control domain under [`docs/compliance/`](../README.md) implements it.

## Purpose

To state management's commitment to protecting the confidentiality, integrity, and
availability of the systems and data the Factory fleet processes, and to establish the
policy framework, objectives, and accountability that govern how the fleet is built,
run, and changed. This policy exists so that the strong technical controls the fleet
already operates (audit hash-chain, cosign/SBOM supply-chain signing, signed task
contracts, independent verification with evidence gates, sandboxed execution) are held
inside a management system that assigns ownership, assesses risk, and demonstrates
oversight — not left as undocumented engineering.

## Scope

The ISMS covers (ISO 27001 Clause 4.3):

- **Repositories (6):** `Factory` (spec/contract hub), `PFactory` (planning),
  `AIFactory` (build), `TFactory` (verification), `CFactory` (cockpit), and
  `factory-gitops` (deploy manifests).
- **Runtime substrate:** the k3d Kubernetes cluster, per-task Kubernetes Jobs, the
  MinIO object store (evidence and artifacts), and the Postgres job-state store.
- **Pipelines:** the GitHub Actions CI/CD for all repositories, including build,
  scan, sign, and deploy workflows.
- **Data:** task specifications and plans, source code produced by agents, verification
  evidence, audit records, and any customer content passed through a run.
- **People and agents:** human contributors, machine/service accounts, and the LLM
  agents that plan, build, and verify.

Third-party LLM providers, GitHub, Cloudflare, and cloud infrastructure are in scope as
managed vendors under the [vendor-and-third-party-policy.md](vendor-and-third-party-policy.md).

## Objectives

1. Preserve the integrity and provenance of everything the fleet produces (signed
   artifacts, tamper-evident audit trail, independently verified output).
2. Enforce least privilege for every human and machine identity.
3. Detect and respond to security events within defined timelines.
4. Recover fleet state within defined RTO/RPO after a disruption.
5. Assess and treat risk continuously, with named owners and recorded decisions.
6. Keep the control set provable: every claim maps to real code, config, or evidence.

### Measurable objectives (ISO 27001 Clause 6.2; SOC 2 CC3.1)

Each objective above has a measure, a target and a data source. The table holds targets,
not results: the Security Owner reads the current value from the source at each
quarterly management review ([management-review-and-internal-audit.md](../management-review-and-internal-audit.md))
and records it in the minutes. Factory#3699.

| # | Measure | Target | Data source | Frequency |
|---|---|---|---|---|
| 1 | Audit-chain verification verdict | `ok` every day; any `broken` or missed run handled as an incident | CronJob `audit-anchor-alert`, [audit-logging.md](audit-logging.md) | Daily |
| 1 | Released fleet images carrying a cosign signature and dual SBOM | 100 percent of releases | CI deploy workflows, [supply-chain-integrity.md](supply-chain-integrity.md) | Per release |
| 2 | Access review completed and unexpected grants removed | Every quarter | `access_review.py` export, [iam-access-control.md](iam-access-control.md) | Quarterly |
| 3 | Time to fix open vulnerabilities | Within the windows in [remediation-sla.md](../remediation-sla.md); no open item past its due date without a recorded exception | [vulnerability-register.md](../vulnerability-register.md) | Monthly |
| 3 | Security incidents with a post-incident review | 100 percent of Sev-1 and Sev-2 | [incident-response.md](incident-response.md) records | Per incident |
| 4 | Restore drill with measured RPO and RTO | At least once a year, results recorded in [dr-runbook.md](../dr-runbook.md) | Drill record | Annually |
| 5 | Risk register reviewed and each High risk has an owner and treatment | Quarterly | [risk-register.md](../risk-register.md) | Quarterly |
| 5 | Management review held and minuted | Every quarter | Minutes | Quarterly |
| 5 | Internal audit completed | Once a year | Audit report | Annually |
| 5 | Security training completed by everyone with fleet access | Within 12 months of the last completion | [training-and-awareness.md](../training-and-awareness.md) records | Annually |
| 6 | Controls whose evidence is a file, not an operating output, that are named as such | Zero unnamed; each such control states its gap | [soc2-gap-assessment.md](../soc2-gap-assessment.md) | Annually |

The owner may change a target at a management review; the change is minuted.

## Policy statements

1. **Security is owned.** A named Security Owner is accountable for the ISMS, and every
   control domain has a named control owner ([roles.md](../roles.md)). Ownership is not
   optional or implicit.
2. **Least privilege by default.** Access to systems and data is granted on need, scoped,
   and reviewed; see [access-control-policy.md](access-control-policy.md).
3. **Change is controlled.** All changes reach protected branches through peer-reviewed
   pull requests that pass the CI security gates; see
   [secure-sdlc-policy.md](secure-sdlc-policy.md).
4. **Provenance is mandatory.** Released container images are signed (cosign keyless)
   and ship a dual SBOM (SPDX and CycloneDX); task plans are HMAC-signed contracts;
   agent output is independently verified before it is trusted.
5. **Everything security-relevant is logged tamper-evidently.** The audit hash-chain
   with a daily signed anchor and an air-gapped verifier is the system of record; see
   the [audit-logging](audit-logging.md) domain.
6. **Data is classified and handled to its class.** See
   [data-classification-and-handling-policy.md](data-classification-and-handling-policy.md);
   PII sent to third-party LLMs is governed by the redaction control.
7. **Risk is assessed and treated.** The [risk register](../risk-register.md) is
   maintained per the documented methodology; residual risk above the Medium band
   requires Security Owner sign-off.
8. **We can recover.** Backups and tested restore for Postgres and MinIO are required;
   see [business-continuity-policy.md](business-continuity-policy.md).
9. **Vendors are assessed.** Third parties are reviewed before onboarding and
   periodically thereafter; see
   [vendor-and-third-party-policy.md](vendor-and-third-party-policy.md).
10. **Incidents are handled to a plan.** See
    [incident-response-policy.md](incident-response-policy.md) and the operational
    [incident-response runbook](incident-response.md); statutory notification timelines
    (SEC four business days; NYDFS 72 hours) are honored.
11. **Exceptions are explicit.** Any deviation from a policy is recorded as a risk-register
    entry with a compensating control, an owner, and an expiry date, approved by the
    Security Owner.

## Roles and responsibilities

Defined in full in [roles.md](../roles.md). In summary: the Security Owner is
accountable for the ISMS and reports to leadership quarterly; control owners maintain
their domain's controls and evidence; every contributor and agent operator is
responsible for following this policy and the acceptable-use policy.

## Related controls

- Program index and control-to-framework mapping:
  [README.md](../README.md), [control-matrix.md](../control-matrix.md)
- Governance and ISMS domain assessment: [governance-isms.md](governance-isms.md)
- All subordinate policies in [`policies/`](.)
- Statement of Applicability: [statement-of-applicability.md](../statement-of-applicability.md)

## Review and enforcement

This policy is reviewed at least annually and after any material change. Non-compliance
is handled through the change process (a non-compliant change does not merge) and,
where an incident results, through the incident-response process. Repeated or wilful
non-compliance by a contributor is escalated to the Security Owner.
