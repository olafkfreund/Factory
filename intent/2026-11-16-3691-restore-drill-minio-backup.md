---
status: approved
issue: 3691
author: olafkfreund
---

# Intent: Scheduled restore drill and MinIO backup (R-001)

## Problem

Risk R-001 sits at 10 (target 5). Three gaps remain after #321:

- The MinIO buckets `factory-artifacts` and `factory-evidence` have no backup.
  Versioning is on, but versioning is not a backup.
- The only restore drill is the manual one of 2026-08-10 in
  `docs/compliance/dr-runbook.md`. Nothing schedules another, so the evidence
  has an expiry date nobody tracks.
- That drill timed the data-restore step (17s), not the full path
  (fetch, stand up a database, restore, validate).

## Proposed outcome

- A CronJob in factory-gitops restores the newest `postgres-backup` dump into a
  throwaway Postgres (inside the Job pod, never the live database), runs
  integrity checks, measures the full-path time, writes the result to the
  `job_health` stream and to `factory-evidence`, and leaves nothing behind.
  It fails red when the restore or a check fails. `job-watchdog` covers it like
  every other CronJob (failure, staleness, never-succeeded).
- A MinIO bucket backup CronJob exists in factory-gitops, committed but not
  deployed, mirroring the same way the Postgres off-site copy landed in
  factory-gitops#333. It uses the same off-site Secret as #3681.
- `docs/compliance/dr-runbook.md` states what is now covered, how to read the
  drill result, the full-path RTO method, and what the owner still has to do.

## Affected users and systems

factory-gitops (`apps/backups`, new CronJobs, one CI test), Factory
(`docs/compliance/dr-runbook.md`, these artifacts). The owner for the off-site
target. No change to the live Postgres, MinIO or any application.

## Constraints

- No live cluster change from this work; Argo CD syncs the drill after merge.
- No new credential for the drill: it reuses `minio-creds` and `observe-root`.
- The MinIO backup never deletes or overwrites at the destination.
- The off-site S3 target itself (#3681) is an owner action and out of scope.
- Do not claim a full-path RTO number that was not measured on the cluster.

## Open questions

None. (Owner actions: provide the off-site S3 target and the
`offsite-s3-creds` Secret, then enable the MinIO backup.)
