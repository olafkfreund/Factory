# NYDFS 23 NYCRR Part 500: Control Mapping

- **Owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** Annually, and when [#3697](https://github.com/olafkfreund/Factory/issues/3697) is decided
- **Framework:** New York DFS Cybersecurity Regulation, 23 NYCRR Part 500
- **Issue:** Factory#3700

> **Conditional.** Whether Part 500 applies is the owner's decision in Factory#3697 and
> is not made here. If the answer is that it does not apply, this document is withdrawn
> and #3700 is closed as not planned. Section summaries below are written from memory
> of the 2023 amendment and every row must be checked against the current rule text
> (https://www.dfs.ny.gov/industry_guidance/cybersecurity/23_nycrr_part_500) before
> anyone relies on it.

## Two cases

Part 500 can reach the fleet in two different ways, and a row means something different
in each:

1. **The operator is a covered entity** (it operates under a license, registration or
   charter under the New York Banking, Insurance or Financial Services Law). Every
   section binds the operator directly, and the officers in 500.17(b) are the
   operator's.
2. **A customer is a covered entity and the operator is its third-party service
   provider.** The customer's duties pass to the operator only through 500.11 and the
   contract. Rows other than 500.11 describe the customer's duties, and the fleet's
   controls are what the customer would rely on.

Rows say which fleet control would answer each section. "Gap" means the control the
section needs is not in place today.

## Section mapping

| Section | Requirement (short) | Fleet control | Status | Gap or issue |
|---|---|---|---|---|
| 500.1 | Definitions | Administrative | n/a | |
| 500.2 | Cybersecurity program | [Information Security Policy](policies/information-security-policy.md), [governance-isms.md](policies/governance-isms.md), [control matrix](control-matrix.md) | Partial | Management review not yet held (Factory#3694) |
| 500.3 | Cybersecurity policy | [Policy set](policies/index.md), approved by Security Owner | Partial | Board or senior-officer approval, not held (case 1) |
| 500.4 | CISO and governance; report to the board at least annually (500.4(b)) | Security Owner is the CISO function ([roles.md](roles.md)); [management review](management-review-and-internal-audit.md) | Gap | Report to governing body not produced; no deputy named |
| 500.5 | Penetration testing (annual) and vulnerability management | CodeQL, Trivy P0 gate, Dependabot, [vulnerability-register.md](vulnerability-register.md) | Gap | No external pen test: accepted risk R-015 / AR-002 contradicts an annual test requirement if Part 500 applies |
| 500.6 | Audit trail | HMAC audit hash-chain, daily anchor, SIEM forward ([audit-logging.md](policies/audit-logging.md)) | Partial | Retention floor vs ILM (Factory#3692) |
| 500.7 | Access privileges and management | [access-control-policy.md](policies/access-control-policy.md), [iam-access-control.md](policies/iam-access-control.md), [operator-endpoint-standard.md](operator-endpoint-standard.md) | Partial | Wildcard `APP_API_TOKEN` (R-002, Factory#312) |
| 500.8 | Application security | [secure-sdlc-policy.md](policies/secure-sdlc-policy.md): PR review, CodeQL, Trivy, gitleaks, signed provenance; independent TFactory verification | Partial | Annual review of the written procedures and the in-house applications' security is not recorded |
| 500.9 | Risk assessment (periodic, documented) | [risk-register.md](risk-register.md) methodology and quarterly review | Partial | Review not yet recorded (Factory#3694); written assessment sign-off |
| 500.10 | Cybersecurity personnel and intelligence | Security Owner named in [roles.md](roles.md); [training-and-awareness.md](training-and-awareness.md) | Gap | No qualified-personnel record, no threat-intelligence intake defined, no recorded training (Factory#3693) |
| 500.11 | Third-party service provider security policy | [vendor-and-third-party-policy.md](policies/vendor-and-third-party-policy.md), [supplier-management.md](supplier-management.md) | Partial | Register and terms not recorded (Factory#3695); the only section that binds in case 2 |
| 500.12 | Multi-factor authentication | Keycloak SSO with GitHub upstream | Gap | MFA not enforced at the IdP (R-010, Factory#312) |
| 500.13 | Asset management and data retention | [data-governance.md](policies/data-governance.md), classification policy | Partial | No asset inventory register (SoA A.5.9) |
| 500.14 | Monitoring and training | Audit-chain alert, `audit-siem-forward`; [training-and-awareness.md](training-and-awareness.md) | Gap | No paging, no recorded training (Factory#3688, #3693) |
| 500.15 | Encryption of nonpublic information | [encryption-key-mgmt.md](policies/encryption-key-mgmt.md) | Partial | Postgres at rest accepted R-014 |
| 500.16 | Incident response and business continuity and disaster recovery plans | [incident-response.md](policies/incident-response.md), [business-continuity-dr.md](policies/business-continuity-dr.md), [dr-runbook.md](dr-runbook.md) | Partial | Runbook untested (Factory#3688); no off-cluster copy (Factory#3681) |
| 500.17(a) | Notice of a cybersecurity event within 72 hours | [incident-response.md](policies/incident-response.md) | Partial | No authority contact list (Factory#3698) |
| 500.17(b) | Annual submission by April 15 | See below | Gap | No certification process held |
| 500.18 | Confidentiality of information provided to the department | Administrative | n/a | |
| 500.19 | Exemptions | See below | Not decided | Owner's determination |
| 500.20 | Enforcement | Administrative | n/a | |
| 500.21 | Effective date | Administrative | n/a | |
| 500.22 | Transitional periods | Administrative | n/a | Check which transition dates have passed |
| 500.23 | Severability | Administrative | n/a | |
| 500.24 | Exemptions from electronic filing | Exemption | n/a | Only if the owner has to file |

Every row: verify against the current rule before reliance.

## 500.17(b): the annual submission

Part 500.17(b) requires, by April 15 each year, for the prior calendar year, either:

- a **certification of material compliance** with the regulation, or
- an **acknowledgment of noncompliance**, identifying the sections not complied with,
  the reasons, and a timeline for remediation.

Both are signed by the **highest-ranking executive** and the **CISO**. The supporting
records are kept five years. In this fleet the CISO function is the Security Owner
(`roles.md`). The highest-ranking executive is for the owner to name. While one person
holds both roles the submission records that, and the signatures stay two lines.

Rule for the preparer: any row above with status Gap or Partial is an open deficiency,
so the submission is the **acknowledgment of noncompliance** unless the Security Owner
has closed each such row and keeps the evidence. The mapping never leads mechanically
to a certification.

> TEMPLATE: not a record. Leave every field empty until the submission is made.

| Field | Certification of material compliance | Acknowledgment of noncompliance |
|---|---|---|
| Calendar year covered | | |
| Sections and deficiencies | | |
| Remediation timeline | | |
| Evidence retained (location) | | |
| Date submitted | | |
| Highest-ranking executive (name, signature) | | |
| CISO (name, signature) | | |

## 500.19: exemptions

500.19 gives limited exemptions by size and some other categories (for example based on
number of employees and contractors, gross annual revenue, and year-end total assets,
or being fully covered by a parent's program). The thresholds change and must be taken
from the current rule. The determination is the owner's, recorded in #3697:

| Field | Value |
|---|---|
| Exemption claimed (category, thresholds) | |
| Facts and figures relied on | |
| Date determined | |
| Determined by | |
| Notice of exemption filed (date) | |

If an exemption applies, the sections it excuses are marked exempt in the table above.
The exemption does not cover every section: check the current rule for which ones
still apply.

## Done when

Every Part 500 section is mapped, marked administrative, or marked exempt in the
table above, and #3697 is decided. This document delivers the mapping only.
