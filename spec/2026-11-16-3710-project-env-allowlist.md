---
status: draft
issue: 3710
intent: intent/2026-11-16-3710-project-env-allowlist.md
---

# Spec: Project .env allowlist in PFactory and TFactory

## Design

Port AIFactory's `server/services/project_env.py` into each repo as
`apps/web-server/server/utils/project_env.py`: a `PROJECT_ENV_KEYS` frozenset
(the keys the Settings routes write plus `USE_CLAUDE_MD` and the MCP toggles
`core/client.py` reads), a refusal regex (`LD_*`, `DYLD_*`, `NODE_OPTIONS`,
`BASH_ENV`, `ENV`, `PYTHON*`, `GIT_*` except the Factory git keys, `PATH`, `HOME`,
`SHELL`, `*_PROXY`) as defence in depth, and
`load_project_env_file(path, env)`: parse `KEY=VALUE` lines, stripping one pair of surrounding quotes (the
`pr_review_service` behaviour; `agent_service` kept them, which only mattered for
quoted values and is an intended fix), never overwrite existing keys, set only allowed keys, log the names of ignored
keys once per load at WARNING. Replace the project-file loops in `agent_service.py`
(two sites) and the `_load_env_file(project_path / ".<x>factory" / ".env")` call in
`pr_review_service.py` with it. The backend `.env` loops stay.

## Alternatives rejected

- Blocklist of dangerous names: misses the next one (`RUBYOPT`, `JAVA_TOOL_OPTIONS`).
- Remove project `.env` loading: breaks Settings UI keys.
- Shared package in Factory: a cross-repo release for ~40 lines; AIFactory already duplicates it.

## Risks

A key the UI writes but the list omits stops loading. Mitigated by deriving the
list from `routes/context.py` and a test that every key that route writes is
allowed.

## Verification

New `tests/test_project_env_allowlist.py` per repo: dotenv with `PYTHONPATH`,
`LD_PRELOAD`, `NODE_OPTIONS` and `USE_CLAUDE_MD`; assert only the last loads,
ignored names logged, values not logged, existing env keys not overwritten, and
`pr_review_service` path behaves the same, a quoted value loads unquoted, and the
source of each runner entry point (both `agent_service` loaders and `pr_review_service`)
no longer calls the raw loader for the project file. Run the repo's pytest for touched files and ruff.
