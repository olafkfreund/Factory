---
status: draft
issue: 3806
intent: intent/2026-11-18-3806-offsite-mirror-cap.md
---

# Spec: cap mc mirror parallelism in the offsite backup scripts

## Design

Each of the three scripts sets `MC_MAX_WORKERS=${MC_MAX_WORKERS:-4}`, rejects a non-numeric or zero-leading value, and passes `--max-workers "$MC_MAX_WORKERS"` to every `mc mirror`: minio-local.sh (1 call), minio-offsite.sh (2: the age-encrypted snapshot path of factory-gitops#356 and the plaintext path), offsite-copy.sh (1, the legacy path; its age path uses cat/cp, no mirror). Other mc verbs (cp, cat, find, diff) are single-stream and not capped. Tests: the mc stub/wrapper in each test.sh rejects any `mirror` call without `--max-workers $EXPECT_WORKERS` (default 4); minio-local and minio-offsite also run once with MC_MAX_WORKERS=2.

## Alternatives rejected

- Raise the memory limit: owner decision on #3806 is to reduce parallelism first.
- Hardcode 4 in each script: no way to tune without an image edit.
- Cap via a global mc env var: mc has no such setting; the flag is explicit and testable.

## Risks

Low: a lower worker count slows large mirrors. Offsite is not deployed. A bad override fails fast with a clear message.

## Verification

The three test.sh scripts pass (real mc 2025-08-13 for minio-local/minio-offsite, stub for offsite); shellcheck clean of new findings; kustomization files untouched (neither offsite directory referenced); the rendered minio-backup-local ConfigMap changes only by the script text.
