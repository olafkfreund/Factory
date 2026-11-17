---
status: approved
issue: 3737
spec: spec/2026-11-17-3737-git-metadata-baseline.md
coders:
  all: lead  # small, security-sensitive edits; a handoff costs more than it saves
reviewers:
  - codex  # agy is off by owner decision
---

# Plan: git metadata baseline for PFactory and TFactory

Decisions carried from the spec: one hub module bound as the `check` of
`merge_driver_pins`; record at `create_worktree`; bind only in PF/TF core merge and writer
paths; AIFactory vendors only; late baseline is a warning, as in AIFactory. Base `main`
(hub), `dev` (services). Branch `feat/3737-git-baseline-remote-pins` everywhere.

## Steps

1. Factory `shared/factory-sandbox/agent_sandbox/git_metadata.py`, `__init__.py`,
   `tests/test_git_metadata.py`, `README.md`, `scripts/check_factory_sandbox_drift.py`
   (`CANONICAL_FILES`, `_ADDED_LATER` skip rule for `git_metadata.py` only, self-test cases) → `pytest shared/factory-sandbox/tests
   tests/test_check_factory_sandbox_drift.py`; `ruff check`.
   Traps: stdlib only; the module name must not import `env`.
2. PFactory and TFactory `apps/backend/agent_sandbox/*` copied byte-for-byte from the hub
   commit on `main`, `.hub-sha`, `.github/workflows/agent-sandbox-drift.yml` `HUB_SHA`.
   → drift script exit 0. Traps: vendored files are never edited; the pin must be on hub main.
3. PFactory and TFactory `apps/backend/core/child_env.py` `merge_driver_pins(..., baseline=False)`;
   `core/workspace/git_utils.py` (two calls) and `tools/git_writer.py` pass `baseline=True`;
   `core/worktree.py` `create_worktree` records both baselines → new
   `tests/test_git_metadata_baseline.py`. Traps: plain names in parenthesised imports (ruff).
4. AIFactory: step 2 plus tests in `tests/test_agent_sandbox.py` (hub `merge_driver_pins` refuses
   `remote.evil.uploadpack`; the vendored `check_git_metadata` detects a tampered repo). → drift
   script exit 0; `pytest tests/test_agent_sandbox.py`.
5. Per repo: `codex review --base origin/<base>`, own read against this plan, lint, push, PR.

## Deviations

From the Codex final review (`codex review --base origin/main` and per service):

- Step 1: `git_metadata` reads git output as bytes, so a CR-to-LF change in a config value
  is detected (text mode hid it); the recovery hint prefixes `FACTORY_GIT_BASELINE_DIR=<dir>`
  when the variable is set, because PF/TF default to `~/.pfactory` and `~/.tfactory`.
- Step 3 (PF/TF): the bound check ignores an injected `run` and uses the byte-exact default
  runner, and `create_worktree` records with it too, so recording and checking decode the
  same way. `tests/test_git_writer.py` (fake runner on non-git directories) stubs the check;
  the real check is exercised in `tests/test_git_metadata_baseline.py` and
  `tests/test_git_utils_env.py`.

## Tests

Hub: `pytest shared/factory-sandbox/tests tests/test_check_factory_sandbox_drift.py`.
Services: `pytest tests/test_git_metadata_baseline.py tests/test_git_utils_env.py`; drift script;
`ruff check apps tests`. Negative test: a tampered baseline is detected (every service).

## Rollback

Revert the PRs. Baseline files under `~/.factory/git-baselines` are inert and can be deleted.
