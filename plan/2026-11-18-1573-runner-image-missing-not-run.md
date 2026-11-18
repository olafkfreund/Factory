---
status: draft
issue: 1573
spec: spec/2026-11-18-1573-runner-image-missing-not-run.md
---

# Plan: Treat docker exit 125 as "test never ran"

Decisions carried from the approved spec: add 125 to the existing
`_SHELL_NOT_RUN_CODES`; no stderr parsing, no host fallback, no new path.
Two files, two steps: implemented directly, no handoff.

## Steps

1. `apps/backend/agents/stability_runner.py` (~L125-126): change the tuple to
   `(125, 126, 127)` and the comment to say 125 is `docker run` failing before
   the container starts (image missing). Verify by the test in step 2.
   Traps: none.
2. `tests/test_stability_runner.py`: add a test that `classify_pytest_failure("", 125)`
   is `environment`; and one that `_mutation_from_codes` marks 125 NOT_RUN.
   Verify by it failing on dev and passing with step 1.
   Traps: tests run from repo root with apps/backend on the path as the neighbours do.

## Tests

`pytest tests/test_stability_runner.py tests/test_confidence.py -q` passes;
the new test fails with step 1 reverted.

## Rollback

Revert the squash commit; no data or config changes.
