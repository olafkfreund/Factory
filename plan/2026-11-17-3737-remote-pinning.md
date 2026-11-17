---
status: approved
issue: 3737
spec: spec/2026-11-17-3737-remote-pinning.md
coders:
  all: lead  # a few lines in the hub; the services only vendor and test
reviewers:
  - codex  # agy is off by owner decision
---

# Plan: pin remotes other than origin

Decision carried from the spec: `merge_driver_pins` refuses `remote.*.uploadpack`,
`.receivepack` and `.vcs`; no per-remote `-c` pins. Base `main` (hub), `dev` (services).
Shares the branch `feat/3737-git-baseline-remote-pins` and the vendoring commits with
`plan/2026-11-17-3737-git-metadata-baseline.md`.

## Steps

1. Factory `shared/factory-sandbox/agent_sandbox/git_pins.py` (`_REMOTE_PROGRAM_SUFFIXES`,
   check in the key loop, docstring), `tests/test_git_metadata.py` (refusal and witness tests),
   `README.md` → `pytest shared/factory-sandbox/tests`.
   Traps: keep the `=` check and the surrogateescape note intact.
2. PFactory, TFactory, AIFactory: vendored with step 2 of the baseline plan. Service tests:
   `tests/test_git_metadata_baseline.py` (PF/TF) asserts `core.child_env.merge_driver_pins`
   raises for `remote.evil.uploadpack`; AIFactory `tests/test_agent_sandbox.py` asserts the same
   on the vendored `agent_sandbox.merge_driver_pins`. → pytest those files.
3. Per repo: `codex review --base origin/<base>`, lint, push, PR.

## Tests

As the baseline plan. Negative test: an unpinned remote is rejected.

## Rollback

Revert the hub PR and the service re-vendor PRs; no state is written.
