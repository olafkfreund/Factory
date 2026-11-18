---
status: approved
issue: 3807
spec: spec/2026-11-18-3807-backup-cronjob-failures.md
coders:
  1: lead   # three small edits to one script: a handoff costs more than it saves
  2: lead
  3: lead
reviewers:
  - codex   # read-only review of each draft and of the final diff
---

# Plan: backup CronJob failures

Approved decisions (spec): fix the drill's expectations to match the live
database (ignore any `role ... does not exist`; require pfactory, tfactory,
aifactory, cfactory to exist; require tables only in pfactory, tfactory,
aifactory); cap `mc mirror` with `--max-workers 4` and keep 512Mi. All changes
in factory-gitops (base main). No live-cluster action.

## Steps

1. `apps/backups/drill/drill.sh`: change the default `EXPECTED_DBS`
   and `TABLE_DBS` lines, and the error filter
   `role "factory" already exists` -> `role ".*" does not exist|role "factory" already exists`.
   → verify by step 2.
   Traps: filter lives inside `grep -vcE`; keep `|| true`.
2. `apps/backups/drill/test.sh`: build the source like production (databases
   pfactory tfactory aifactory populated, cfactory empty, role+db `myfriends`);
   update expected `databases`/`tables`/`rows`; keep the `missing-db` and other
   cases. → verify by `docker run` of the pinned postgres:16.4 image as uid 999
   running test.sh (CI does the same), expect `ALL PASS`; also run
   `python3 apps/backups/drill/test_emit.py`.
3. `apps/backups/minio-local/minio-local.sh` line 34: `mc mirror --max-workers 4`;
   update the comment on the script's header if needed. → verify by
   `sh apps/backups/minio-local/test.sh` and the same test inside the pinned minio-client image as CI does (test.sh forwards to real `mc`).
   Traps: the fake `mc` in test.sh must still match `$1 = mirror`.
4. Commit, push, PR to main; wait for checks. Comment root causes on #3806
   and #3807 (no close).
5. If a drill run succeeds before the PR is done, record its `rto_seconds` in
   Factory `docs/compliance/dr-runbook.md` (Factory PR, docs only).

## Tests

test.sh (drill), test_emit.py, minio-local/test.sh: all pass.

## Rollback

Revert the factory-gitops PR; Argo CD syncs the old scripts.
