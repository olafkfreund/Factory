# Statement of Applicability (ISO/IEC 27001:2022 Annex A)

- **Owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** At least annually and at each management review
- **Framework:** ISO/IEC 27001:2022 Clause 6.1.3(d) — the SoA is a mandatory document
- **Assessment date:** 2026-07-24

This is the ISO-specific, control-by-control view of the ISMS. It covers all **93** Annex
A controls across the four themes (A.5 Organizational 37, A.6 People 8, A.7 Physical 14,
A.8 Technological 34). Each control is marked:

- **Implemented** — a real control exists; the justification cites the evidence (file,
  RFC, CI job, or domain document).
- **Partial** — a real control exists but does not cover the whole scope, or is declared
  and not enforced on the current substrate; the justification states which part is live
  and cites the issue tracking the remainder. A control that cannot be shown to operate
  is not Implemented.
- **Planned** — applicable but not yet fully in place; the justification cites the
  driving Factory child issue and remediation wave.
- **Not Applicable** — out of scope for a cloud-only, remote, automated fleet; the
  justification states why (justified, not silently dropped).

Evidence pointers are relative to the repository roots under
`GitHub/{Factory,PFactory,AIFactory,TFactory,CFactory,factory-gitops}`. The
[control-matrix.md](control-matrix.md) gives the cross-framework view; this SoA and that
matrix draw evidence from the same [domain documents](policies/). Owner tags map to
[roles.md](roles.md) (Security Owner unless a domain control owner is named).

## A.5 Organizational controls (37)

