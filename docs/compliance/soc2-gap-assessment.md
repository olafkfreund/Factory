# SOC 2 Gap Assessment (Trust Services Criteria)

- **Owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** At least annually and at each management review
- **Framework:** AICPA 2017 Trust Services Criteria, revised points of focus 2022
- **Assessment date:** 2026-11-07

This is a criterion-by-criterion gap assessment against SOC 2. It is an internal
readiness view, not an attestation. It answers one question per criterion: what
control and evidence does the fleet have today, and what is missing. It implements
Factory#324 and sits beside the [control matrix](control-matrix.md), which maps
control domains to criteria, and the [Statement of Applicability](statement-of-applicability.md)
(SoA), which holds the control-by-control status.

## Scope

- **In scope:** Security (CC1-CC9, the common criteria), Availability (A1) and
  Confidentiality (C1). That is 38 criteria.
- **Processing Integrity** is excluded, on the assumption that no
  transaction-accuracy commitment is made to customers. The Security Owner
  confirms that assumption at sign-off.
- **Privacy** is deferred. The matrix maps data governance to "C1, P-series". The
  personal-data exposure stays visible through the C1.1 and C1.2 rows and R-004
  (Factory#320).
- Either decision is reversed at sign-off by adding the category.
- The risk scores in this document are the register's recorded scores with their
  assessment dates (2026-07-24 for R-001 to R-013, 2026-10-24 for R-014 to R-016),
  not a new assessment. See [risk-register.md](risk-register.md).

## Status legend

Met, Partial and Gap use the SoA's definitions of Implemented, Partial and Planned
([statement-of-applicability.md](statement-of-applicability.md), lines 12-19).

1. **Met** needs evidence that covers the whole criterion, and the evidence must
   be an operating output, not only a config file or a policy.
2. **SoA ceiling.** The evidence column names the SoA controls the row relies on.
   Its status is no better than the worst of them (Implemented, then Partial, then
   Planned). A Not Applicable SoA row gives no credit. A Planned control named only
   in the Gap column is the missing part of the criterion, not a control relied
   on, and caps the row at Partial.
3. **Unmapped criteria** (CC6.4, CC6.5, CC6.7, A1.1, and anything the matrix files
   under "CC-series") are Gap unless the row cites a specific SoA row or
   domain-document section that answers them.
4. **An accepted risk gives no implementation credit.** Such a row is Partial at
   best.
5. **When in doubt, round down.**

The "Risk (register)" column gives the risk ID and its inherent score as the
register records it. Accepted risks add `accepted` and their log reference. Where a
register row is outdated the row says so; the register itself is not edited. For
example R-008 says there is no signature-verification gate, while the matrix and
AR-001 cite Kyverno `Enforce`.

Evidence pointers are copied from the cited documents and are not re-verified here.
The SoA and several domain documents carry an assessment date of 2026-07-24, so
some of their "current state" text is older than this assessment.

## Security (CC1-CC9)

| Criterion | Requirement | Status | Control and evidence (incl. SoA rows) | Gap | Risk (register) | Issue |
|---|---|---|---|---|---|---|
| CC1.1 | Commitment to integrity and ethical values | Partial | SoA A.5.10, A.6.4 (Implemented). [acceptable-use-policy.md](policies/acceptable-use-policy.md); violation handling and escalation in the acceptable-use and InfoSec policies ([information-security-policy.md](policies/information-security-policy.md)). Policies only; no operating output cited. | No recorded acknowledgement or enforcement outcome; awareness cadence pending (SoA A.6.3 Planned). | none recorded | #311 |
| CC1.2 | Board or management oversight of internal control | Gap | SoA A.5.4 (Implemented): management commitment in the InfoSec policy; quarterly management review defined in [roles.md](roles.md). | The review is defined but no record of a held review is cited in the sources. No independent board or oversight body. | none recorded | #311 |
| CC1.3 | Structure, authority and responsibility | Partial | SoA A.5.2 (Implemented). [roles.md](roles.md) names the Security Owner and per-domain control owners with a RACI. | Deputy / alternate "to be named"; until individuals are named the Security Owner holds every domain. | none recorded | #311 |
| CC1.4 | Commitment to competence | Gap | SoA A.6.3 (Planned), A.6.1 (Not Applicable, no credit). The policy set is the baseline material. | Recorded awareness and training cadence pending; no hiring or screening process. | none recorded | #311 |
| CC1.5 | Accountability for internal control | Partial | SoA A.5.2, A.6.4, A.5.36 (Implemented). Roles and RACI in [roles.md](roles.md); CI gates enforce SDLC policy. | Accountability is documented, but no evidence of an enforced consequence or a performance review. | none recorded | #311 |
| CC2.1 | Obtains and uses relevant, quality information | Partial | SoA A.8.15, A.5.28 (Implemented). Tamper-evident hash-chain audit log (`audit_chain.py`, `audit_service.py`) and air-gapped `verify-chain` verifier (`AIFactory/apps/web-server/server/audit/__main__.py`). | Background events unchained; no unified fleet audit stream; no SIEM forward ([audit-logging.md](policies/audit-logging.md)). | R-011 (9 Medium) | #313 |
| CC2.2 | Internal communication of responsibilities | Partial | SoA A.5.1, A.5.2, A.5.37 (Implemented). Policy set under [policies/](policies/); [roles.md](roles.md); runbooks and RFCs. | Awareness cadence pending (SoA A.6.3 Planned); `SECURITY.md` and `CODEOWNERS` coverage uneven per [governance-isms.md](policies/governance-isms.md) gap G8. | none recorded | #311 |
| CC2.3 | External communication | Partial | SoA A.5.6 (Implemented). Coordinated disclosure through `SECURITY.md` (PFactory/AIFactory/TFactory). | `SECURITY.md` missing in the hub and CFactory per governance-isms.md G8; authority-contact list pending (SoA A.5.5 Planned). | none recorded | #311, #319 |
| CC3.1 | Specifies objectives to identify and assess risk | Gap | No SoA row. [risk-register.md](risk-register.md) Methodology section states the scoring scale and bands. | No documented security objectives are cited in the sources; the register covers risk, not objectives. | none recorded | #311 |
| CC3.2 | Identifies and analyses risk | Partial | SoA A.5.7 (Implemented). [risk-register.md](risk-register.md): 16 scored risks with owner and treatment; threat models `Factory/docs/security/untrusted-content-threat-model.md`, `sandbox-runtime-class.md`. | Quarterly review is the stated cadence; no review record is cited. Asset inventory pending (SoA A.5.9 Planned). | R-001 to R-016, scores per register | #311 |
| CC3.3 | Considers the potential for fraud | Gap | No SoA row and no domain-document section on fraud risk. | Fraud risk is not assessed. | none recorded | #311 |
| CC3.4 | Identifies and assesses changes that affect controls | Partial | SoA A.5.8 (Implemented). Register is re-scored on any material change; AR-001 records revisit triggers ([risk-register.md](risk-register.md)). RFC process embeds security intent (`Factory/docs/rfc/`). | No cited process that detects a change to the system or vendor landscape and feeds it to the register. | AR-001 (R-012, 8 Medium, accepted) | #311, #322 |
| CC4.1 | Ongoing and separate evaluations | Partial | SoA A.5.36 (Implemented). Daily evidence-collector CronJob (`apps/evidence-collector`, 03:00 UTC) snapshots audit anchor, running image digests and backups index to `factory-evidence/<date>/` (factory-gitops `docs/evidence-collection.md`); it showed Complete for 2026-11-04 to 11-06. Continuous-monitoring plan in [roles.md](roles.md). | Code-scanning snapshot blocked on a new `evidence-github-token` secret; push producers (Trivy, CodeQL) not yet wired; no independent review (SoA A.5.35 Planned). | none recorded | #324 |
| CC4.2 | Communicates deficiencies for corrective action | Gap | SoA A.5.35 (Planned). Corrective actions feed the risk register (SoA A.5.27); [remediation-sla.md](remediation-sla.md). | Annual independent review scheduled but not yet performed; no cited record of deficiencies reported to management. | none recorded | #311 |
| CC5.1 | Selects and develops control activities | Partial | SoA A.5.36, A.8.25 (Implemented). Treatments with owner and wave per register row; [secure-sdlc-policy.md](policies/secure-sdlc-policy.md); CI gates. | Many register treatments are open; controls are domain-by-domain, no consolidated selection record. | R-001 to R-016, see register | #311 |
| CC5.2 | General controls over technology | Partial | SoA A.8.9, A.8.19, A.8.25 (Implemented). Declarative gitops (`factory-gitops/`), pinned inputs, images built in CI. | Factory#499: a filename can be present and not applied to the cluster, so config evidence alone is not credited. Direct-to-main gitops auto-deploy. | R-005 (12 Medium) | #316, #322 |
| CC5.3 | Deploys control activities through policies and procedures | Partial | SoA A.5.1, A.5.37 (Implemented). Policy set under [policies/](policies/), parent [information-security-policy.md](policies/information-security-policy.md); git history is the dated approval record; runbooks. | Policy approval is git history only; no acknowledgement or review-record cited. | none recorded | #311 |
| CC6.1 | Logical access security | Partial | SoA A.5.15, A.5.16, A.5.17, A.8.2, A.8.5, A.8.24 (Implemented, with the SoA's own Partial qualifiers). Org RBAC (`require_org_role`), scoped `acw_` keys, Keycloak `factory` realm (`factory-gitops/infra/keycloak/`). Stored-data protection: MinIO SSE-S3 (factory-gitops#71, #310). | Shared wildcard `APP_API_TOKEN` grants `is_service=True` fleet-admin bypass; MFA not enforced at the IdP; no at-rest encryption or KMS for Postgres and cluster-internal cleartext; manual secret rotation accepted. | R-002 (15 High); R-003 (12 Medium); R-010 (12 Medium); R-014 (6 Low, accepted, log entry 2026-10-24); R-016 (9 Medium, accepted, log entry R-016) | #312, #314, #315 |
| CC6.2 | Access provisioning, changes and removal | Partial | SoA A.5.18, A.6.5 (Implemented). Provisioning, revocation and quarterly review via `access_review.py` (`AIFactory/apps/web-server/server/routes/access_review.py`); access-review NDJSON push (AIFactory#1018) to `factory-evidence/control-plane-push/access-review/`. | No defined review cadence, approver or retained completed review; SoA A.5.18 states a quarterly review, but [iam-access-control.md](policies/iam-access-control.md) gap 6 finds no named approver and no retained completed review, so the cadence is stated, not evidenced. The access-review push merged in AIFactory#1018 (2026-07-25); `evidence-collection.md` still calls it a follow-up because that doc predates the merge. | R-002 (15 High) | #312, #324 |
| CC6.3 | Role-based access and least privilege | Partial | SoA A.5.15, A.8.2, A.8.3 (Implemented). Org RBAC; scoped `acw_` keys (`mcp:read`/`mcp:write`); cred-broker Role scoped to one Secret. | Wildcard-token bypass; no fleet-wide human RBAC role model across the four services. | R-002 (15 High) | #312 |
| CC6.4 | Physical access restrictions | Gap | SoA A.7.1-A.7.6, A.7.8, A.7.10-A.7.14 (Not Applicable, no credit); A.7.7, A.7.9 (Planned). Physical security inherited from the hosting provider under [vendor-and-third-party-policy.md](policies/vendor-and-third-party-policy.md). | No provider assurance report is cited in the sources; operator-endpoint hardening pending (SoA A.8.1). | none recorded | #311 |
| CC6.5 | Disposal of logical and physical assets | Partial | SoA A.8.10 (Implemented, with qualifiers). Retention jobs (`audit_retention.py`, evidence `retention.py`) and MinIO ILM delete data. A.7.14 is Not Applicable (no credit). | ILM expires evidence at 30 days against a 90-day claim; DSAR erasure not done. | R-006 (12 Medium); R-004 (16 High) | #313, #320 |
| CC6.6 | Boundary protection against external threats | Partial | SoA A.8.20, A.8.22 (Implemented); A.8.21, A.8.23 (Partial). Default-deny ingress and egress per-task NetworkPolicy `factory-sandbox-jobs-egress` (`factory-gitops apps/factory-namespace/manifests/networkpolicy-sandbox-jobs.yaml:100,131`); Cloudflare edge. | Egress is 443 to any public IP; 3-5 s unconfined window at pod start (Factory#517); no PodSecurity Admission on task namespaces. Accepted risk gives no credit. | R-012 (8 Medium, accepted, AR-001) | #322 |
| CC6.7 | Restricts transmission, movement and removal of information | Partial | SoA A.5.14 (Implemented). TLS at Cloudflare edge; PII-redaction and egress-class controls ([data-governance.md](policies/data-governance.md)). | Cluster-internal traffic is cleartext; PII can egress to LLM providers via two unscrubbed CLI spawns; no output DLP (SoA A.8.12 Planned). | R-003 (12 Medium); R-004 (16 High) | #314, #320 |
| CC6.8 | Prevents or detects unauthorised or malicious software | Partial | SoA A.8.7, A.8.19 (Implemented). Untrusted content handled as hostile (`prompt_guard.py`); bwrap sandbox (#363); Job seccomp `RuntimeDefault`, `runAsNonRoot` (`AIFactory apps/backend/core/job_dispatch.py:633-635`); Kyverno `Enforce` image-signature gate (`factory-gitops apps/kyverno-policies/manifests/verify-factory-image-signatures.yaml:206`). | No microVM boundary (accepted); no `readOnlyRootFilesystem` on nix Jobs; shared warm `/nix/store` PVC is write-shared ([runtime-isolation.md](policies/runtime-isolation.md) gaps 1, 2, 4, 6). Admission is failurePolicy Ignore per the matrix. | R-012 (8 Medium, accepted, AR-001); R-008 (12 Medium; register text outdated, it says no signature gate) | #318, #322 |
| CC7.1 | Detection and monitoring of vulnerabilities and configuration changes | Partial | SoA A.8.8 (Partial). CodeQL x5, Trivy P0 gate, Dependabot base-image updates; [remediation-sla.md](remediation-sla.md); [vulnerability-register.md](vulnerability-register.md); weekly CodeQL ratchet (`.github/workflows/codeql-ratchet.yml`, Factory#813). | CFactory even-coverage in flight (CFactory#191); agent-CLI pins in factory-gitops unmanaged; no external pen test (accepted). | R-008 (12 Medium; register text outdated); R-015 (8 Medium, accepted, AR-002) | #317, #318 |
| CC7.2 | Monitors components for anomalies | Gap | SoA A.8.15 (Implemented), A.8.16 (Planned). Hash-chain audit log, daily signed anchor, OpenObserve telemetry and a pipeline-health heuristic. | No security alerting or paging, no SIEM forward, no detection for auth failures or anomalous egress; ceiling is the Planned A.8.16 row. | R-009 (16 High); R-011 (9 Medium) | #313, #319 |
| CC7.3 | Evaluates security events | Gap | SoA A.5.25 (Implemented), A.8.16 (Planned). Runbook triage and severity classification ([incident-response.md](policies/incident-response.md)). | No detection layer feeds triage; runbook never exercised; ceiling is the Planned A.8.16 row. | R-009 (16 High) | #313, #319 |
| CC7.4 | Responds to security incidents | Partial | SoA A.5.24, A.5.26 (Implemented). [incident-response-policy.md](policies/incident-response-policy.md) and the [runbook](policies/incident-response.md) with containment, eradication and recovery lifecycle. | Runbook untested (no tabletop or post-incident review run against it); materiality decision-maker and regulator contacts not enumerated (SoA A.5.5 Planned). | R-009 (16 High) | #319 |
| CC7.5 | Recovers from security incidents | Gap | SoA A.5.26 (Implemented); A.5.29, A.5.30 (Planned). Runbook recovery step; blameless review within 5 business days (SoA A.5.27). | Recovery from data loss cannot be guaranteed: backup gap ([business-continuity-dr.md](policies/business-continuity-dr.md) G1, G2; off-cluster copy still missing). A restore drill ran on 2026-08-10 ([dr-runbook.md](dr-runbook.md)), but SoA A.5.29 and A.5.30 are not yet updated. Ceiling is Planned. | R-001 (15 High); R-009 (16 High) | #319, #321 |
| CC8.1 | Authorises, tests and approves changes | Partial | SoA A.8.32 (Implemented, with qualifiers). PR flow, CI gates, RFC-0009 guarded auto-merge ([change-management-sod.md](policies/change-management-sod.md)); branch protection on service repos and factory-gitops; generated autonomy matrix (#1962). | Direct-to-main gitops auto-deploy; `enforce_admins` off so an admin can merge past a red check (#943); Fides change-gate unwired; segregation of duties not yet in place (SoA A.5.3 Planned). | R-005 (12 Medium) | #316 |
| CC9.1 | Mitigates risk of business disruption | Gap | SoA A.5.29, A.5.30, A.8.13, A.8.14 (Planned). BC policy defined ([business-continuity-policy.md](policies/business-continuity-policy.md)); RTO/RPO proposed. | Recovery constrained by the open backup gap; single-instance data stores; a single restore drill (2026-08-10, [dr-runbook.md](dr-runbook.md)) that SoA A.5.30 does not yet reflect. Ceiling is Planned. | R-001 (15 High); R-007 (12 Medium) | #321 |
| CC9.2 | Assesses and manages vendor and partner risk | Gap | SoA A.5.19 (Implemented); A.5.21 (Partial); A.5.20, A.5.22 (Planned). [vendor-and-third-party-policy.md](policies/vendor-and-third-party-policy.md); cosign + dual SBOM on four image repos; Trivy P0 gate. | Processor terms and sub-processor list pending; annual vendor re-review not yet operating; agent-CLI pins unmanaged. Ceiling is Planned. | R-008 (12 Medium; register text outdated) | #318, #320 |

## Availability (A1)

| Criterion | Requirement | Status | Control and evidence (incl. SoA rows) | Gap | Risk (register) | Issue |
|---|---|---|---|---|---|---|
| A1.1 | Capacity management | Partial | SoA A.8.6 (Implemented). KEDA-driven per-task Job scaling (RFC-0016); Postgres and Redis job-state backpressure. | No capacity forecasting or review record cited; single-instance stores (SoA A.8.14 Planned). | R-007 (12 Medium) | #321 |
| A1.2 | Environmental protections, backup and recovery infrastructure | Gap | SoA A.5.29, A.5.30, A.8.13, A.8.14 (Planned). [business-continuity-dr.md](policies/business-continuity-dr.md); `backups-index.json` in the daily evidence snapshot. | Off-cluster encrypted backup is Wave 2 and the SoA records no backups today. Ceiling is Planned. Note: evidence-collection.md describes a 02:15 UTC Postgres backup (`apps/backups`) that the SoA and R-001 do not yet reflect. | R-001 (15 High); R-007 (12 Medium) | #321 |
| A1.3 | Tests recovery plan procedures | Gap | SoA A.5.30 (Planned). [dr-runbook.md](dr-runbook.md) and [business-continuity-dr.md](policies/business-continuity-dr.md). | A Postgres restore drill ran on 2026-08-10 with measured RTO and RPO ([dr-runbook.md](dr-runbook.md)), but SoA A.5.30 still reads Planned and is not yet updated, so the ceiling keeps this row at Gap. No off-cluster copy, and no recurring drill cadence is cited. | R-001 (15 High) | #321 |

## Confidentiality (C1)

| Criterion | Requirement | Status | Control and evidence (incl. SoA rows) | Gap | Risk (register) | Issue |
|---|---|---|---|---|---|---|
| C1.1 | Identifies and maintains confidential information | Gap | SoA A.5.12 (Implemented); A.5.9, A.5.13 (Planned). Four-tier scheme in [data-classification-and-handling-policy.md](policies/data-classification-and-handling-policy.md). | Systematic labelling and asset inventory pending; data-governance.md records no basis for tier-driven handling. Ceiling is Planned. | R-004 (16 High) | #320 |
| C1.2 | Disposes of confidential information | Partial | SoA A.8.10 (Implemented, with qualifiers). Retention jobs (`audit_retention.py`, evidence `retention.py`) and MinIO ILM delete data; test artifacts retained 7 days (SoA A.8.33). | ILM misconfiguration; DSAR erasure deferred by decision 2026-10-24. | R-006 (12 Medium); R-004 (16 High) | #313, #320 |

## Summary

| Category | Criteria | Met | Partial | Gap |
|---|---|---|---|---|
| Security (CC1-CC9) | 33 | 0 | 22 | 11 |
| Availability (A1) | 3 | 0 | 1 | 2 |
| Confidentiality (C1) | 2 | 0 | 1 | 1 |
| **Total** | **38** | **0** | **24** | **14** |

No criterion is Met. Every Partial row has a real control but misses one of the
Met tests: whole-criterion coverage or an operating output.

Criteria whose register risk is High (15 or more inherent):

- R-001 (15, no backups): CC7.5, CC9.1, A1.2, A1.3.
- R-002 (15, wildcard `APP_API_TOKEN`): CC6.1, CC6.2, CC6.3.
- R-004 (16, PII egress): CC6.5, CC6.7, C1.1, C1.2.
- R-009 (16, no alerting): CC7.2, CC7.3, CC7.4, CC7.5.

## Accepted risks

Accepted risks give no implementation credit. Each is recorded, with compensating
controls, expiry and sign-off, in [risk-register.md](risk-register.md); they are not
restated here.

- AR-001 / R-012, runtime isolation (review 2027-04-24).
- AR-002 / R-015, no external penetration test (review 2027-04-24).
- R-014, Postgres at rest unencrypted (dated log entry 2026-10-24).
- R-016, manual secret rotation (dated log entry; review 2027-04-24).

## ISO 27001:2022 gap summary

The control-by-control view is [statement-of-applicability.md](statement-of-applicability.md).
This section summarises it and does not replace it. Row-level counts for the 93
Annex A controls: 54 Implemented, 4 Partial, 18 Planned, 17 Not Applicable.

**Partial (4):** A.5.21, A.8.8, A.8.21, A.8.23.

**Planned (18), grouped by driving issue:**

| Issue | SoA rows |
|---|---|
| #311 governance | A.5.35, A.6.3, A.7.7, A.7.9, A.8.1 |
| #313 audit logging | A.8.16 |
| #316 change management | A.5.3 |
| #319 incident response | A.5.5 |
| #320 data governance (A.5.9 also #315, A.8.12 also #323) | A.5.9, A.5.13, A.5.20, A.5.34, A.8.12 |
| #321 business continuity | A.5.29, A.5.30, A.8.13, A.8.14 |
| none cited in the row | A.5.22 |

## Residual-risk sign-off

The signature accepts the current exposure shown above, not a future target
residual. The table is left unsigned.

Before signing, refresh the risk-register rows R-001, R-006, R-008, R-009, R-011
and R-013. On 2026-11-07 they still describe gaps whose controls have since gone
live (for example, the daily Postgres backup and the 2026-08-10 restore drill in
[dr-runbook.md](dr-runbook.md) under R-001), so the scores shown above may
overstate those risks. Off-cluster backup stays open under
R-001 either way: no issue tracks it since factory-gitops#70 closed.

| Framework | Current exposure accepted? | Scope decisions confirmed | Signed by | Date |
|---|---|---|---|---|
| SOC 2 |  |  |  |  |
| ISO 27001 |  |  |  |  |
