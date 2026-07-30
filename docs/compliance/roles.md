# Security Roles, Management Review, and Continuous Monitoring

- **Policy owner:** Security Owner (CISO function)
- **Review cadence:** Annually, and whenever an owner changes
- **Frameworks:** ISO/IEC 27001:2022 Clause 5.3 and A.5.2; SOC 2 CC1.3; NYDFS 500.4;
  SEC Reg S-K Item 106(c)

This document names the people accountable for the Factory ISMS, defines the
management-review cadence that demonstrates oversight (ISO Clause 9.3), and sets the
continuous-monitoring plan that watches control effectiveness between reviews (ISO
Clause 9.1). It is the join between the [policies](policies/) and the humans who own them.

## Security roles

The fleet is small, so one person may hold several roles; the point is that each
responsibility is named, not that headcount is large. Current assignments reference the
real repository ownership (`CODEOWNERS` is set to `@dataseeek` in `AIFactory`,
`PFactory`, and `TFactory`).

| Role | Holder | Accountable for |
|---|---|---|
| Security Owner (CISO function) | Fleet maintainer (`@dataseeek`) | The ISMS as a whole; risk acceptance; policy approval; quarterly report to leadership |
| Deputy / alternate | To be named | Acting Security Owner when the owner is unavailable (avoids a single point of failure for incident decisions) |
| Incident Commander | Security Owner (default), delegable per incident | Running an incident to resolution and post-incident review; statutory notification decisions |
| Control owners | Per domain (below) | Maintaining their domain's controls, evidence, and remediation |

### Control owners (one per domain)

Each control domain under [`docs/compliance/`](README.md) has an accountable owner.
Until individuals are named, the Security Owner holds every domain and this table is the
backlog for delegation.

| Domain | Document | Owner |
|---|---|---|
| Governance / ISMS | [governance-isms.md](policies/governance-isms.md) | Security Owner |
| IAM & access control | [iam-access-control.md](policies/iam-access-control.md) | Security Owner |
| Audit logging & retention | [audit-logging.md](policies/audit-logging.md) | Security Owner |
| Encryption & key management | [encryption-key-mgmt.md](policies/encryption-key-mgmt.md) | Security Owner |
| Secrets management | [secrets-management.md](policies/secrets-management.md) | Security Owner |
| Change management & SoD | [change-management-sod.md](policies/change-management-sod.md) | Security Owner |
| Vulnerability & patch mgmt | [vuln-patch-management.md](policies/vuln-patch-management.md) | Security Owner |
| Supply-chain integrity | [supply-chain-integrity.md](policies/supply-chain-integrity.md) | Security Owner |
| Incident response | [incident-response.md](policies/incident-response.md) | Incident Commander |
| Data governance & PII | [data-governance.md](policies/data-governance.md) | Security Owner |
| Business continuity / DR | [business-continuity-dr.md](policies/business-continuity-dr.md) | Security Owner |
| Runtime isolation | [runtime-isolation.md](policies/runtime-isolation.md) | Security Owner |
| Agentic-AI governance | [agentic-ai-governance.md](policies/agentic-ai-governance.md) | Security Owner |

## RACI for key ISMS activities

| Activity | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Approve a policy | Policy author | Security Owner | Control owner | Contributors |
| Accept a risk above Medium | Control owner | Security Owner | Incident Commander | Leadership |
| Grant a policy exception | Requestor | Security Owner | Control owner | — |
| Declare and run an incident | Incident Commander | Security Owner | Control owner(s) | Leadership, affected parties |
| Sign off a control as Implemented in the SoA | Control owner | Security Owner | — | Assessor |

## Management review

The Security Owner chairs a management review of the ISMS **quarterly**, and ad hoc
after any Sev-1 incident. This is the ISO Clause 9.3 oversight record.

Standing agenda:

1. Risk register — new risks, re-scoring, treatment progress, and any risk acceptances.
2. Incidents since last review — what happened, root cause, and corrective actions.
3. Control effectiveness — the continuous-monitoring signals below, with trend.
4. Audit and assessment findings, and their remediation status.
5. Policy exceptions granted and their expiry.
6. Changes to scope, architecture, vendors, or the threat landscape.
7. Resourcing and decisions requiring leadership.

Each review is minuted to `docs/compliance/management-review/YYYY-QN.md` (decisions,
owners, due dates). The minutes are the evidence that oversight occurred, and the
risk-acceptance decisions recorded there are authoritative.

## Continuous monitoring

Between reviews, control effectiveness is watched through signals the fleet already
emits. Where a signal exists, it is cited rather than invented; where it does not yet
exist, wiring it is a tracked gap (see the referenced issue).

| Signal | Source | Cadence | Escalation |
|---|---|---|---|
| Audit-chain integrity | Daily signed anchor + air-gapped external verifier | Daily | Anchor failure or chain break pages the Incident Commander (alerting wiring tracked, Factory#313/#319) |
| Supply-chain provenance | cosign signature + dual SBOM presence in CI | Per build | Missing signature/SBOM fails the build; CFactory parity tracked Factory#318 |
| Vulnerability posture | CodeQL (5 repos), Trivy P0 build gate, Dependabot (security alerts + base images) | Per PR / per build / daily | P0 fails the build; CodeQL alerts triaged; SLA tracked Factory#317 |
| Access review | `access_review.py` export | Quarterly | Unexpected grant removed and logged; wildcard-token retirement tracked Factory#312 |
| CI gate pass rate | GitHub Actions | Continuous | Sustained failures reviewed at management review |
| Backup success / restore test | Backup jobs (being introduced) | Per backup / periodic restore drill | Backup absence is the current top risk, tracked Factory#321 |
| Auth-failure and anomaly spikes | Application + audit logs | Continuous (alerting to be wired) | Spike pages Incident Commander; SIEM forward tracked Factory#313 |

The continuous-monitoring output (scan results, anchor-verifier logs, access-review
exports, backup/restore logs) is the evidence sampled at each management review and,
where automated, snapshotted into the MinIO evidence store.