| Control | Title | Status | Justification and evidence | Owner |
|---|---|---|---|---|
| A.5.1 | Policies for information security | Implemented | Policy set under [policies/](policies/), parent [information-security-policy.md](policies/information-security-policy.md); git history is the dated approval record. | Security Owner |
| A.5.2 | Information security roles and responsibilities | Implemented | [roles.md](roles.md) names the Security Owner and per-domain control owners with a RACI. | Security Owner |
| A.5.3 | Segregation of duties | Planned | SoD intent stated in [secure-sdlc-policy.md](policies/secure-sdlc-policy.md); weakened by push-to-main auto-deploy and single-owner CODEOWNERS (R-005, Factory#316). | Change-mgmt |
| A.5.4 | Management responsibilities | Implemented | Management commitment in the InfoSec policy; quarterly management review defined in [roles.md](roles.md). | Security Owner |
| A.5.5 | Contact with authorities | Planned | Notification obligations (SEC/NYDFS/GDPR) documented in the [IR runbook](policies/incident-response.md); a maintained authority-contact list is pending (Factory#319). | IR |
| A.5.6 | Contact with special interest groups | Implemented | Coordinated disclosure via `SECURITY.md` (PFactory/AIFactory/TFactory); dependency advisories via GitHub / Dependabot alerts. | Security Owner |
| A.5.7 | Threat intelligence | Implemented | Threat models `Factory/docs/security/untrusted-content-threat-model.md`, `sandbox-runtime-class.md`; CodeQL/Trivy feeds. | Runtime |
| A.5.8 | Information security in project management | Implemented | RFC process (`Factory/docs/rfc/`) embeds security intent (task contracts, evidence gates, VAL) into design. | Security Owner |
| A.5.9 | Inventory of information and other associated assets | Planned | Assets enumerated in the ISMS scope; a maintained asset/secret inventory register is pending (Factory#315/#320). | Data |
| A.5.10 | Acceptable use of information and other associated assets | Implemented | [acceptable-use-policy.md](policies/acceptable-use-policy.md). | Security Owner |
| A.5.11 | Return of assets | Not Applicable | No issued physical assets; access is credential-based and revoked on departure (leaver process, [access-control-policy.md](policies/access-control-policy.md)). | Security Owner |
| A.5.12 | Classification of information | Implemented | Four-tier scheme in [data-classification-and-handling-policy.md](policies/data-classification-and-handling-policy.md). | Data |
| A.5.13 | Labelling of information | Planned | Classification defined; systematic labelling of stored artifacts pending (Factory#320). | Data |
| A.5.14 | Information transfer | Implemented | TLS at Cloudflare edge; PII-redaction and egress-class controls for third-party transfer ([data-governance.md](policies/data-governance.md)). | Data |
| A.5.15 | Access control | Implemented | Org RBAC (`require_org_role`), scoped `acw_` keys, cluster RBAC; [access-control-policy.md](policies/access-control-policy.md). | IAM |
| A.5.16 | Identity management | Implemented | Keycloak `factory` realm with GitHub upstream IdP (`factory-gitops/infra/keycloak/`). | IAM |
| A.5.17 | Authentication information | Implemented | Secrets via out-of-band K8s Secrets + agenix; cred-broker rotation ([secrets-management.md](policies/secrets-management.md)). Partial: broad rotation pending (R-002). | Secrets |
| A.5.18 | Access rights | Implemented | Provisioning/revocation and quarterly review via `access_review.py` (`AIFactory/apps/web-server/server/routes/access_review.py`). | IAM |
| A.5.19 | Information security in supplier relationships | Implemented | [vendor-and-third-party-policy.md](policies/vendor-and-third-party-policy.md). | Security Owner |
| A.5.20 | Addressing information security within supplier agreements | Planned | Processor-terms/DPA and sub-processor list pending publication (Factory#320). | Security Owner |
| A.5.21 | Managing information security in the ICT supply chain | Partial | Dependency pinning (`flake.lock`, digest-pinned bases), Trivy P0 gate, Dependabot base-image updates ([supply-chain-integrity.md](policies/supply-chain-integrity.md)). Downgraded from Implemented 2026-07-30: pinning without an operating update bot is a frozen supply chain, not a managed one, and that was the actual state until Factory#436. `factory-gitops` agent-CLI pins remain unmanaged. | Supply-chain |
| A.5.22 | Monitoring, review and change management of supplier services | Planned | Annual vendor re-review defined in policy; recurring review cadence being operationalized. | Security Owner |
| A.5.23 | Information security for use of cloud services | Implemented | Cluster/edge/provider controls; egress-class routing for LLM providers ([runtime-isolation.md](policies/runtime-isolation.md), [data-governance.md](policies/data-governance.md)). | Runtime |
| A.5.24 | Information security incident management planning and preparation | Implemented | [incident-response-policy.md](policies/incident-response-policy.md) + [runbook](policies/incident-response.md) with severity/roles/lifecycle. | IR |
| A.5.25 | Assessment and decision on information security events | Implemented | Runbook triage (t0=confirmed) and severity classification ([incident-response.md](policies/incident-response.md)). | IR |
| A.5.26 | Response to information security incidents | Implemented | Runbook containment/eradication/recovery lifecycle. | IR |
| A.5.27 | Learning from information security incidents | Implemented | Blameless post-incident review within 5 business days; corrective actions feed the risk register. | IR |
| A.5.28 | Collection of evidence | Implemented | Tamper-evident audit hash-chain + air-gapped `verify-chain` verifier (`AIFactory/apps/web-server/server/audit/__main__.py`). | Audit |
| A.5.29 | Information security during disruption | Planned | BC policy defined; recovery constrained by the open backup gap (R-001, Factory#321). | BC/DR |
| A.5.30 | ICT readiness for business continuity | Planned | RTO/RPO proposed; backups, tested restore, and DR runbook pending (Factory#321). | BC/DR |
| A.5.31 | Legal, statutory, regulatory and contractual requirements | Implemented | Notification obligations mapped in the IR runbook's breach-notification matrix; GDPR ROPA `AIFactory/guides/compliance/dpia-data-flow.md`. | Security Owner |
| A.5.32 | Intellectual property rights | Implemented | Dual SBOM (SPDX/CycloneDX) inventories dependencies and their licences; OSS licence compliance tracked in supply-chain. | Supply-chain |
| A.5.33 | Protection of records | Implemented | Audit records are tamper-evident and retained 13 months (`audit_retention.py`); note evidence ILM bug (R-006). | Audit |
| A.5.34 | Privacy and protection of PII | Planned | Redactor + DPIA exist; PII-egress-by-default and DSAR gaps open (R-004, Factory#320). | Data |
| A.5.35 | Independent review of information security | Planned | Annual independent review scheduled but not yet performed (governance domain, Factory#311). | Security Owner |
| A.5.36 | Compliance with policies, rules and standards | Implemented | CI gates enforce SDLC policy; management review checks control effectiveness ([roles.md](roles.md)). | Security Owner |
| A.5.37 | Documented operating procedures | Implemented | Runbooks and RFCs (`Factory/docs/rfc/`, IR runbook, BC/DR remediation, bootstrap-flow docs). | Security Owner |

## A.6 People controls (8)

| Control | Title | Status | Justification and evidence | Owner |
|---|---|---|---|---|
| A.6.1 | Screening | Not Applicable | Small maintainer team with no employment/hiring process; contributor access is credential- and review-gated rather than HR-screened. Re-scope if the team formalizes employment. | Security Owner |
| A.6.2 | Terms and conditions of employment | Not Applicable | No employment relationship; acceptable use is bound via [acceptable-use-policy.md](policies/acceptable-use-policy.md) instead. | Security Owner |
| A.6.3 | Information security awareness, education and training | Planned | Policy set is the baseline material; a recorded awareness cadence is pending (Factory#311). | Security Owner |
| A.6.4 | Disciplinary process | Implemented | Violation handling and escalation defined in the acceptable-use and InfoSec policies. | Security Owner |
| A.6.5 | Responsibilities after termination or change of employment | Implemented | Immediate access revocation on departure ([access-control-policy.md](policies/access-control-policy.md), leaver process). | IAM |
| A.6.6 | Confidentiality or non-disclosure agreements | Not Applicable | No employees/contractors under NDA today; confidentiality obligations flow through the acceptable-use policy. Re-scope on formal engagements. | Security Owner |
| A.6.7 | Remote working | Implemented | Fully remote by design; access is MFA-intended, least-privilege, and audited (device hardening tracked A.8.1). | IAM |
| A.6.8 | Information security event reporting | Implemented | Reporting via Security Owner and `SECURITY.md` coordinated disclosure ([acceptable-use-policy.md](policies/acceptable-use-policy.md)). | IR |

## A.7 Physical controls (14)

The fleet is cloud/cluster-hosted with no organization-owned data centre, office, or
physical media in scope; physical security of the underlying facilities is inherited from
the cloud/hosting provider under the vendor policy. Most A.7 controls are therefore Not
Applicable to the fleet's own operation, justified per control below.

| Control | Title | Status | Justification and evidence | Owner |
|---|---|---|---|---|
| A.7.1 | Physical security perimeters | Not Applicable | No owned facility; inherited from hosting provider (vendor policy). | Security Owner |
| A.7.2 | Physical entry | Not Applicable | No owned facility; provider-inherited. | Security Owner |
| A.7.3 | Securing offices, rooms and facilities | Not Applicable | No owned office in ISMS scope; remote-only operation. | Security Owner |
| A.7.4 | Physical security monitoring | Not Applicable | Provider-inherited for hosting facilities. | Security Owner |
| A.7.5 | Protecting against physical and environmental threats | Not Applicable | Provider-inherited (power, cooling, fire). | Security Owner |
| A.7.6 | Working in secure areas | Not Applicable | No secure physical areas operated by the fleet. | Security Owner |
| A.7.7 | Clear desk and clear screen | Planned | Applies to operator endpoints; covered by remote-working guidance, formal statement pending (A.8.1). | Security Owner |
| A.7.8 | Equipment siting and protection | Not Applicable | No owned server/equipment; provider-inherited. | Security Owner |
| A.7.9 | Security of assets off-premises | Planned | Operator laptops are the only off-premises assets; endpoint hardening is tracked at A.8.1. | Security Owner |
| A.7.10 | Storage media | Not Applicable | No removable physical media; all storage is cloud volumes/object store. | Security Owner |
| A.7.11 | Supporting utilities | Not Applicable | Provider-inherited (power/network utilities). | Security Owner |
| A.7.12 | Cabling security | Not Applicable | Provider-inherited. | Security Owner |
| A.7.13 | Equipment maintenance | Not Applicable | No owned physical equipment; provider-inherited. | Security Owner |
| A.7.14 | Secure disposal or re-use of equipment | Not Applicable | No owned physical media to dispose; cloud-volume decommissioning is logical deletion (A.8.10). | Security Owner |

## A.8 Technological controls (34)

| Control | Title | Status | Justification and evidence | Owner |
|---|---|---|---|---|
| A.8.1 | User endpoint devices | Planned | Operator-endpoint hardening standard pending; interim reliance on remote-working guidance (Factory#311). | Security Owner |
| A.8.2 | Privileged access rights | Implemented | Least-privilege cluster RBAC (e.g. cred-broker Role scoped to one Secret); org admin role gated. Partial: wildcard-token bypass (R-002). | IAM |
| A.8.3 | Information access restriction | Implemented | Org RBAC and scoped `acw_` keys (`mcp:read`/`mcp:write`) restrict access to data and functions. | IAM |
| A.8.4 | Access to source code | Implemented | GitHub org access + CODEOWNERS; branch protection on protected repos ([secure-sdlc-policy.md](policies/secure-sdlc-policy.md)). Partial: coverage uneven (R-005). | Change-mgmt |
| A.8.5 | Secure authentication | Implemented | Keycloak OIDC (JWT/cookie validation, `TokenAuthMiddleware`). Partial: MFA enforcement pending (R-010). | IAM |
| A.8.6 | Capacity management | Implemented | KEDA-driven per-task Job scaling (RFC-0016); Postgres/Redis job-state backpressure. | Runtime |
| A.8.7 | Protection against malware | Implemented | Untrusted content treated as hostile (`prompt_guard.py`); no execution of untrusted binaries outside the sandbox; image scanning via Trivy. | Runtime |
| A.8.8 | Management of technical vulnerabilities | Partial | CodeQL (5 repos), Trivy P0 gate (`test_p0_supply_chain.py`), Dependabot. Partial: no remediation SLA, CFactory unscanned (Factory#317). Status corrected from Implemented 2026-07-30: the Renovate leg of this control had never operated in any repo (Factory#436), and the row already listed two partials while claiming Implemented. | Vuln |
| A.8.9 | Configuration management | Implemented | Declarative gitops (`factory-gitops/`), pinned inputs, per-task securityContext in manifests. | Change-mgmt |
| A.8.10 | Information deletion | Implemented | Retention jobs (`audit_retention.py`, evidence `retention.py`) and MinIO ILM delete data; note ILM misconfig (R-006). Partial: DSAR erasure (R-004). | Data |
| A.8.11 | Data masking | Implemented | PII redactor (`llm_pii_redactor.py`) masks SSN/email/phone/card. Partial: outbound off-by-default (R-004). | Data |
| A.8.12 | Data leakage prevention | Planned | Egress guards + secret scanners exist but are target-level, not content DLP; output DLP pending (Factory#320/#323). | Data |
| A.8.13 | Information backup | Planned | No backups of Postgres/MinIO today; off-cluster encrypted backup is Wave 2 (R-001, Factory#321). | BC/DR |
| A.8.14 | Redundancy of information processing facilities | Planned | Single-instance data stores on node-local storage; HA/redundancy is Wave 3 (R-007, Factory#321). | BC/DR |
| A.8.15 | Logging | Implemented | Tamper-evident hash-chain audit log (`audit_chain.py`, `audit_service.py`). Partial: background events unchained (R-011). | Audit |
| A.8.16 | Monitoring activities | Planned | OpenObserve telemetry + pipeline anomaly heuristic; security alerting/SIEM forward pending (R-009, Factory#313). | Audit |
| A.8.17 | Clock synchronization | Implemented | Cluster nodes/pods use host NTP; audit anchor stamps at 00:00 UTC daily. | Runtime |
| A.8.18 | Use of privileged utility programs | Implemented | Auth-disable switches prohibited in prod ([access-control-policy.md](policies/access-control-policy.md)); privileged actions run in hardened, non-root pods. | Runtime |
| A.8.19 | Installation of software on operational systems | Implemented | Images are built in CI and deployed via gitops; no ad-hoc installation on running systems (immutable containers). | Change-mgmt |
| A.8.20 | Networks security | Partial | Default-deny-ingress per-task NetworkPolicy applied to the reference cluster (`factory-gitops apps/factory-namespace`, Factory#462); Cloudflare edge. Partial: covers the `kube_sandbox` Job pods, not the `job_dispatch` lane (Factory#502); the chart templates that cover both ship only to self-hosters (Factory#499). | Runtime |
| A.8.21 | Security of network services | Partial | Edge TLS termination. Egress allowlist (kube-dns + 443, RFC1918 excepted) is declared but **not enforced on this substrate**: the cluster CNI enforces NetworkPolicy ingress only (Factory#462). Also coarse where it does apply (R-012). | Runtime |
| A.8.22 | Segregation of networks | Partial | Namespace separation; per-task Job network isolation covers the `kube_sandbox` lane only, ingress-side only ([runtime-isolation.md](policies/runtime-isolation.md), Factory#462/#499/#502). | Runtime |
| A.8.23 | Web filtering | Planned | Outbound egress allowlist is written (443/DNS only, RFC1918 blocked) but unenforced on this CNI (Factory#462); in-process egress/SSRF guards are the only live control. Per-destination FQDN pinning pending (R-012). | Runtime |
| A.8.24 | Use of cryptography | Implemented | HMAC audit chain/anchor, cosign signing, HMAC task contracts, TLS in transit. Partial: no at-rest encryption/KMS (R-003). | Encryption |
| A.8.25 | Secure development life cycle | Implemented | [secure-sdlc-policy.md](policies/secure-sdlc-policy.md); PR review + CI gates + independent verification (RFC-0001a/0006). | Change-mgmt |
| A.8.26 | Application security requirements | Implemented | Signed task contracts (RFC-0002), evidence gates, standards-conformance gate (RFC-0012). | Agentic-AI |
| A.8.27 | Secure system architecture and engineering principles | Implemented | Fail-closed guards, defence-in-depth sandboxing, threat models; RFC-driven design. | Runtime |
| A.8.28 | Secure coding | Implemented | Ruff + CodeQL enforced in CI; secret scanners (`scan_secrets.py`); coder test-honesty gate (#851). Partial: scanners not a required pre-merge gate. | Change-mgmt |
| A.8.29 | Security testing in development and acceptance | Implemented | Trivy P0 gate, CodeQL, sandbox-escape corpus (`test_sandbox_escape_corpus.py`), TFactory verification. | Vuln |
| A.8.30 | Outsourced development | Not Applicable | Development is in-house/agent-driven; no outsourced development houses. Agent-produced code is treated as untrusted and independently verified (TFactory). | Agentic-AI |
| A.8.31 | Separation of development, test and production environments | Implemented | Separate branches/CI, per-task ephemeral Jobs, gitops-managed prod; note direct-to-main auto-deploy weakens the boundary (R-005). | Change-mgmt |
| A.8.32 | Change management | Implemented | PR flow, CI gates, RFC-0009 guarded auto-merge ([change-management-sod.md](policies/change-management-sod.md)). Partial: SoD/branch-protection gaps (R-005). | Change-mgmt |
| A.8.33 | Test information | Implemented | Synthetic/test data preferred over real PII ([data-classification-and-handling-policy.md](policies/data-classification-and-handling-policy.md)); test artifacts retained short (7d). | Data |
| A.8.34 | Protection of information systems during audit testing | Implemented | Read-only cluster probes for planning/feasibility; verification runs in isolated sandboxes without touching prod state. | Runtime |

## Summary

| Theme | Controls | Implemented | Planned | Not Applicable |
|---|---|---|---|---|
| A.5 Organizational | 37 | 26 | 10 | 1 |
| A.6 People | 8 | 4 | 1 | 3 |
| A.7 Physical | 14 | 0 | 2 | 12 |
| A.8 Technological | 34 | 28 | 5 | 1 |
| **Total** | **93** | **58** | **18** | **17** |

Not-Applicable controls are concentrated in A.7 (physical, provider-inherited for a
cloud-only fleet) and the employment-specific A.6 controls, each justified above. Planned
controls each trace to a Factory#310 child issue and a remediation wave in the
[README roadmap](README.md#remediation-roadmap) and the [risk register](risk-register.md).
No control is left blank.
