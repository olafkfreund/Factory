---
status: draft
issue: 3697
intent: intent/2026-11-16-3697-framework-applicability.md
---

# Spec: Framework applicability, authority contacts, owner checklist

## Design

All edits are under `docs/compliance/` in Factory.

1. **New `framework-applicability.md`** (decision record, #3697). One table row per framework
   (SEC cyber rules, NYDFS Part 500, FFIEC, SOX ITGC): question asked, premise, decision "Not
   applicable", date 2026-11-16, decided by "owner delegation 2026-11-16 (recommended option)",
   re-scope trigger, and the action when triggered. Triggers: SEC = the operator becomes an
   SEC registrant or a public company's subsidiary that must disclose; NYDFS and FFIEC = the
   operator or a customer becomes a regulated financial firm, or a customer contract makes the
   operator its third-party service provider under 500.11 or the outsourcing booklet; SOX = the
   fleet's output or hosting is used in a public company's financial-reporting systems. A trigger
   means "review", not "applies". Each framework has its own reassessment action: SEC, review
   the Item 1.05 and risk-management disclosure duties and make the incident-response SEC row
   active; NYDFS, decide first whether the operator is itself a covered entity (all sections
   apply) or only a customer's third-party service provider (500.11 and the contract apply),
   and activate only that scope in the mapping; FFIEC, review the booklet-level mapping
   against the customer's examiner expectations; SOX, assess whether the fleet is in scope of
   the customer's financial-reporting systems and, if so, add the computer-operations ITGC
   domain, which the control matrix does not map today. Where a framework is then confirmed,
   open a gap assessment modelled on `soc2-gap-assessment.md`. The record also states the three premises, a review
   cadence (annual, and at each new customer or contract), and a premise-check table the owner
   fills (blank, with the date).
2. **README scope table** (three rows cover the four frameworks): the "Conditional" rows become "Not applicable (decided
   2026-11-16)" with a link to the record; "Next steps" item 1 is updated.
3. **`nydfs-part500-mapping.md`** (#3700): replace the "Conditional" banner by "Not applicable
   per framework-applicability.md; kept as the reference mapping if re-scoped". Every section
   gets a new "Applicability" column set to "N/A"; the existing Status column is renamed "Status
   if the Part applied" and kept as reference material. 500.19 and 500.17(b) are marked "n/a
   while not applicable". The unverified-text warning stays.
   "Done when" is rewritten to the new fact.
4. **`control-matrix.md`**: intro paragraph says the decision is made; NYDFS, FFIEC, SEC and
   SOX ITGC columns are labelled reference mappings, not in-scope claims.
5. **`policies/incident-response.md`** (#3698): the breach-notification matrix marks SEC and
   NYDFS rows "not applicable while out of scope (framework-applicability.md)"; its preamble
   (clocks start at confirmation) is corrected for GDPR, whose Art. 33 clock runs from
   awareness, and the row notes that a processor tells its controller without undue delay; and
   a new
   "Authority contact list" section holds a table: authority, when it is contacted, deadline,
   channel, contact, owner, last verified. Rows: data-protection authority (required, the
   competent authority; the owner first records jurisdiction, whether the operator is controller
   or processor, the authority and the applicable clock; the 72 hours is the controller's
   Art. 33 default), law enforcement or national CERT, hosting and platform providers
   (`supplier-management.md` identifies the providers; the owner takes incident contacts from
   provider documents or contracts), legal counsel, affected customers or controllers (per
   contract), and SEC and NYDFS rows marked "only if re-scoped". Contact cells are empty. List owner: Security Owner.
   First population due 2026-12-16 (target); review annually and on any change; next review
   due 2027-11-16.
6. **`statement-of-applicability.md`** A.5.5 cites the list and says it is Planned until the
   DPA contact is filled; no status changes.
7. **Scope wording** in `training-and-awareness.md`, `management-review-and-internal-audit.md`,
   `supplier-management.md` and `operator-endpoint-standard.md` (each cites NYDFS or the
   conditional frameworks): reworded to "reference mapping, out of scope per
   framework-applicability.md".
8. **`audit-readiness.md`** (#324, #310): rows "Authority contact list" and "Applicability"
   updated; the "Owner actions" section becomes a dated checklist of targets (labelled targets,
   checkboxes unticked) covering: confirm the three premises; evidence PAT (command, no value);
   residual-risk signature; mock-audit date and auditor (the auditor must not own the controls
   audited); first training cycle and record; first management review and minutes; supplier
   register, assurance reports and first annual re-review; endpoint attestations; authority
   contacts; the #310 owner items of 2026-11-14 not otherwise covered (offline backup of one
   agenix decrypting identity, real dates in the rotation ledger, MinIO KEK emergency test or
   risk acceptance, off-cluster backup target or risk acceptance, #3681); CI evidence-push decision; IR tabletop. Each item names the document holding the
   template and the SoA or SOC 2 row it unlocks. Target dates are 2026-11-30 to 2027-02-26
   spaced by dependency; the mock audit target is the week of 2027-01-18, after the first
   management review.

Issue handling: comments "Decision (owner delegation 2026-11-16):" on #3697, #3700, #3698,
#324 and #310. #3697 is closed as completed on merge; #3700 is closed as not planned (NYDFS not applicable), with the
retained reference mapping explained in the comment. #3698, #3693 to #3696, #3699, #324 and #310
stay open with the owner steps listed; no status in the SoA or SOC 2 is upgraded.

## Alternatives rejected

- Apply the frameworks (SEC, NYDFS, FFIEC, SOX gap assessments now): four large assessments
  against requirements nobody is subject to; rejected as cost without a trigger.
- Delete the NYDFS mapping: loses the trigger-ready reference, and #3700 asks that sections
  be mapped or marked.
- Mark the decision as the owner's confirmed fact: the premises are unverified by the
  agent, so the record states them as premises.
- Fill contact details from public sources: the DPA depends on the owner's establishment,
  which no document records; guessing would invent a fact.

## Risks

- A wrong premise makes the "not applicable" claim false. Mitigation: the premise table and
  the stated reopen rule; the owner checklist item 1 is the first one.
- Documentation drift: scope text is repeated in README, matrix, NYDFS mapping and IR
  runbook. Mitigation: each links to the single record instead of restating it.
- An assessor may read target dates as commitments. Mitigation: labelled "target".

## Verification

- `grep -rni "conditional" docs/compliance` shows no remaining open scope claim for the four.
- Link check on the touched files (relative links resolve): script in the plan.
- Repo's markdown/doc lint from CI, run locally if present.
- `codex review --base origin/main` and own read against `plan/`.
