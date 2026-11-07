---
status: approved
issue: 324
author: olafkfreund
---

# Intent: SOC 2 gap assessment and ISO 27001 gap summary

## Problem

Epic #324 still lists "per-framework gap assessments for ISO 27001 + SOC 2 with
residual-risk sign-off" as open. ISO 27001 already has a control-by-control view
(`docs/compliance/statement-of-applicability.md`: 93 Annex A control rows,
54 Implemented, 4 Partial (A.5.21, A.8.8, A.8.21, A.8.23), 18 Planned, 17 Not
Applicable). Its summary table is stale: it counts 58 Implemented because it
folds the 4 Partial rows in. SOC 2 has no criterion-by-criterion assessment.
What exists is domain-level: the "SOC 2 (TSC)" column in
`docs/compliance/control-matrix.md` maps each domain to criteria (some single,
like CC8.1, most ranges, like CC6.1-.3), and the risk register cites CC3.1-.4.
An assessor cannot see, per
Trust Services Criterion, what control answers it, what evidence exists, what
the gap is and what residual risk remains.

The control matrix is also stale for #324 itself. Its row says "No automated
evidence collection", and a "planned" section describes jobs that now run: the
evidence-collector CronJob (factory-gitops#74) and the access-review push
(AIFactory#1018).

## Proposed outcome

- `docs/compliance/soc2-gap-assessment.md` exists. It has one row per SOC 2 TSC
  criterion in scope (Security CC1-CC9, Availability A1, Confidentiality C1).
  Each row gives the status (Met / Partial / Gap), the control and its evidence
  pointer, the gap, and the linked risk-register ID. Risk is shown as it stands
  today (current exposure), kept apart from the register's target residual
  (the score expected after treatment) and from risks already accepted
  (AR-001, AR-002, R-014). A short ISO
  27001 section summarises the SoA counts and links to it. The SoA stays the
  ISO gap view and is not duplicated. Its stale summary table is corrected to
  the row-level counts. A residual-risk sign-off table is left
  unsigned for the Security Owner.
- The control matrix #324 rows and the "Automated evidence collection" section
  describe what runs today and name the code-scanning snapshot as blocked on a
  secret.
- The compliance README lists the new document.

## Affected users and systems

Docs only, in the Factory repo, under `docs/compliance/`. The readers are the
Security Owner (the user) and a future SOC 2 CPA or ISO assessor. No code,
manifests or cluster changes.

## Constraints

- Every Met or Partial claim cites real evidence (a file, workflow or issue)
  that already appears in the domain documents, the SoA or the risk register.
  Nothing is invented.
- The sign-off is a human deliverable. The document must not record a sign-off,
  only leave the slot for one. The slot signs off current exposure, not a
  future target.
- Scope is Security (mandatory) plus the Availability and Confidentiality
  categories. Processing Integrity is excluded on an assumption the Security
  Owner must confirm: the fleet makes no transaction-accuracy commitment to
  customers. Privacy (P-series) is deferred, not dropped:
  the control matrix maps data governance to "C1, P-series", and the PII risk
  stays visible through C1 and risk R-004 (#320). The document states both
  exclusions and their reasons, so the Security Owner can reverse them at
  sign-off.
- Readiness checklist and mock audit (#324 item c) are out of scope. A mock
  audit is a human exercise.

## Open questions

None blocking. The TSC category choice above is recorded as a decision the
Security Owner confirms or reverses at sign-off.
