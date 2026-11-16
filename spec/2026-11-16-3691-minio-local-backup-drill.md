---
status: approved
issue: 3691
intent: intent/2026-11-16-3691-minio-local-backup-drill.md
---

# Spec: MinIO local snapshot and scheduled MinIO restore drill

## Design

All in factory-gitops `apps/backups`.

1. `minio-local/` (new, added to `manifests/kustomization.yaml`): PVC
   `minio-backup-local` (local-path, 20Gi, same size as `minio-data`) and CronJob
   `minio-backup-local`, 03:30 UTC. Each run writes a NEW generation
   `/backup/gen-<UTC stamp>/<bucket>/...` (full `mc mirror`, so a rewritten key is
   captured and the earlier generation keeps the old bytes), under a `.tmp-` name.
   It then checks every object against the live source (name, size, sha256),
   writes `MANIFEST.sha256` (one hash per snapshot file), and only then renames
   the directory to `gen-...` and writes a `COMPLETE` marker last. It keeps the
   newest 3 complete generations and deletes older ones and stale `.tmp-` dirs.
   shortcut: full copy per generation, fine at MB-GB scale; move to hardlinks or
   restic when the buckets grow.
2. `drill/minio-drill.sh` + CronJob `minio-restore-drill` in the existing drill
   ConfigMap and kustomization, 04:30 UTC. Mounts the PVC read-only. Steps:
   newest generation that has `COMPLETE`, else problem `no_snapshot`; its age from
   the name must be at most 25h (`snapshot_stale`); create `restore-drill-scratch`
   if absent and set SSE-S3 on it; pick a bounded sample per bucket (20 objects
   by name, each at most 50 MiB; a bucket with no objects is `empty_bucket_...`);
   restore each from the snapshot into scratch via `mc cp`; compare the restored
   bytes with the hash in `MANIFEST.sha256` (NOT with live data, so a deleted or
   corrupted live object does not hide a good restore, and a corrupted snapshot
   file is caught); remove the scratch objects by exact key. Writes `result.json`
   in the shape the Postgres drill uses (`ok`, `problems`, `rto_seconds`,
   per-phase seconds, counts).
3. `rto_seconds` = job start to verified scratch restore. Only the sample is
   restored; `sample_bytes` and `snapshot_bytes` are in the result so a
   full-bucket estimate can be derived, and the result does not claim one.
4. `emit.py` takes `CRONJOB` and `DRILL_KIND` from the environment (defaults keep
   the Postgres drill unchanged) so one emitter serves both.
5. Tests: `minio-local/test.sh` and `drill/test-minio.sh` against the real mc
   with a local-directory wrapper (same pattern as `minio-offsite/test.sh`),
   wired into `backup-drill-test.yml`, plus a kustomize render check.
6. Factory `dr-runbook.md`: record what exists, the same-node limit, and the
   owner steps still open.

## Alternatives rejected

- Mirror to a second MinIO bucket: same PVC, same failure domain, and
  versioning lifecycle already covers it; no gain.
- Restic/Kopia snapshots: new image and tooling for no extra protection here.
- Hard-linked or incremental generations: `mc` may rewrite hard-linked files in place, which would corrupt older generations.
- Restoring the whole bucket in the drill: cost grows with data; a sample plus
  recorded sizes gives a real measured path and a scalable estimate.
- A new emitter: duplicates `emit.py`.

## Risks

- Snapshot and `minio-data` share the node disk: stated, not hidden.
- The snapshot is plaintext on the PVC (mc reads decrypted bytes), so SSE-S3 at rest does not carry over. Mitigation: mode 0700, uid 65532 only. Residual risk, owner decision (encrypt snapshots with a key the owner provides, or accept).
- PVC of 10Gi may be too small later; the job fails red when full, so it is seen.
- Scratch bucket stays (empty); it is not covered by lifecycle rules.
- `minio-creds` is the root credential, so the drill could in principle write
  elsewhere; the script only touches the scratch bucket (tested).

## Verification

CI `backup drill test` (real mc): good run; a rewritten key lands in a new
generation while the old one keeps the old bytes; a failed run leaves no `gen-`
dir; only 3 generations kept; the drill passes after the live object is deleted
or changed; the drill fails on a corrupted snapshot file, a missing COMPLETE
marker, a stale snapshot and an empty bucket; scratch is left empty. `kustomize build apps/backups/manifests`
renders both CronJobs and the PVC. After merge: first scheduled run shows in
`job_health` with `cronjob=minio-restore-drill`.
