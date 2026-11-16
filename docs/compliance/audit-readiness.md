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
| Authority contact list | Owner | [policies/incident-response.md](policies/incident-response.md#authority-contact-list): list defined with owner and review date; contacts empty | [#3698](https://github.com/olafkfreund/Factory/issues/3698) | IR |
| Applicability of SEC, NYDFS, FFIEC, SOX | Ready | [framework-applicability.md](framework-applicability.md): not applicable, decided 2026-11-16 by delegation; the owner confirms the three premises (checklist item 1) | [#3697](https://github.com/olafkfreund/Factory/issues/3697) | Security Owner |
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

## Owner checklist

These cannot be done by an agent: each is an attestation, a signature, a secret or a booking.
Dates are **targets** set on 2026-11-16 so the items come in dependency order; they are not
events and nothing here is ticked. Tick an item only with a dated record in the named document.
Decisions are marked as decisions. Never commit a secret value.

| # | Target | Action | Template or runbook | Unlocks |
|---|---|---|---|---|
| 1 | 2026-11-23 | [ ] Confirm the three premises behind the scope decision and fill the premise table. | [framework-applicability.md](framework-applicability.md) | Keeps SEC, NYDFS, FFIEC and SOX at not applicable (#3697) |
| 2 | 2026-11-23 | [ ] Create the secret for the code-scanning snapshot: a fine-grained PAT with `security_events:read` and `metadata:read` on the factory repos, then `kubectl -n factory create secret generic evidence-github-token --from-literal=token="$PAT"` | factory-gitops docs/evidence-collection.md | Code-scanning evidence snapshot (#324) |
| 3 | 2026-11-30 | [ ] Complete the first training cycle and commit the dated completion record. | [training-and-awareness.md](training-and-awareness.md) | SoA A.6.3, SOC 2 CC1.4 (#3693) |
| 4 | 2026-12-07 | [ ] Check each operator host, attach the evidence, sign the attestation. | [operator-endpoint-standard.md](operator-endpoint-standard.md) | SoA A.8.1, A.7.7, A.7.9 (#3696) |
| 5 | 2026-12-14 | [ ] Fill the supplier register from the real contracts, record the processor terms, collect each provider's SOC 2 or ISO report (or record the gap), publish the sub-processor list. | [supplier-management.md](supplier-management.md) | SoA A.5.20, A.5.22, SOC 2 CC9.2, CC6.4 (#3695) |
| 6 | 2026-12-16 | [ ] Fill the authority contact list, starting with the data-protection authority (jurisdiction, controller or processor role, authority, clock). | [policies/incident-response.md](policies/incident-response.md#authority-contact-list) | SoA A.5.5 (#3698) |
| 7 | 2026-12-18 | [ ] Hold and minute the first management review: accept or change the security-objective targets and the R-017 scoring, record measured values. Decision: accept or change the targets. | [management-review-and-internal-audit.md](management-review-and-internal-audit.md) | SOC 2 CC1.2, CC3.1, CC3.3, CC4.2 (#3694, #3699) |
| 8 | 2026-12-18 | [ ] Sign the residual-risk tables. Decision: accept the current exposure shown there; this also confirms Processing Integrity excluded and Privacy deferred. | [soc2-gap-assessment.md](soc2-gap-assessment.md) | Residual-risk sign-off (#324) |
| 9 | 2026-12-18 | [ ] Decision: book the mock-audit date and name the auditor, who must not own the controls audited. Target week: 2027-01-18. | Plan above | Mock audit (#324) |
| 10 | 2027-01-08 | [ ] Run the IR tabletop and file the record. | [ir-tabletop.md](ir-tabletop.md) | IR evidence (#3688) |
| 11 | 2027-01-08 | [ ] Confirm an offline backup of one agenix decrypting identity outside p510 and p620. | factory-gitops docs/secrets-management.md | Secrets recovery (#310) |
| 12 | 2027-01-08 | [ ] Enter the real last-rotated dates in the rotation ledger. | factory-gitops docs/secrets-management.md | Rotation evidence (#310) |
| 13 | 2027-01-08 | [ ] Test the MinIO KEK emergency procedure in a planned window, or record a risk acceptance with a review date. | [policies/encryption-key-mgmt.md](policies/encryption-key-mgmt.md) | #314 |
| 14 | 2027-01-08 | [ ] Decision: provide an off-cluster backup target and credentials, or record a risk acceptance with a review date. | [dr-runbook.md](dr-runbook.md) | #3681 |
| 15 | 2027-01-08 | [ ] Decision: wire CI scan results into the evidence store. The in-cluster MinIO is not reachable from GitHub runners, so this needs S3 credentials in CI. The push contract is `mc cp trivy.json fac/factory-evidence/control-plane-push/trivy/<repo>-<YYYY-MM-DD>.json` and `mc cp results.sarif fac/factory-evidence/control-plane-push/codeql/<repo>-<YYYY-MM-DD>.sarif`. | factory-gitops docs/evidence-collection.md | Scan-results evidence (#324) |
| 16 | 2027-01-22 | [ ] Hold the mock audit, file the report in the programme's template and, if it was independent, cite it for A.5.35. | [management-review-and-internal-audit.md](management-review-and-internal-audit.md) | SoA A.5.35, SOC 2 CC4.2 (#3694, #324) |
| 17 | 2027-02-26 | [ ] Run and record the first annual supplier re-review. | [supplier-management.md](supplier-management.md) | SoA A.5.22 (#3695) |

Closing the epics: #324 closes when items 2, 8, 9 and 16 are done; #310 closes when every child
issue is closed.
