---
status: draft
issue: 3697
author: olafkfreund
---

# Intent: Record framework applicability, authority contacts and the owner checklist (#3697, #3698, #3700, #324, #310)

## Problem

Governance records for #3693 to #3696 and #3699 are merged (PR #3726) as procedures and blank
templates. What is still open in the #310 programme:

- #3697: SEC, NYDFS Part 500, FFIEC and SOX ITGC still read "Conditional" in
  `docs/compliance/README.md`. No decision is recorded, so #3700's NYDFS mapping is
  "conditional" and the control matrix says the decision is open.
- #3698: SoA A.5.5 is Planned. There is no authority-contact list, so the 72-hour and
  4-business-day clocks in `policies/incident-response.md` have no named channel or owner.
- #324 / #310: the owner-only steps (evidence PAT, residual-risk signature, mock-audit date and
  auditor, first training, first management review, supplier register, endpoint attestations)
  are scattered across documents, with no dated checklist.

## Proposed outcome

- A decision record for the four conditional frameworks, dated 2026-11-16, taking the
  recommendation of #3697 (not applicable to a non-regulated single-operator platform) with the
  trigger conditions that would make each applicable and what to do then.
- README scope table, control matrix and NYDFS mapping state the decision; the NYDFS mapping
  keeps every section mapped or marked, now as "not applicable, reference mapping".
- An authority-contact list in the IR runbook with owner, review date and blank contact fields.
- `audit-readiness.md` carries one dated owner checklist covering every attestation.
- No document claims an event happened. No SoA or SOC 2 status is upgraded by this change except
  that A.5.5 cites the list (it stays Planned until contacts are filled).

## Affected users and systems

Documentation under `docs/compliance/` in Factory only. The owner (Security Owner) is the only
person with actions.

## Constraints

- The decision rests on two premises the owner must confirm: the operator is not a public
  company and no customer or the operator is a regulated financial firm. They are stated as
  premises, not as verified facts.
- No invented events, names, contacts or dates of events. Target dates are labelled targets.
- Secrets (the evidence PAT) are never handled; the checklist gives the command only.
- Approve-unseen bulk run: owner approval in advance, 2026-11-16.

## Open questions

None. Delegated decision: take the recorded recommendation (not applicable, with triggers).
