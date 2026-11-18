---
status: draft
issue: 3807
author: olafkfreund
---

# Intent: backup CronJob failures (postgres-restore-drill, minio-backup-local)

## Problem

Two job-watchdog alerts, both about backups (Factory#3691, risk R-001):

- #3807: CronJob `factory/postgres-restore-drill` has failed every run since it
  was merged (factory-gitops#338); there has never been a success, so no
  scheduled-drill RTO is on record (the runbook has only an August manual one). The 04:15 run of 2026-11-18 reported
  `restore_failed` with problems `restore_errors_1`, `no_tables_cfactory`,
  `missing_db_factory`. The pod itself works (fetch, restore, evidence, emit all
  ran); the drill's expectations do not match the live database.
- #3806: pod `minio-backup-local-29916210-klzvj` container `copy` was
  OOMKilled (exit 137, 4 s after start) at 2026-11-18T03:30Z. The retry
  (backoffLimit 1) of the same Job passed, so the nightly snapshot exists, but
  the first attempt dies at the 512Mi limit.

## Proposed outcome

- The restore drill passes against the live dump and writes its first
  successful scheduled-drill `rto_seconds`; a drill that is genuinely wrong still fails red.
- `minio-backup-local` stays under its memory limit on the first attempt.

## Affected users and systems

factory-gitops `apps/backups/drill` and `apps/backups/minio-local`; the
`factory` namespace on k3d-factory (Argo CD syncs the change); job-watchdog
issues #3806 and #3807; Factory `docs/compliance/dr-runbook.md` (RTO record).

## Constraints

- Change only through factory-gitops PRs; cluster access is read-only.
- No secrets in the repo. Do not close #3806 or #3807 by hand (watchdog does).
- Keep `test_emit.py` and the backup-drill-test workflow green.
- Do not claim a full-path RTO; only record the drill's measured value.

## Open questions

None. Decisions taken under the owner delegation are recorded in the spec.
