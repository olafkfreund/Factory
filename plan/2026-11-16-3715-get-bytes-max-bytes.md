---
status: draft
issue: 3715
spec: spec/2026-11-16-3715-get-bytes-max-bytes.md
coders:
  1: lead
  2: lead
  3: lead
reviewers:
  - codex
  - agy
---

# Plan: get_bytes(max_bytes=)

Implement the spec: optional `max_bytes` on hub `get_bytes`, raise ValueError
on overflow, re-vendor byte-exactly, drop AIFactory `_read_capped`.

## Steps

1. scripts/artifact_store.py: add `max_bytes`, fake ContentLength, `_selftest_get_bytes_cap` → `python3 scripts/artifact_store.py`, `ruff check`.
   Traps: none.
2. Re-vendor the hub copy to AIFactory apps/backend/core, PFactory apps/backend/runners, TFactory apps/backend/tools/runners; set `HUB_PIN_SHA` in each verification-core-drift.yml to the hub merge SHA → `cmp` against hub file.
   Traps: pin must be a squash-merge SHA on hub main; do not hand-edit vendored files.
3. AIFactory workspace_fetch.py: use `get_bytes(max_bytes=)`, delete `_read_capped` and its test, adapt the fake store in tests/test_spec_job_backend.py → `pytest tests/test_spec_job_backend.py`.
   Traps: AIFactory ruff alias sorting (plain names).

## Tests

Hub self-test passes; AIFactory spec-job tests pass; drift gates green after re-point.

## Rollback

Revert the four PRs; the default (uncapped) path is unchanged.
