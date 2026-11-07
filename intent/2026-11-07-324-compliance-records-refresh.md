---
status: draft
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
  Each changed row cites that evidence. Where the control is live, the risk is
  closed or downgraded. Where a gap remains, the row says so and names the
  tracking issue, or says that no issue tracks it.
- The SoA rows behind A1.3, CC7.5 and CC9.1 reflect measured state, and the SoA
  summary counts stay consistent.
- `soc2-gap-assessment.md` ratings are re-derived under its own rules (SoA
  ceiling, round down) from the refreshed SoA. Its summary counts, High-risk
  list and ISO summary agree with the rows.

## Affected users and systems

- Files: `docs/compliance/risk-register.md`,
  `docs/compliance/statement-of-applicability.md`,
  `docs/compliance/soc2-gap-assessment.md` in Factory.
- People: the Security Owner, who signs the residual-risk table.
- Systems are read, never changed: the k3d `factory` cluster on p620,
  factory-gitops, AIFactory, PFactory and CFactory `origin/main`, and GitHub
  issues.

## Constraints

- Read-only against the cluster. No live state changes.
- Never trust issue or document text, including the claims in this task
  request. Every new statement must cite something measured: a command output,
  a file and line on `origin/main`, or gh API state.
- An accepted risk earns no implementation credit. When in doubt, round down.
- Documentation only. No code changes, and no sign-off is filled in.
- Off-cluster backup stays open under Factory#3681.

## Open questions

- None blocking. Where a remaining gap has no open tracking issue (paging and
  the IR tabletop for R-009, keyed or expiring plan keys for R-013), the record
  says "no open issue". Opening those issues is left to the user.
