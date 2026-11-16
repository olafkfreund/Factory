# Management Review and Internal Audit Programme

- **Policy owner:** Security Owner (CISO function) — see [roles.md](roles.md)
- **Review cadence:** Management review quarterly; internal audit annually
- **Frameworks:** ISO/IEC 27001:2022 Clause 9.2 (internal audit), 9.3 (management review),
  A.5.35; SOC 2 CC1.2, CC4.1, CC4.2; NYDFS 500.4(b) (reference only, not applicable: see
  [framework-applicability.md](framework-applicability.md)); FFIEC management and audit booklets
- **Issue:** Factory#3694

This document is the procedure and the templates. It is not a record: no review or audit
is claimed here. CC1.2, CC4.2 and A.5.35 stay Gap/Planned until the Security Owner holds
the first review and the first audit and files the dated records.

## 1. Management review (Clause 9.3)

The Security Owner chairs it quarterly and after any Sev-1 incident. The standing agenda
is in [roles.md](roles.md) (risk register, incidents, control effectiveness from the
continuous-monitoring signals, audit findings, policy exceptions, scope changes,
resourcing), plus these fixed inputs each time:

- the [security objectives](policies/information-security-policy.md) with their measured values;
- the open items in [risk-register.md](risk-register.md), including accepted risks nearing review;
- status of the previous review's actions and of any audit findings;
- the supplier [register](supplier-management.md) and training status.

Minutes go to `docs/compliance/management-review/YYYY-QN.md` (create with the first
review), committed through a pull request so git history dates it. A review with a
single attendee is minuted as such; it is not treated as independent oversight.

### Minute template

> TEMPLATE: not a record. Leave every field empty until the review has happened.

| Field | Value |
|---|---|
| Period (YYYY-QN) | |
| Date held | |
| Chair | |
| Attendees | |
| Inputs reviewed (list) | |
| Decisions (with risk acceptances) | |
| Actions (owner, due date) | |
| Previous actions status | |
| Next review date | |
| Minuted by | |
| Signature | |

## 2. Internal audit programme (Clause 9.2)

**Scope.** All of the ISMS over a rolling twelve months: Clauses 4 to 10 and the Annex A
themes (A.5 organizational, A.6 people, A.7 physical, A.8 technological) as recorded in
the [SoA](statement-of-applicability.md), plus the SOC 2 criteria in the
[gap assessment](soc2-gap-assessment.md). The programme names which themes are audited in
which quarter before the year starts; each quarter covers one theme and its operating
evidence (not only configuration), and a theme with a Planned row is audited for the
plan's progress.

**Cadence.** An annual cycle; each audit produces a report within 30 days of fieldwork.

**Independence.** The auditor must not own, or have operated, the controls audited. The
fleet has one Security Owner who holds every domain, so the Security Owner cannot audit
their own domains. The audit is performed by someone else: a peer maintainer, an external
reviewer, or a certification or SOC 2 readiness assessor. The report names the auditor
and states why they are independent. A self-review is recorded as a self-review and does
not satisfy A.5.35.

**First audit.** The "readiness checklist + mock audit" item under Factory#324 counts as
the first audit only if it is held and recorded as an internal audit under this section,
with a report in the template below.

**Findings.** Each finding gets an id, a severity, an owner and a due date under
[remediation-sla.md](remediation-sla.md), goes into the [risk register](risk-register.md)
if it is a risk, and is reviewed at the next management review until closed.

### Audit report template

> TEMPLATE: not a record. Leave every field empty until the audit has happened.

| Field | Value |
|---|---|
| Audit id and theme | |
| Scope and period | |
| Auditor and basis of independence | |
| Fieldwork dates | |
| Evidence examined | |
| Findings (id, severity, owner, due date) | |
| Conclusion | |
| Report date | |
| Auditor signature | |
| Security Owner response and signature | |

## 3. Evidence and what flips the rows

| Row | The owner must produce | Then reassess |
|---|---|---|
| SOC 2 CC1.2 | The first dated, minuted review | An assessor re-reads it against the criterion |
| SOC 2 CC4.2 | The first audit report with findings communicated to management | Same |
| SoA A.5.35 | The first independent audit report | Same |
| ISO Clause 9.2 / 9.3 | The programme above plus both records | Same |
