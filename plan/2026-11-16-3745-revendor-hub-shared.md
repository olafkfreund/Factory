---
status: approved
issue: 3745
spec: spec/2026-11-16-3745-revendor-hub-shared.md
coders:
  1: you
  2: you
reviewers:
  - codex
---

# Plan: re-vendor hub shared packages

Decisions carried from the spec: copy canonical byte-for-byte, pin to hub main `b3844b8b224d1ec198afd7a77221eb67b45fe217`, one PR per repo (base dev), minimal test adaptation only.

## Steps

1. AIFactory, PFactory, TFactory `apps/backend/agent_sandbox/*.py` and `.hub-sha`; factory_common in AIFactory `apps/{backend,web-server}`, PFactory/TFactory `apps/web-server`, CFactory `apps/backend` → verify by drift script and `diff -r`.
   Traps: never hand-edit vendored files; pin = hub main squash commit.
2. AIFactory `tests/test_sanitize_error_message.py`: use a non-sk-ant- key in the original-placeholder test and add a test that sk-ant- keys get the fleet placeholder → verify by `pytest tests/test_sanitize_error_message.py`.
   Traps: none.
3. After the PRs merge, run `python3 scripts/check_pin_freshness.py` in Factory (it reads remote default branches, so it cannot check unmerged PRs) → verify the factory-common rows pass.

## Tests

`python3 scripts/check_factory_sandbox_drift.py --service apps/backend/agent_sandbox`; `diff -r --exclude=.hub-sha --exclude=README.md` of each vendored factory_common against the canonical;  url-safety, logsafe, credential-repr and sanitize tests pass; repo CI green.

## Rollback

Revert the PR; pins return to the previous SHA.
