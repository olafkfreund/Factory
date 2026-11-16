---
status: approved
issue: 3691
spec: spec/2026-11-16-3691-minio-local-backup-drill.md
coders:
  1: lead (small, one repo, tightly coupled scripts; no handoff)
  2: lead
  3: lead
  4: lead
reviewers:
  - codex   # independent read of the diff against this plan
---

# Plan: MinIO local snapshot and scheduled MinIO restore drill

Self-contained summary of the approved spec. Repo: factory-gitops, `apps/backups`
(branch feat/3691-minio-local-backup-drill off main). Factory only gets the
runbook edit. Decisions: generation-per-run full copy in `/backup/gen-<stamp>`
with `MANIFEST.sha256` and `COMPLETE` written last, keep 3; drill verifies
against the manifest, not live data; stale (>25h), missing-COMPLETE and empty
bucket are red; scratch bucket `restore-drill-scratch` with SSE-S3, emptied by
exact key; `rto_seconds` = start to verified restore of a bounded sample; one
emitter via CRONJOB / DRILL_KIND env; no new credential; plaintext snapshot
is a stated residual risk.

## Steps

1. `minio-local/{cronjob.yaml,kustomization.yaml,minio-local.sh,test.sh}`: PVC +
   CronJob 03:30 UTC (copy the securityContext/limits pattern of
   `minio-offsite/cronjob.yaml`, uid 65532, mount PVC rw at /backup), script as
   in spec item 1 → verify: `test.sh` in the pinned mc image.
   Traps: mc image has no extra tools beyond sh/grep/sha256sum (as offsite);
   use plain `mc mirror`, no `--overwrite` needed on a fresh dir; chmod 0700.
2. `drill/minio-drill.sh`, `drill/test-minio.sh`, `drill/minio-cronjob.yaml`
   (CronJob `minio-restore-drill` 04:30 UTC: initContainer `drill` (mc image),
   container `emit` (python, same as Postgres drill); evidence upload as in the
   Postgres drill; PVC mounted readOnly), add to `drill/kustomization.yaml`
   (resource + ConfigMap file) → verify: `test-minio.sh`.
   Traps: result.json must keep the keys emit.py reads; backoffLimit 0.
3. `drill/emit.py`: `cronjob` from env CRONJOB, `kind` from DRILL_KIND, defaults
   unchanged; extend `drill/test_emit.py` → verify: `python3 apps/backups/drill/test_emit.py`.
4. `manifests/kustomization.yaml`: add `../minio-local`;
   `.github/workflows/backup-drill-test.yml`: run both new tests, render check
   → verify: `kustomize build apps/backups/manifests` shows 3 CronJobs + PVC.
5. Factory `docs/compliance/dr-runbook.md`: record the snapshot, the drill, the
   same-node and plaintext limits, owner steps (separate Factory PR).

## Tests

Both new shell tests in the mc image via the workflow's docker invocation;
`test_emit.py`; kustomize build; `kubectl kustomize` or kubeconform if the
repo's manifest-validate workflow uses it.

## Rollback

Revert the PR; Argo prunes the CronJobs. The PVC `minio-backup-local` is pruned
too (data is a copy only).
