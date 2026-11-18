---
status: approved
issue: 3807
intent: intent/2026-11-18-3807-backup-cronjob-failures.md
---

# Spec: backup CronJob failures

## Design

Evidence (read-only kubectl, 2026-11-18):

**#3807.** Pod `postgres-restore-drill-29916255-hc7tz`: fetch, drill and
evidence exited 0, emit exited 1 with `status=restore_failed rto_seconds=6`.
`result.json`: problems `restore_errors_1`, `no_tables_cfactory`,
`missing_db_factory`; 4 databases, 62 tables, 751 rows. I re-ran
`pg_dumpall --clean` of the live server into a local throwaway cluster:
- the one counted error is `role "myfriends" does not exist` (the dump DROPs
  every role; on a fresh cluster only `factory` exists). `drill.sh` already
  ignores this for `factory` only, so any other role trips it. Not a real
  restore failure.
- live Postgres has databases postgres, pfactory, tfactory, aifactory, cfactory,
  myfriends, myfriends_test and no `factory` database (the StatefulSet's
  `POSTGRES_DB=factory` was never applied to this PGDATA; `postgres-init`
  creates only the four service databases). `drill.sh` expects `factory`.
- live `cfactory` has 0 tables; `drill.sh` requires tables there.
The memory limit, scratch size and bash/pipefail were not the cause (drill
finished in 4 s). Rejected suspects: missing bucket object (fetch OK), credentials
(fetch and evidence OK), emit (worked as designed).

Fix in `apps/backups/drill/drill.sh`:
1. Ignore `role ".*" does not exist` (generalise the existing `role "factory"
   already exists` style filter).
2. Default `EXPECTED_DBS` = `pfactory tfactory aifactory cfactory` (drop the
   non-existent bootstrap `factory`).
3. Default `TABLE_DBS` = `pfactory tfactory aifactory`; `cfactory` must exist
   but may hold no tables (it has none live).
`test.sh` is changed to mirror production: four service databases, `cfactory`
empty, an extra role `myfriends` owning a database; expected counts updated.
This is the regression test for the failure found.

**#3806.** Pod `...klzvj` OOMKilled 4 s after start; its Job's second pod
`...crhkl` completed and the previous night's Job completed in 41 s. The
source buckets hold 4.3 GB / 1198 objects (artifacts) and 4.7 MB (evidence),
no object larger than a few MB, so object size and SSE buffering do not
explain it. `mc mirror --max-workers` defaults to "autodetect"; the node has
128 CPUs, so the autodetected worker count (upstream caps it at 128, each worker buffering parts) is
host-sized. This is the working hypothesis, not proven; the pinned image's
behaviour was only checked for the flag's existence. Four workers is the mitigation. Decision (owner
delegation 2026-11-18): reduce parallelism first: `mc mirror --max-workers 4`
in `minio-local.sh`; keep the 512Mi limit. Measured need is not available
(metrics-server samples only running pods, the OOM pod is gone); if it recurs
after this change, raise the limit then.

## Alternatives rejected

- Raise the memory limit to 1Gi: masks the unbounded worker count.
- Make the drill tolerant by removing the table/db checks: loses the signal.
- Create the `factory` database in live Postgres: a live change outside GitOps.
- Cap `mc mirror` in `minio-offsite` / `offsite` too: same pattern, but not in
  a watchdog alert; left for a follow-up if they alert.

## Risks

The drill is looser on `cfactory` content and on non-bootstrap role drops; both
are properties of this cluster, and the total `no_rows` check cannot see lost cfactory content while other
databases hold rows. Suppressing every `role ... does not exist` also hides it for
ALTER/GRANT lines, but a failed CREATE ROLE still reports a different, counted error.
`--max-workers 4` makes the snapshot slower (53 s today; the 3600 s deadline is
far away).

## Verification

`apps/backups/drill/test.sh` (in the pinned postgres image as non-root),
`test_emit.py`, `apps/backups/minio-local/test.sh`, the repo's CI. After merge
and sync, the 04:15 UTC drill passes and job-watchdog closes #3807; #3806 closes
after 24 h without recurrence. Do not trigger either by hand.
