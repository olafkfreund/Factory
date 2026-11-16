---
status: draft
issue: 3691
spec: spec/2026-11-16-3691-restore-drill-minio-backup.md
coders:
  1: lead
  2: lead
  3: lead
  4: lead
reviewers:
  - codex
  - agy
---

# Plan: Scheduled restore drill and MinIO backup (R-001)

Carries the approved spec: daily in-pod restore drill (deployed), disabled
MinIO backup (not deployed), tests in CI, runbook update. Repos:
factory-gitops (code, branch `feat/3691-restore-drill-minio-backup`, base
`main`) and Factory (these artifacts and the runbook, branch
`docs/3691-restore-drill-minio-backup`, base `main`). Coder routing: every
step is small and tricky shell/YAML that I verify by running, so I do them
myself; agy and codex review only (reason: a handoff would cost a fresh cache
and a re-read for about 400 lines).

## Decisions carried from the spec

- Drill: CronJob `postgres-restore-drill`, `15 4 * * *`, `backoffLimit: 0`,
  in-pod throwaway Postgres (`initdb -U factory`, unix socket, no listener),
  four steps fetch -> drill -> evidence -> emit; fetch never fails the pod
  (writes a not-ok result); evidence and job_health attempted independently;
  Job red on any not-ok result.
- Rejects dumps that are not gzip, empty, older than 25h, future-dated, or
  lacking the `pg_dumpall` end marker. Replay `ON_ERROR_STOP=0`; three benign
  fresh-cluster errors excluded, every other ERROR/FATAL/PANIC counts (limit 0).
  Checks: five databases exist, four service databases have tables, rows > 0,
  `pg_dump -s` per database. Records `rto_seconds` and the phase split.
- Result goes to `factory-evidence/control-plane-push/restore-drill/<UTC>.json`
  and to OpenObserve `job_health` (`source=restore-drill`), credentials
  `minio-creds` and `observe-root`. `job-watchdog` unchanged.
- MinIO backup: `minio-backup-offsite`, `45 3 * * *`, `factory-artifacts` and
  `factory-evidence` only, no `--remove`, no `--overwrite`, fails on source
  objects missing or different at the destination, destination-only objects
  are fine; same `offsite-s3-creds` as #3681; not deployed.
- Runbook states the RTO method and its exclusions and leaves the first value
  pending the first scheduled run. The off-site target is an owner action.

## Steps

1. factory-gitops `apps/backups/drill/drill.sh`, `emit.py`, `fetch.sh`,
   `kustomization.yaml` (configMapGenerator, no name hash): the scripts as in
   the spec. Check: step 3 test.
   Traps: bash not sh in the postgres image (dash has no pipefail); `mc find`
   is unordered, sort; the mc image has no jq; the dump replays a role
   password so use trust auth on a socket; vendored/pinned image digests only
   (copy the digests from `apps/backups/manifests/manifests.yaml` and
   `apps/audit-anchor-alert`).
2. factory-gitops `apps/backups/drill/cronjob.yaml`, and add `- ../drill` to
   `apps/backups/manifests/kustomization.yaml`. Check: `kustomize build
   apps/backups/manifests` renders both CronJobs and the ConfigMap.
   Traps: no `ttlSecondsAfterFinished` (#381), `restartPolicy: Never` (#438),
   not `suspend`.
3. factory-gitops `apps/backups/drill/{test.sh,test-fetch.sh,test_emit.py}`,
   `apps/backups/minio-offsite/{cronjob.yaml,minio-offsite.sh,test.sh,
   kustomization.yaml}`, `.github/workflows/backup-drill-test.yml`.
   Check: run both tests locally in the pinned images; shellcheck-free
   syntax with `sh -n`/`bash -n`.
   Traps: pin images by digest; workflow has no `paths:` filter, action pinned
   by SHA like `backup-offsite-test.yml`; the minio-offsite dir is not
   referenced by any kustomization.
4. Factory `docs/compliance/dr-runbook.md`: protected-assets table, RTO
   section (method, what is excluded, first value pending), drill section
   (how to read, query), outstanding list (MinIO backup landed disabled,
   scheduled drill done, owner actions). Also correct the manual drill note
   that it is "outstanding". Check: markdown reads, links resolve.

## Tests

- `docker run` the pinned postgres image with `apps/backups/drill/test.sh`:
  expect ALL PASS (good, truncated gzip, incomplete SQL, missing database,
  stale, future-dated).
- `docker run` the pinned mc image with `apps/backups/drill/test-fetch.sh` and
  `apps/backups/minio-offsite/test.sh`: expect ALL PASS.
- `python3 apps/backups/drill/test_emit.py`: expect ALL PASS.
- `kustomize build apps/backups/minio-offsite` (not built by manifest-validate).
- `kustomize build apps/backups/manifests`; manifest-validate in CI.
- Final: `codex review --base origin/<base>` on both repos plus agy.

## Rollback

Revert the factory-gitops PR (Argo CD prunes the CronJob and ConfigMap; the
evidence objects already written are harmless). The MinIO backup is not
deployed, so it has nothing to roll back until enabled.
