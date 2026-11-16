---
status: approved
issue: 314
spec: spec/2026-11-16-314-encryption-custody-sse-audit.md
coders:
  1: you (lead)
  2: you (lead)
  3: you (lead)
  4: you (lead)
reviewers:
  - codex
---

# Plan: encryption custody, SSE audit, policy refresh

Self-contained summary: add an offline SSE audit script and custody/KES/LUKS documentation in factory-gitops, refresh the stale Factory compliance policy, comment on #314. No live changes. Decisions carried from spec: fail-closed audit, stay on static KMS key, LUKS stays owner-run on p620.

## Steps

1. factory-gitops `scripts/minio-sse-audit.py` (new): stdin mc JSON lines, per-bucket counts, delete markers skipped, required --bucket, fail closed (exit 1 unencrypted, 2 bad/empty input or a status:error line; tests for truncated and error input), `--self-test`, stdlib only → verify `python3 scripts/minio-sse-audit.py --self-test`.
   Traps: no subprocess/network imports; never print object content.
2. factory-gitops `.github/workflows/secret-rotation-due.yml`: add script path to PR paths and a self-test step beside the drill's → verify `python3 -c 'import yaml,sys;yaml.safe_load(open(".github/workflows/secret-rotation-due.yml"))'` and run the step locally.
   Traps: workflow-duplication check; keep permissions read-only.
3. factory-gitops `docs/secrets-management.md`, `docs/encryption-at-rest.md`: custody register + commands, offline backup check, KES decision record, LUKS host fix plus mandatory verified off-cluster copy of buckets (all versions) and recovery key, audit script in owner checks → verify `rotation-ledger-check.py --validate-only`, `minio-kek-drill.py --self-test` (it parses the runbook section; do not rename the KEK compromise heading or drop buckets).
   Traps: no key material or fingerprints in docs.
4. Factory `docs/compliance/policies/encryption-key-mgmt.md`: refresh Current state, Gaps → verify links resolve to existing files and PR numbers via gh.
   Traps: do not claim FIPS or KES; mark Live vs Repo vs Record.

## Tests

The three scripts above exit 0. Codex review on both diffs.

## Rollback

Revert the two PRs; docs and an unused script only.
