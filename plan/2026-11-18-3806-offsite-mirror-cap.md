---
status: draft
issue: 3806
spec: spec/2026-11-18-3806-offsite-mirror-cap.md
coders:
  1: you   # contained edits across 3 scripts, done by the lead; Codex reviews the diff
  2: you   # tests, same files family
reviewers:
  - codex  # read-only review of every draft and the final diff
---

# Plan: cap mc mirror parallelism in the offsite backup scripts

Repo: olafkfreund/factory-gitops, base main, branch fix/3806-offsite-mirror-cap. Decisions from the spec: shared overridable `MC_MAX_WORKERS` (default 4, digits only, no leading zero) on every `mc mirror`; CronJob limits unchanged; neither offsite directory added to a kustomization.

## Steps

1. apps/backups/{minio-local/minio-local.sh,minio-offsite/minio-offsite.sh,offsite/offsite-copy.sh}: add the variable + validation after `SCRATCH=`, add `--max-workers "$MC_MAX_WORKERS"` to each mc mirror (4 calls) → verify by grep that no mirror lacks the flag.
   Traps: do not touch kustomization.yaml or cronjob.yaml.
2. apps/backups/*/test.sh: mc stub/wrapper rejects an uncapped mirror (exit 97), override run with MC_MAX_WORKERS=2, bad-value rejection in minio-local → verify by running the three test.sh files.
   Traps: minio-local/minio-offsite tests need real mc (pinned image); locally NIXPKGS_ALLOW_INSECURE=1 nix shell --impure nixpkgs#minio-client nixpkgs#age.

## Tests

`sh apps/backups/{offsite,minio-local,minio-offsite}/test.sh` all pass; CI backups workflow green.

## Rollback

Revert the PR; nothing offsite is deployed, minio-local returns to the hardcoded 4.
