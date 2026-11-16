---
status: approved
issue: 3691
intent: intent/2026-11-16-3691-restore-drill-minio-backup.md
---

# Spec: Scheduled restore drill and MinIO backup (R-001)

## Design

All code is in factory-gitops under `apps/backups/`; Factory holds the
artifacts and the runbook.

**Restore drill** (`apps/backups/drill/`, deployed: added to
`apps/backups/manifests/kustomization.yaml`). CronJob `postgres-restore-drill`,
daily `15 4 * * *` (after the 02:15 dump and the 03:15 off-site copy), same
hardening as `postgres-backup` (non-root, read-only rootfs, caps dropped,
`restartPolicy: Never`, `backoffLimit: 0` so one night is one record, history
limits 3/10, no TTL, `activeDeadlineSeconds`).
One pod, four steps, throwaway state in an `emptyDir`:

1. `fetch` (mc image): write `t0`, find the newest `factory-cluster-*.sql.gz`
   with `mc find | sort | tail -1` (names sort in time order; `mc find` is
   unordered), copy it. It never fails the pod: on any failure (no dump, MinIO
   unreachable) it writes a not-ok `result.json` (`no_dump_found`,
   `fetch_failed`) so steps 3 and 4 still run and report.
2. `drill` (postgres image, `drill.sh`): skips if fetch failed. Rejects the
   dump if it is not valid gzip, empty, older than 25h (`dump_stale`),
   future-dated, or lacks the `pg_dumpall` end marker (`dump_incomplete`:
   a cut-short but well-formed gzip passes `gzip -t`). Then `initdb -U factory`
   (same bootstrap role as production); start Postgres on a unix socket in the
   scratch dir (no network listener, cannot touch or be reached from the live
   cluster); replay the dump with `ON_ERROR_STOP=0`. On a fresh cluster the
   `--clean` dump always produces three benign errors (DROP DATABASE of a
   database that does not exist yet, DROP ROLE of the current user, CREATE
   ROLE of the existing bootstrap role); those three patterns are excluded and
   every other `ERROR`, `FATAL`, `PANIC` or `invalid command` line counts against
   `MAX_RESTORE_ERRORS` (0). Then check the
   artefact, not the exit code: every expected database exists
   (`pfactory tfactory aifactory cfactory factory`), the four service databases
   each have at least one user table (the bootstrap `factory` database may be
   empty), the cluster has rows, row counts are read per database and recorded, `pg_dump -s`
   succeeds per database. It always writes `result.json`, exits 0, and removes the throwaway cluster
   and the dump from the scratch volume so nothing big stays on the node while
   the finished pod is kept.
3. `evidence` (mc image): upload `result.json` to
   `factory-evidence/control-plane-push/restore-drill/<UTC>.json` (the
   existing evidence layout, existing `minio-creds`). A failed upload leaves a
   marker instead of stopping the pod.
4. `emit` (python image, the main container): POST the record to the
   OpenObserve `job_health` stream (`source=restore-drill`,
   `cronjob=postgres-restore-drill`, status `ok` or `restore_failed`, the
   timings and counts), using the `observe-root` credential and the same
   `/_json` path as `audit-anchor-alert`. Exit 1 if the drill result was not
   ok, the evidence upload failed, or delivery failed, so the Job goes red.
   Evidence and job_health are attempted independently.

`job-watchdog` already watches every CronJob in the namespace (failure,
staleness against the schedule period, never-succeeded); nothing in it
changes. A drill that stops running becomes `stale`; a failing drill is
`failing`.

**Full-path RTO** is `now - t0` at the end of the checks: fetch + initdb +
start + replay + validation. It is recorded per run as `rto_seconds`, with the
phase split. It excludes pod scheduling and the first image pull, includes the later
steps' image pulls on a cold node, and excludes repointing services; the runbook says so and keeps the manual steps listed as
unmeasured. The first number of record comes from the first scheduled run on
the cluster, not from this change.

