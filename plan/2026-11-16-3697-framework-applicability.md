---
status: approved
issue: 3697
spec: spec/2026-11-16-3697-framework-applicability.md
coders:  # lead does every step: docs prose, a handoff costs more than it saves
  1: lead
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
- Triggers (each means "review"): SEC, operator becomes an SEC registrant or a public
  company's disclosing subsidiary; NYDFS and FFIEC, operator or a customer becomes a regulated
  financial firm, or a customer contract makes the operator its third-party service provider
  (500.11, outsourcing booklet); SOX, fleet output or hosting is used in a public company's
  financial-reporting systems. Reassessment actions: SEC, review Item 1.05 and risk-management
  disclosure duties and activate the SEC row; NYDFS, decide covered entity (all sections) or
  third-party provider (500.11 and contract), activate only that scope; FFIEC, review the
  booklet mapping against the customer's examiner expectations; SOX, assess scope and, if in,
  add the computer-operations ITGC domain. A confirmed framework gets a gap assessment modelled
  on `soc2-gap-assessment.md`.
- Authority contact list in the IR runbook: contacts empty, DPA required, owner records
  jurisdiction, controller/processor role, authority and clock; owner: Security Owner; first
  population target 2026-12-16; annual review, next 2027-11-16. Fix the GDPR clock wording.
- A.5.5 cites the list, stays Planned. No SoA or SOC 2 status is upgraded.
- Contact table columns: authority, when contacted, deadline, channel, contact, owner, last
  verified. Rows: data-protection authority (required; the owner first records jurisdiction,
  controller or processor role, competent authority, clock; 72 hours is the controller's
  Art. 33 default), law enforcement or national CERT, hosting and platform providers (GitHub,
  Cloudflare, LLM providers: `supplier-management.md` names them, the owner takes incident
  contacts from provider documents or contracts), legal counsel, affected customers or
  controllers (per contract), SEC and NYDFS ("only if re-scoped"). Review on any change.
- Owner checklist with dated targets (not events): confirm the three premises; evidence PAT;
  residual-risk signature; mock-audit date and auditor (independent of control owners; the
  week of 2027-01-18, after the first management review); first training cycle and record;
  first management review and minutes; supplier register, assurance reports, first annual
  re-review; endpoint attestations; authority contacts; CI evidence-push decision; IR
  tabletop; and the #310 items: offline backup of one agenix identity, real dates in the
  rotation ledger, MinIO KEK emergency test or risk acceptance, off-cluster backup target or
  risk acceptance (#3681). Each item names its template document and the row it unlocks.
- Issue handling: decision comments on #3697, #3700, #3698, #324, #310. #3697 closed on merge;
  #3700 closed as not planned with a comment explaining the retained reference mapping; #3693 to
  #3696, #3698, #3699, #324 and #310 stay open with owner steps listed. Every comment starts
  "Decision (owner delegation 2026-11-16):" where it records a decision.

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
3. `docs/compliance/nydfs-part500-mapping.md`: banner (line 8), table (lines 34-61) Applicability column on every
   section row, Status header rename, 500.17(b) and 500.19 sections marked n/a, "Done when".
   -> verify: row count of the table unchanged; every row has the column.
4. `docs/compliance/control-matrix.md` intro (lines 18-22) and table header (line 26): decision
   stated; NYDFS, FFIEC, SEC and SOX ITGC columns labelled "(reference)". -> verify:
   `grep -c "(reference)" docs/compliance/control-matrix.md` is at least 1 and the table has
   the same number of rows as on main (`git diff --stat` shows only header/intro changes).
5. `docs/compliance/policies/incident-response.md`: notification matrix rows (SEC, NYDFS
   n/a while out of scope; GDPR clock from awareness; processor tells controller), preamble fix
   (line ~165) and matrix rows (lines 168-175), new "Authority contact list" section and a gaps/plan line;
   `docs/compliance/statement-of-applicability.md` A.5.5 (line 38) cites it, stays Planned.
   -> verify: contact cells empty; every link resolves.
6. `docs/compliance/audit-readiness.md`: update the two rows (lines 30-31), mock-audit text
   (stays), and "Owner actions" (lines 66-81), replace "Owner actions" with the
   dated checklist (unticked boxes, targets 2026-11-30 to 2027-02-26, mock-audit week of
   2027-01-18, auditor independent of control owners, evidence-PAT command without a value,
   the #310 owner items 3-6). -> verify: each item names its template document and the row
   it unlocks.

Then: relative-link check script over touched files, `codex review --base origin/main`, own
read against this plan, push, PR, issue comments.

## Tests

- Link check, run from the repo root; expected output empty:
  `for f in $(git diff --name-only origin/main -- 'docs/compliance/*.md' 'docs/compliance/policies/*.md'); do d=$(dirname $f); grep -o '](\([^)#:]*\.md\)' $f | sed 's/^](//;s/)$//' | while read l; do [ -e "$d/$l" ] || echo "$f -> $l"; done; done`
- NYDFS rows: `grep -c '^| 500\.' docs/compliance/nydfs-part500-mapping.md` equals the count on
  main (25); every such row contains "N/A".
- No Markdown linter is configured (pre-commit has gitleaks only); gitleaks passes.
- `git diff --stat origin/main` touches only `docs/compliance/**`, `intent/`, `spec/`, `plan/`.
- Repo doc CI (markdown/pre-commit) run locally if configured; CI green on the head SHA.

## Rollback

Revert the PR. Documentation only; no runtime effect.
