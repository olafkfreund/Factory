---
status: approved
issue: 3710
spec: spec/2026-11-16-3710-project-env-allowlist.md
coders:
  1: lead   # small, mechanical port; a handoff costs more than the edit
  2: lead   # same, in the TFactory worktree
reviewers:
  - codex   # read-only final review per repo
  - agy     # read-only final review per repo
---

# Plan: Project .env allowlist in PFactory and TFactory

Approved design: per repo, add `server/utils/project_env.py` (allowlist +
refusal regex + `load_project_env_file`), use it for the project `.env` only
(agent_service two sites, pr_review_service one call), keep backend `.env`
loading, log ignored key names never values. AIFactory needs no change. Code PRs
target `dev` in PFactory and TFactory.

## Steps

1. PFactory `apps/web-server/server/utils/project_env.py` (new);
   `services/agent_service.py` (~689-704, ~942-960);
   `services/pr_review_service.py` (~292): use the loader; add
   `tests/test_project_env_allowlist.py` → `pytest` that file + `ruff check`.
   Test asserts: PYTHONPATH/LD_PRELOAD/NODE_OPTIONS absent, USE_CLAUDE_MD present;
   every key `routes/context.py` writes is allowed; existing env keys not overwritten;
   ignored names logged, values not; quotes stripped; a source check that the
   project-file call sites use `load_project_env_file`.
   Traps: `sanitize_log` for logged names.
2. TFactory: same files (`agent_service.py` ~3055-3070, ~3341-3360;
   `pr_review_service.py` ~271; f-string logging style there) → same check.
   Traps: none beyond step 1.

## Tests

`pytest apps/web-server/tests/test_project_env_allowlist.py` (path per repo layout)
green; `ruff check`/`ruff format --check` clean on touched files.

## Rollback

Revert the PR; behaviour returns to loading every key.
