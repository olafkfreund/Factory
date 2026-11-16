# Audit readiness: checklist and mock-audit plan

Factory#324. This page answers one question an assessor asks first: what is ready, what is
open, and what only the owner can close. It rates nothing itself. Each status is copied from
the document in the Evidence column; if that document changes, change the row.

Status values: **Ready** (the document exists and its own rating is current), **Open** (work
is tracked and an agent can do it), **Owner** (needs a decision, signature or secret from the
owner).

## Readiness checklist

| Item | Status | Evidence | Tracker | Owner |
|---|---|---|---|---|
| Policy set | Ready | [information-security-policy.md](policies/information-security-policy.md) | Factory#311 | Security Owner |
| Statement of Applicability | Ready | [statement-of-applicability.md](statement-of-applicability.md) | Factory#311 | Security Owner |
| Risk register and treatment | Ready | [risk-register.md](risk-register.md) | Factory#311 | Security Owner |
| Roles and monitoring plan | Ready | [roles.md](roles.md) | Factory#311 | Security Owner |
| Control-to-framework matrix | Ready | [control-matrix.md](control-matrix.md) | Factory#324 | Security Owner |
| SOC 2 gap assessment | Ready | [soc2-gap-assessment.md](soc2-gap-assessment.md) | Factory#324 | Security Owner |
| Residual-risk sign-off (SOC 2, ISO 27001) | Owner | [soc2-gap-assessment.md](soc2-gap-assessment.md): the table is unsigned | Factory#324 | Security Owner |
| First held management review and independent review | Open | [management-review-and-internal-audit.md](management-review-and-internal-audit.md) | [#3694](https://github.com/olafkfreund/Factory/issues/3694) | Security Owner |
| Security awareness record | Open | [training-and-awareness.md](training-and-awareness.md) | [#3693](https://github.com/olafkfreund/Factory/issues/3693) | Security Owner |
| Supplier records in operation | Open | [supplier-management.md](supplier-management.md) | [#3695](https://github.com/olafkfreund/Factory/issues/3695) | Security Owner |
| Backup and restore evidence | Open | [dr-runbook.md](dr-runbook.md), [dr-restore-drill.yaml](dr-restore-drill.yaml); off-cluster copy and MinIO backup not done | [#3681](https://github.com/olafkfreund/Factory/issues/3681), [#3691](https://github.com/olafkfreund/Factory/issues/3691) | BC/DR |
| Automated evidence collection | Owner | `evidence-collector` CronJob runs daily; the code-scanning snapshot needs the `evidence-github-token` secret | Factory#324 | Security Owner |
| Evidence retention floor (13 months) | Ready | [risk-register.md](risk-register.md) R-006 | [#3692](https://github.com/olafkfreund/Factory/issues/3692) (closed) | Audit |
| Vulnerability SLA and register | Ready | [remediation-sla.md](remediation-sla.md), [vulnerability-register.md](vulnerability-register.md) | Factory#317 | Vulnerability |
| Incident-response tabletop | Owner | [ir-tabletop.md](ir-tabletop.md): script ready, not run | [#3688](https://github.com/olafkfreund/Factory/issues/3688) | IR |
| Authority contact list | Open | [statement-of-applicability.md](statement-of-applicability.md) A.5.5 | [#3698](https://github.com/olafkfreund/Factory/issues/3698) | IR |
| Applicability of SEC, NYDFS, FFIEC, SOX | Open | [nydfs-part500-mapping.md](nydfs-part500-mapping.md) | [#3697](https://github.com/olafkfreund/Factory/issues/3697) | Security Owner |
| PCI DSS scope | Ready | [control-matrix.md](control-matrix.md): scoped out, no cardholder data | Factory#324 | Security Owner |

## Mock-audit plan

The standing programme is [management-review-and-internal-audit.md](management-review-and-internal-audit.md)
section 2. It sets scope, cadence, the independence rule, the findings route and the report
template. This plan does not restate those. It is the first audit under that section, and it
counts as the independent review (ISO A.5.35, [#3694](https://github.com/olafkfreund/Factory/issues/3694))
only if the auditor is not the Security Owner and the report says why.

**Status: not held.** No finding below is real until a report in the programme's template
exists.

**Sample.** One control per framework family, chosen for operating evidence:

| Sample | Claim to test | Operating evidence to pull |
|---|---|---|
| SoA A.8.13 backup | Postgres is dumped daily | `mc cat fac/factory-evidence/<date>/backups-index.json` for three dates in the last 30 days |
| SoA A.5.28 evidence | The audit chain is intact and verified daily | `mc cat fac/factory-evidence/<date>/audit-anchor.json` for the same dates; compare the head hash across days |
| SOC 2 CC6 access | Access is reviewed and exported | `mc ls fac/factory-evidence/control-plane-push/access-review/` and one object |
| SoA A.8.8 vulnerabilities | Scans run and results are retained | `mc ls fac/factory-evidence/control-plane-push/codeql/` (no workflow pushes there yet, so expect it empty) |

The `mc` alias and the retrieval steps are in factory-gitops docs/evidence-collection.md
("How an assessor retrieves a control's evidence").

**Pass criterion.** Each sampled control has dated evidence that it operated, not only a
manifest or a policy sentence. Missing evidence is a finding, not a pass.

**Findings.** Each gets an id, severity, owner and due date under
[remediation-sla.md](remediation-sla.md) and goes into [risk-register.md](risk-register.md) if
it is a risk. The A.8.8 sample is expected to fail until the CI scan push is wired.

**Output.** One report in the template of the programme, recorded as section 3 of that document describes, and the rows A.5.35, CC1.2 and CC4.2 updated by the owner.

## Owner actions

These cannot be done by an agent. Decisions are marked as decisions.

1. Create the secret for the code-scanning snapshot (the value is the owner's fine-grained
   PAT with `security_events:read` and `metadata:read` on the factory repos; never commit it):
   `kubectl -n factory create secret generic evidence-github-token --from-literal=token="$PAT"`
2. Sign the residual-risk tables in [soc2-gap-assessment.md](soc2-gap-assessment.md) (decision:
   accept the current exposure shown there).
3. Decision: the date of the mock audit and who runs it. The auditor must not own the
   controls audited.
4. Decision: wire CI scan results into the evidence store. The in-cluster MinIO is not reachable
   from GitHub runners, so this needs S3 credentials in CI. The push contract is
   `mc cp trivy.json fac/factory-evidence/control-plane-push/trivy/<repo>-<YYYY-MM-DD>.json`
   and `mc cp results.sarif fac/factory-evidence/control-plane-push/codeql/<repo>-<YYYY-MM-DD>.sarif`.
5. Run the [IR tabletop](ir-tabletop.md) and file the record.
