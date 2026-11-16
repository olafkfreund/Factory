---
status: approved
issue: 314
intent: intent/2026-11-16-314-encryption-custody-sse-audit.md
---

# Spec: encryption custody, SSE audit, policy refresh

## Design

1. factory-gitops `scripts/minio-sse-audit.py`: reads mc JSON lines on stdin (`mc stat --versions --recursive --json`), skips delete markers, counts per bucket the entries that are SSE-S3 (`X-Amz-Server-Side-Encryption: AES256`, header name case-insensitive, under `metadata` or top level), and fails closed: an entry with no encryption field counts as unencrypted; unparseable lines, a line with `status: error` (an interrupted or failed enumeration) or an empty input exit 2. One bucket per run (`--bucket NAME` is required and printed), run for all three buckets under `set -o pipefail`, so a truncated capture or a skipped bucket cannot read as green. Exit 0 only when at least one entry was seen and all are encrypted. Prints counts and up to N offending names. `--self-test` mirrors `minio-kek-drill.py`. Stdlib only. The real `mc` JSON shape is UNPROVEN until the owner runs it once; the doc says so and the script accepts the documented header.
2. factory-gitops `docs/secrets-management.md`: extend "Decryption-key custody" with a custody register table (identity, holder, where, recovery use), exact agenix re-key and identity-rotation commands, and an offline-backup verification (decrypt one test file with the backup identity, never print values).
3. factory-gitops `docs/encryption-at-rest.md`: add the audit script to "Open owner checks", a "KES versus the static key" decision record (stay static: single node, one KEK, KES needs its own KMS backend and an HA-less KES would add a second root of trust; revisit when scheduled KEK rotation or multiple named keys is required), and fix the LUKS runbook host (p620) with exact commands, and require a verified off-cluster copy of all three buckets (every version) and of the LUKS recovery key before formatting.
4. Workflow `secret-rotation-due.yml`: add the new script and run its self-test (it already guards the KEK drill the same way).
5. Factory `docs/compliance/policies/encryption-key-mgmt.md`: replace the stale Current state and Gaps with the dated state, each line linking its evidence.
6. Epic comment.

## Alternatives rejected

- Deploy KES: needs a KMS backend and owner credentials; no scheduled rotation requirement today.
- Script that calls mc: needs credentials and a live endpoint; piping keeps it offline and testable.
- Re-encrypt old objects automatically: rewriting objects in production is the same class of risk as the untested KEK drill; owner decision.

## Risks

Doc drift (the new script is covered by the workflow self-test). The mc JSON field name may differ: fail closed makes that visible, not silently green.

## Verification

`python3 scripts/minio-sse-audit.py --self-test`, `python3 scripts/minio-kek-drill.py --self-test`, `python3 scripts/rotation-ledger-check.py --validate-only`, manifest-validate unchanged. Codex review of both diffs.
