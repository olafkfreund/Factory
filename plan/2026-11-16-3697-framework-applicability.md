---
status: draft
issue: 3697
spec: spec/2026-11-16-3697-framework-applicability.md
coders:
  1: lead (docs prose; a handoff costs more than it saves)
  2: lead
  3: lead
  4: lead
  5: lead
  6: lead
reviewers:
  - codex   # independent read-only review of each draft and the final diff; agy is off by owner decision
---

# Plan: Framework applicability, authority contacts, owner checklist (#3697, #3698, #3700, #324, #310)

Approved decisions carried from the spec (all under `docs/compliance/`, Factory only):

- SEC, NYDFS Part 500, FFIEC and SOX ITGC are recorded Not applicable, 2026-11-16, by the
  owner's delegation (recommended option), on three stated premises (operator not public;
  neither operator nor a customer a regulated financial firm; fleet does not affect anyone's
  financial reporting). A trigger means "review", not "applies"; each framework has its own
  reassessment action; NYDFS distinguishes covered entity from third-party service provider;
  SOX adds the computer-operations ITGC domain if it ever applies.
- NYDFS mapping is kept as reference with an Applicability column "N/A" on every section;
  Status column renamed "Status if the Part applied". Unverified-text warning stays.
- Authority contact list in the IR runbook: contacts empty, DPA required, owner records
  jurisdiction, controller/processor role, authority and clock; owner: Security Owner; first
  population target 2026-12-16; annual review, next 2027-11-16. Fix the GDPR clock wording.
- A.5.5 cites the list, stays Planned. No SoA or SOC 2 status is upgraded.
- Owner checklist with dated targets (not events), including the #310 owner items.
- Issue handling: decision comments on #3697, #3700, #3698, #324, #310. #3697 closed on merge;
  #3700 closed as not planned; the others stay open.

## Steps

1. `docs/compliance/framework-applicability.md` (new): decision table (framework, question,
   premise, decision, date, decided by, re-scope trigger, reassessment action), premise-check
   table (blank, owner fills), review cadence (annual and at each new customer or contract),
   owner. -> verify: file exists, links resolve.
   Traps: do not state the premises as facts; no names, contacts or events invented.
2. `docs/compliance/README.md` lines 49, 93-95 and "Next steps" item 1; the scope wording in
   `training-and-awareness.md:6`, `management-review-and-internal-audit.md:6`,
   `supplier-management.md:6`, `operator-endpoint-standard.md:7`. -> verify:
   `grep -rni conditional docs/compliance` shows no open scope claim for the four.
3. `docs/compliance/nydfs-part500-mapping.md`: banner (line 8), Applicability column on every
   section row, Status header rename, 500.17(b) and 500.19 sections marked n/a, "Done when".
   -> verify: row count of the table unchanged; every row has the column.
4. `docs/compliance/control-matrix.md` intro (lines 18-22): decision stated; NYDFS, FFIEC, SEC
   and SOX ITGC columns labelled reference mappings.
5. `docs/compliance/policies/incident-response.md`: notification matrix rows (SEC, NYDFS
   n/a while out of scope; GDPR clock from awareness; processor tells controller), preamble fix
   (line ~165), new "Authority contact list" section and a gaps/plan line;
   `docs/compliance/statement-of-applicability.md` A.5.5 (line 38) cites it, stays Planned.
   -> verify: contact cells empty; every link resolves.
6. `docs/compliance/audit-readiness.md`: update the two rows, replace "Owner actions" with the
   dated checklist (unticked boxes, targets 2026-11-30 to 2027-02-26, mock-audit week of
   2027-01-18, auditor independent of control owners, evidence-PAT command without a value,
   the #310 owner items 3-6). -> verify: each item names its template document and the row
   it unlocks.

Then: relative-link check script over touched files, `codex review --base origin/main`, own
read against this plan, push, PR, issue comments.

## Tests

- Link check: for each touched `.md`, every relative `](path)` target exists (script in step
  verification). Expected: no missing targets.
- `git diff --stat origin/main` touches only `docs/compliance/**`, `intent/`, `spec/`, `plan/`.
- Repo doc CI (markdown/pre-commit) run locally if configured; CI green on the head SHA.

## Rollback

Revert the PR. Documentation only; no runtime effect.
