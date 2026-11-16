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
   fleet's output or hosting is used in a public company's financial-reporting systems. When
   triggered: open a gap assessment modelled on `soc2-gap-assessment.md`, restore the
   nydfs mapping to active scope, and for SOX add the computer-operations ITGC domain, which
   the control matrix does not map today. The record also states the three premises, a review
   cadence (annual, and at each new customer or contract), and a premise-check table the owner
   fills (blank, with the date).
2. **README scope table**: the four "Conditional" rows become "Not applicable (decided
   2026-11-16)" with a link to the record; "Next steps" item 1 is updated.
3. **`nydfs-part500-mapping.md`** (#3700): replace the "Conditional" banner by "Not applicable
   per framework-applicability.md; kept as the reference mapping if re-scoped". Every section
   status gets the note that the table describes the case where the Part applies; 500.19 and
   500.17(b) are marked "n/a while not applicable". The unverified-text warning stays.
   "Done when" is rewritten to the new fact.
4. **`control-matrix.md`**: intro paragraph says the decision is made; NYDFS, FFIEC, SEC and
   SOX ITGC columns are labelled reference mappings, not in-scope claims.
5. **`policies/incident-response.md`** (#3698): the breach-notification matrix marks SEC and
   NYDFS rows "not applicable while out of scope (framework-applicability.md)", and a new
   "Authority contact list" section holds a table: authority, when it is contacted, deadline,
   channel, contact, owner, last verified. Rows: data-protection authority (required, the
   lead authority for the establishment, deadline 72 hours), law enforcement or national CERT,
   hosting and platform providers (GitHub, Cloudflare, LLM providers: contacts come from
   `supplier-management.md`), legal counsel, affected customers (per contract), and SEC and
   NYDFS rows marked "only if re-scoped". Contact cells are empty. List owner: Security Owner.
   First population due 2026-12-16 (target); review annually and on any change; next review
   due 2027-11-16.
6. **`statement-of-applicability.md`** A.5.5 cites the list and says it is Planned until the
   DPA contact is filled; no status changes.
7. **`audit-readiness.md`** (#324, #310): rows "Authority contact list" and "Applicability"
   updated; the "Owner actions" section becomes a dated checklist of targets (labelled targets,
   checkboxes unticked) covering: confirm the three premises; evidence PAT (command, no value);
   residual-risk signature; mock-audit date and auditor (the auditor must not own the controls
   audited); first training cycle and record; first management review and minutes; supplier
   register, assurance reports and first annual re-review; endpoint attestations; authority
   contacts; CI evidence-push decision; IR tabletop. Each item names the document holding the
   template and the SoA or SOC 2 row it unlocks. Target dates are 2026-11-30 to 2027-02-26
   spaced by dependency; the mock audit target is the week of 2027-01-18, after the first
   management review.

Issue handling: comments "Decision (owner delegation 2026-11-16):" on #3697, #3700, #3698,
#324 and #310. #3697 and #3700 are done on merge. #3698, #3693 to #3696, #3699, #324 and #310
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

- `grep -rn "Conditional" docs/compliance` shows no remaining open scope claim for the four.
- Link check on the touched files (relative links resolve): script in the plan.
- Repo's markdown/doc lint from CI, run locally if present.
- `codex review --base origin/main` and own read against `plan/`.
