---
status: draft
issue: 3691
author: olafkfreund
---

# Intent: MinIO local snapshot and scheduled MinIO restore drill

## Problem

Risk R-001 (Factory#3691): the MinIO buckets `factory-artifacts` and
`factory-evidence` have no backup (versioning is not a backup), and no restore
drill is scheduled for them. A Postgres drill (`postgres-restore-drill`) and an
inert off-site mirror (`minio-backup-offsite`, needs credentials from Factory#3681)
already exist in factory-gitops `apps/backups`.

## Proposed outcome

- A nightly in-cluster snapshot of both buckets onto a separate PVC. It needs no
  external credential. It protects against deletion, overwrite and corruption of
  bucket data. It does NOT protect against loss of the node disk (one node, both
  PVCs are `local-path`); only the off-site copy does, and that stays the owner's.
- A nightly MinIO restore drill: restore a bounded sample from the snapshot into
  a scratch bucket, compare content with the source, delete the scratch objects,
  record `rto_seconds` for the whole path to `job_health` and to
  `factory-evidence`, and go red when anything is wrong.
- Tests that run in CI against the real `mc`. The runbook says what is now
  covered and what is not.

## Affected users and systems

factory-gitops `apps/backups` (new CronJobs, one PVC), OpenObserve `job_health`,
job-watchdog (watches the new CronJobs automatically), Factory
`docs/compliance/dr-runbook.md`.

## Constraints

- No new credential; reuse `minio-creds` and `observe-root`.
- No change to the live cluster by hand; Argo CD syncs from main.
- Off-site enablement (Factory#3681) is out of scope and stays inert.
- Drill never touches live objects: it writes only to a scratch bucket.

## Open questions

None. (Owner steps for off-site are listed in the PR.)
