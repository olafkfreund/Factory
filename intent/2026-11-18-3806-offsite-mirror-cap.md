---
status: approved
issue: 3806
author: olafkfreund
---

# Intent: cap mc mirror parallelism in the offsite backup scripts

## Problem

Factory#3806: `minio-backup-local` was OOMKilled at 512Mi because `mc mirror` autodetects its worker count from the host CPUs (128 on the node). factory-gitops#374 capped only that script (`--max-workers 4`). The offsite scripts (`apps/backups/minio-offsite/minio-offsite.sh`, `apps/backups/offsite/offsite-copy.sh`) call `mc mirror` uncapped and would hit the same limit once the owner enables offsite.

## Proposed outcome

Every `mc mirror` call in `apps/backups` carries `--max-workers "$MC_MAX_WORKERS"` (default 4, overridable), tests fail if one does not, and #3806 has closeout evidence.

## Affected users and systems

factory-gitops `apps/backups` (offsite CronJobs are not in the kustomization, so nothing deploys). Owner enabling offsite later.

## Constraints

- Keep CronJob memory limits (owner decision on #3806: reduce parallelism first, raise limits only with a measured value).
- Do not add `../offsite` or `../minio-offsite` to the kustomization.
- Do not close #3806 by hand; the job-watchdog closes it after 24 h without recurrence.

## Open questions

None. Closeout: the cluster was recreated at 10:54 UTC on 2026-11-18, so `minio-backup-local` has no run since the fix yet (next 03:30 UTC); evidence is the deployed script and the next run.
