---
status: draft
issue: 324
intent: intent/2026-11-16-324-audit-readiness.md
---

# Spec: Audit-readiness checklist, mock-audit plan, stale compliance text

## Design

1. New page `docs/compliance/audit-readiness.md`, linked from `README.md`, with:
   - **Readiness checklist.** A table, one row per assessor prerequisite: ISMS
     scope and policy set, SoA, risk register and treatment, roles, control matrix,
     SOC 2 gap assessment, residual-risk sign-off, management review held,
     independent review held, backup restore evidence, evidence collection and
     retention, vulnerability SLA and register, IR tabletop, training record,
     supplier register, NYDFS/FFIEC applicability decision, PCI scope decision.
     Columns: item, status (Ready / Open / Owner), evidence link, tracker, owner.
     Status is copied from the cited document, never rated afresh.
   - **Mock-audit plan.** It does not restate the programme in
     `management-review-and-internal-audit.md` section 2; it cites it and adds:
     the sample (one theme per framework: SoA A.8.13 backup, A.5.28 evidence,
     SOC 2 CC6 access), the evidence pull steps with existing commands, the
     independence rule, pass criteria, how findings feed the register, and the
     report template reference. The page states the audit has not been held.
2. Stale text corrected where the code or a newer document proves it:
   `data-governance.md` (outbound scrub is default on, AIFactory#1128; the
   classification policy exists), `governance-isms.md` (G1 to G4 are marked closed for the documents, G1 keeps an open note: no acknowledgement or review record, `soc2-gap-assessment.md` CC5.3;
   "Current state" is marked as the 2026-07-24 baseline), `business-continuity-policy.md`
   (daily `pg_dumpall` exists; off-cluster copy open at #3681), `roles.md` backup
   row, `README.md` wave-2 backup bullet, and SoA A.5.5 and A.5.35 tracker
   references (#3698, #3694). Redactor fail-open stays documented because it is
   still true in `llm_audit_hook.py`.
   - **Owner actions.** A section with exact commands: create the
     `evidence-github-token` secret (names only, never values), sign the
     residual-risk table, choose the mock-audit date and independent reviewer, and
     the CI scan-upload command. Decisions are labelled as decisions.
3. `tests/test_audit_readiness.py`: every relative markdown link resolves to a
   file; every backticked repo path (`docs/`, `tests/`, `scripts/`) exists; every
   tracker link matches `github.com/olafkfreund/<repo>/issues/<n>`; every row's
   status is in the allowed set. Anchors and external pages are not checked.

## Alternatives rejected

- Rewrite the SoA and SOC 2 ratings from current evidence: owner's rating call.
- Fix alerting, paging and IR text: open work under #3688; editing it would conflict.
- Wire the CI scan upload to the evidence store: needs S3 credentials in CI (owner).
- Add the mock audit to `management-review-and-internal-audit.md`: that file is
  the standing programme; a one-off plan belongs next to the checklist.

## Risks

- Checklist status can drift from the documents it cites. The test checks links,
  not meaning; each row names its source so review can compare.
- Concurrent merges touching `docs/compliance/` may conflict; rebase before push.

## Verification

- `pytest tests/test_audit_readiness.py tests/test_control_catalog.py`.
- Each corrected statement re-checked against its evidence (code line, CronJob).
- `codex review --base origin/main` and a read against `plan/`.
