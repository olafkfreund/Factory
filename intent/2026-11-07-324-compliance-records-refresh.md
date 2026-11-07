---
status: approved
issue: 324
author: olafkfreund
---

# Intent: refresh stale compliance records (risk register, SoA, SOC 2 gap ratings)

Follow-up to Factory#324 (PR #3678, merged) under epic #310.

## Problem

Three compliance records in `docs/compliance/` describe the fleet as it was on
2026-07-24, not as it is on 2026-11-07:

- `risk-register.md` rows R-001, R-006, R-008, R-009, R-011 and R-013 still
  describe gaps whose controls have since gone live, in whole or in part. R-001
  says "No backups", but a `postgres-backup` CronJob has run nightly and a
  restore drill is recorded in `dr-runbook.md` (2026-08-10).
- `statement-of-applicability.md` still marks the backup and continuity
  controls (A.5.29, A.5.30, A.8.13) Planned.
- `soc2-gap-assessment.md` caps A1.3, CC7.5 and CC9.1 at Gap because of those
  SoA rows. Its own sign-off section says to refresh these records before anyone
  signs.

A signer would accept an exposure that is overstated in some rows. The same
records also hide which gaps still remain (no off-cluster backup copy, no paging).

## Proposed outcome

- Each of the six register rows is measured again against the live cluster
  (read-only `kubectl` on p620), `origin/main` of the repos, and the gh API.
  Each changed row cites that evidence. Each row is then re-scored against the
  threat that remains, not marked closed because some control is live. A row
  is Mitigated only when its whole treatment has landed. A partial control
  lowers the current score and leaves the rest of the gap named, with its
  tracking issue or "no open issue". Examples of partial controls: backups that
  stay on-host and leave out MinIO, Kyverno with `failurePolicy: Ignore`, and
  plan-key `kid` support that is not used in the live deployment.
- R-007 says "no versioning", which the same evidence contradicts, so its text
  is corrected. Its score is unchanged.
- SoA rows whose text the same evidence contradicts are refreshed: A.5.29,
  A.5.30 and A.8.13 (backup and continuity); A.8.16 and A.8.15 (monitoring and
  logging); A.8.8, A.5.33 and A.8.10 (CFactory scanning and the MinIO lifecycle
  rules); and the CFactory-has-no-Kyverno-rule note. The SoA summary counts stay
  consistent.
- `soc2-gap-assessment.md` ratings are re-derived under its own rules (SoA
  ceiling, round down) for every row that relies on a refreshed SoA row. That
  covers A1.3, CC7.5 and CC9.1, and also A1.2, CC7.2 and CC7.3. A row stays at
  Gap where another relied-on row is still Planned, for example CC9.1 and A1.2
  on A.8.14. Stale narrative in the rows that cite refreshed risks is corrected
  too: CC2.1, CC6.5, CC6.8, CC7.1, CC9.2 and C1.2. The summary counts,
  High-risk list, ISO summary and sign-off note agree with the rows. The
  sign-off note still claims that no issue tracks off-cluster backup, which
  Factory#3681 contradicts.
- In `dr-runbook.md`, the "Outstanding" list marks MinIO versioning done and
  points the off-box item at Factory#3681.

## Affected users and systems

- Files: `docs/compliance/risk-register.md`,
  `docs/compliance/statement-of-applicability.md`,
  `docs/compliance/soc2-gap-assessment.md`, `docs/compliance/dr-runbook.md`
  in Factory.
- People: the Security Owner, who signs the residual-risk table.
- Systems are read, never changed: the k3d `factory` cluster on p620,
  factory-gitops, AIFactory, PFactory and CFactory `origin/main`, and GitHub
  issues.

## Constraints

- Read-only against the cluster. No live state changes.
- Never trust issue or document text, including the claims in this task
  request. Every new statement must cite something measured: a command output,
  a file and line on `origin/main`, or gh API state (issue open or closed, not
  issue prose).
- The one exception is the 2026-08-10 restore drill, which cannot be measured
  again after the fact. It is cited as a dated, committed record (`dr-runbook.md`,
  commit 03c87f8 of 2026-08-10, #662), and its limits are kept: it proves the
  data restore, not a full-platform recovery.
- An accepted risk earns no implementation credit. When in doubt, round down.
- Documentation only. No code changes, and no sign-off is filled in.
- Off-cluster backup stays open under Factory#3681.

## Open questions

- None blocking. Where a remaining gap has no open tracking issue, the record
  says "no open issue". That covers paging and the IR tabletop for R-009, keyed
  or expiring plan keys for R-013, and HA for R-007. On 2026-11-07, open-issue
  searches in Factory, AIFactory and PFactory for "paging", "tabletop",
  "trusted plan key", "plan signing", "kid" and "HA postgres" found no such
  issue. Opening those issues is left to the user.