**MinIO backup** (`apps/backups/minio-offsite/`, NOT deployed, like
`apps/backups/offsite/`). CronJob `minio-backup-offsite`, daily `45 3 * * *`:
`mc mirror` of `factory-artifacts` and `factory-evidence` to
`off/$OFFSITE_S3_BUCKET/minio/<bucket>/` with no `--remove` and no
`--overwrite`, then `mc diff` source to destination must show no object that
is missing or different at the destination (`<` and `!` lines). Objects only
at the destination (kept after a source delete) are expected and do not fail
the Job. Same Secret names as #3681 (`minio-creds`, `offsite-s3-creds`),
https-only endpoint check. `factory-backups` is excluded: the Postgres dumps
already have their own off-site copy. Enabling is adding `- ../minio-offsite`
to the manifests kustomization, after the owner creates the Secret.

**Tests.** A CI workflow, in the same images the CronJobs use: the real drill
script against a dump it creates itself (good, truncated gzip, valid gzip cut
short, missing database, stale, future-dated); `fetch.sh` and the MinIO backup
against the real `mc` on local directories (absent dump, newest chosen, source
delete keeps the backup, in-place change fails and is not overwritten, http
endpoint refused); `emit.py` against a local HTTP stub (payload, auth, exit
code, evidence-failed marker); and an explicit `kustomize build` of the
not-deployed `apps/backups/minio-offsite`.

## Alternatives rejected

- Restore into a separate namespace with a StatefulSet target (what the
  2026-08-10 manual drill did): needs namespace create/delete RBAC and a
  service, and leaves state behind on failure. An in-pod Postgres on a socket
  is isolated by construction and cleans itself up with the pod.
- Restore into a scratch database on the live Postgres: risks the live
  database and its connections; the role-password replay would overwrite the
  live `factory` password.
- Fail the drill job only on exit code: a partial restore exits 0 (runbook
  step 3), so checks read the restored data.
- Weekly schedule: a bad dump would stay unseen up to a week and the watchdog
  period estimate for non-daily crons is cruder; the drill is cheap.
- Deploy the MinIO backup now suspended: `job-watchdog` escalates a suspended
  never-run CronJob to critical (the #333 finding).
- `mc mirror --remove` or `--overwrite` for the MinIO backup: a backup that
  mirrors deletions is not a backup.

## Risks

- The first live run may expose a replay error the CI cluster did not (a role
  or extension difference). Effect: the Job goes red and `job-watchdog` opens
  an issue; the live cluster is untouched. Mitigation: threshold and log are
  in the evidence record; fix forward.
- The `factory` bootstrap database may hold no tables on the live cluster; it
  is therefore only required to exist. If another database is legitimately
  empty, the first live run fails red with `no_tables_<db>` and the list
  (`TABLE_DBS`) is adjusted.
- Drill duration grows with the dump; `activeDeadlineSeconds` 1800 and the
  5Gi scratch limit bound it, and `rto_seconds` shows the trend.
- OpenObserve unavailable at 04:15: the Job fails (intended) and the evidence
  object is still written.
- Mirror never overwrites, so an object changed in place is reported by
  `mc diff` and fails the job rather than being silently re-copied.
- Row counts are not compared to the live database (RPO makes the delta
  non-deterministic); they are recorded for a human. Completeness of the dump
  rests on the end marker plus the per-database table check; a dump that is
  structurally complete but missing recent rows is RPO, not detectable here.
- The three benign-error patterns are specific to a fresh cluster with the
  `factory` bootstrap role; a change of the bootstrap role name needs the
  pattern updated (the CI test would fail first).

## Verification

- CI: `kustomize build apps/backups/manifests` (via the existing
  manifest-validate), new workflow green on the exact head SHA.
- Local: run the same test script in the same images before pushing.
- After merge (owner/coordinator, not in this change): first `job_health` and
  `factory-evidence/control-plane-push/restore-drill/` record, and the
  `rto_seconds` value goes into the runbook.

## Review record

Codex (review member, model not reported) and agy (headless, model not
reported) reviewed the intent, spec and plan together once, before commit.
Confirmed and fixed: zero-error replay policy and its benign fresh-cluster
errors (tested), cut-short valid gzip, incomplete reporting on early failure,
dump freshness, `mc diff` direction, retry duplicating records, FATAL/PANIC
lines, cleanup of scratch, tests for fetch/emit and a build of the
not-deployed directory. Refuted or deferred: none. agy's claim that `initdb`
fails under uid 65532 does not apply (the pod runs as 999 throughout, tested
with a read-only root).
