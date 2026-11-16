---
status: draft
issue: 3693
intent: intent/2026-11-16-3693-governance-operating-records.md
---

# Spec: Governance operating procedures and mappings

## Design

Five new documents in `docs/compliance/`, each in the style of the existing
control documents (owner, cadence and framework header; policy statements;
records; evidence), plus edits to six existing files.

| New file | Issue | Content |
|---|---|---|
| `training-and-awareness.md` | #3693 | Audience (everyone with fleet access, including agent-operating humans), curriculum drawn from the policy set, annual cadence plus on-joining and after a Sev-1, screening statement for a one-operator fleet, blank completion record |
| `management-review-and-internal-audit.md` | #3694 | Quarterly management-review procedure and blank minute template; internal-audit programme (scope by SoA theme over a rolling year, annual cadence, independence rule, findings into the risk register and SLA); blank audit report template; a recorded mock audit (#324) may count as the first audit only if recorded as one |
| `supplier-management.md` | #3695 | Vendor and sub-processor register (LLM providers, GitHub, Cloudflare, hosting, Ollama local) with columns for data processed, processor terms in force, assurance report and last review, each "owner to record"; an owner checklist to obtain, evaluate and reference each provider's processor terms and assurance report (SOC 2 or ISO certificate), where an unobtainable item stays a recorded gap with a compensating note; processor-terms checklist; annual re-review procedure and blank record |
| `operator-endpoint-standard.md` | #3696 | Requirements (full-disk encryption, screen lock timeout, patching, key-material location, MFA on GitHub, loss/theft handling), evidence source per requirement (NixOS configuration where it sets it, with the file and option to cite), blank per-host attestation that must attach the evidence, not only a signature |
| `nydfs-part500-mapping.md` | #3700 | Every section 500.1 to 500.24 mapped to a control, or marked administrative (definitions, confidentiality, enforcement, dates, severability) or exemption; conditional banner referencing #3697 with two cases (the operator is a covered entity; a customer is, so the operator answers under 500.11 only) and whose controls and officers each mapping row concerns; 500.19 exemption criteria with an owner determination field; 500.17(b): the annual submission is due April 15 for the prior calendar year as either a certification of material compliance or an acknowledgment of noncompliance (deficiencies and remediation timeline), signed by the highest-ranking executive and the CISO, with supporting records kept five years. Both blank forms are provided, with a rule that known open gaps in the mapping route to the acknowledgment form, not the certification. The CISO is the Security Owner under `roles.md`; the highest-ranking executive is for the owner to name |

Edits: `policies/information-security-policy.md` gets a measurable-objectives
table (objective, measure, target, source, frequency; no current values);
`risk-register.md` gets R-017 fraud risk (agent or operator falsifying
verification evidence or the audit trail; controls: audit hash-chain with daily
signed anchor, TFactory independent verification, signed task contracts; gap:
agents authenticate as the operator per `agent-identity.md`); `roles.md` links
the review and audit procedures; `statement-of-applicability.md`,
`soc2-gap-assessment.md`, `control-matrix.md` and `README.md` cite the new
documents.

Status rule: rows stay Planned/Gap. Each cites the procedure and states which
record the owner must produce before the row can be reassessed; a dated
record alone does not flip a whole criterion, the assessor re-reads it against
the criterion.

### Completion per issue (the owner's, not this PR's)

- #3693: a dated completion record exists for the first training cycle; then
  A.6.3 and CC1.4 cite it.
- #3694: the first management review is minuted and the first internal audit
  (or a mock audit recorded as one) is reported; then CC1.2, CC4.2 and A.5.35
  cite the dated records.
- #3695: provider processor terms and assurance reports are collected or
  recorded as gaps, the register is published, and the first annual re-review
  is recorded; then A.5.20, A.5.22 and CC9.2 cite them.
- #3696: each operator host has an attestation with evidence attached; then
  A.8.1, A.7.7 and A.7.9 cite the standard and the evidence.
- #3699: objectives and R-017 are merged, and the owner reviews the objectives'
  targets; CC3.1 and CC3.3 then cite them. This PR delivers the documents, the
  owner's acceptance of the targets is the remaining step.
- #3700: the mapping is merged and #3697 is decided; if NYDFS does not apply
  the owner closes the issue as not planned.

NYDFS statuses are the fleet's existing evidence applied to the section, with
gaps named (for example 500.5 annual penetration testing against accepted risk
R-015, and 500.12 MFA against R-010).

The training and management-review documents describe screening for a
one-operator fleet as not applicable with the A.6.1 reason, re-scoped if
employment begins.

## Alternatives rejected

- One combined governance document: harder to cite per criterion.
- Upgrading SoA rows to Implemented on the strength of procedures: the
  assessor tests operation, and `soc2-gap-assessment.md` already rules that
  policy alone is not credit.
- Creating empty `records/` files per period: an empty record reads as
  evidence of a skipped event; templates live in the procedures instead.
- Deciding NYDFS applicability: the owner's call (#3697).
- Stopping the NYDFS inventory at 500.23: the Part runs to 500.24 (exemptions
  from electronic filing), so a whole-Part claim would be false.

## Risks

- A template read as a completed record: mitigated by empty fields and a
  header line "TEMPLATE: not a record".
- Cited paths drifting: verification checks every link and cited path exists.
- NYDFS regulation text summarised from memory: each row carries "verify
  against current 23 NYCRR 500 text before reliance", and the review step
  checks 500.17(b), 500.19 and 500.24 against the DFS published rule.

## Verification

Link and path check script over the touched files; grep that no new file
contains a filled date or signature; the repo's docs check if CI has one;
read-through against the SoA and SOC 2 rows; an independent review that checks
each new document against its issue's "Do" list and the NYDFS rows against the
current rule.
