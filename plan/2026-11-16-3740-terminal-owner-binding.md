---
status: draft
issue: 3740
spec: spec/2026-11-16-3740-terminal-owner-binding.md
coders:
  1: lead   # AIF: small tricky security logic, kept by the lead rather than a handoff
  2: lead   # PF: port of step 1 with PF's own imports (confine_to_workspace, .projects)
  3: lead   # TF: port of step 1 with TF's own imports (InputRejectedError, ._specpath)
reviewers:
  - codex   # reviews each draft and the final diff per repo; agy is off by owner decision
---

# Plan: bind terminal sessions to their owner and project

Closes Factory#3740. This file is self-contained; the decisions are the approved spec.

## Approved decisions

In AIFactory, PFactory, TFactory (`apps/web-server/server`):

- `pty/session.py`: `PTYSession` gets fields `owner_id: str | None = None`, `project_id: str | None = None` (not in `to_dict`).
- `pty/manager.py`: `class DuplicateSessionError(ValueError)`; `create_session(..., owner_id=None, project_id=None)` raises it under the lock, before `PTYSession(...)`/`start()`, when `session_id` already exists; stores both fields. `close_session(session_id, expected=None)` returns `False` without closing when `expected` is given and `sessions.get(id) is not expected`. Keep every existing caller working (`routes/cli_accounts.py` passes nothing new).
- `pty/access.py` (new): `project_ok(user, project_id)` (strict `authorize_project_for_user` on an `async_session_factory()` session; `False` on any exception; never shadow mode), `may_use(user, session)` (service principal passes; else `user.get("id") == session.owner_id` and `project_ok`), `project_id_for_path(path)` (registered project whose resolved path equals or contains the resolved path, longest wins, else `None`; a registered project id passed as `path` is returned as is), `authorize_path(user, path)` (service passes and returns the match or `None`; else a match is required and `project_ok`, otherwise `HTTPException(403)`; returns the id). A restricted principal is any user that is not `is_service_principal`; on REST `None` is restricted, on WS `None` is unrestricted (the WS handler checks it).
- `routes/terminal.py`: as spec "REST": create (cwd resolved as today, confinement as today, then non-service requires a registered authorized project, stores owner/project, `DuplicateSessionError` -> 409); list and `/sessions` filtered with `may_use`, `/sessions` honours `project` via `project_id_for_path`; `get`, `delete` (passes `expected`), `resize`, `buffer` (non-service saves under the session's project, ignores body `projectId`), `alive` use one helper `_owned(terminal_id, http_request)` returning the session or 404; `/worktrees` GET/POST/DELETE and `DELETE /sessions?project=` call `authorize_path`; `DELETE /sessions` without `project` and `POST /cleanup` return 403 for non-service. Each route gets `http_request: Request` and reads `http_request.state.user` (the create body parameter is already named `request`).
- `websockets/terminal.py`: `authenticate_websocket` instead of `verify_websocket_token` (`WebSocketAuthError` -> return); after `accept`, missing or `not may_use` -> existing "not found" frame, close 4004; for restricted users a watcher task (`_RECHECK_SECONDS = 5.0` module constant) re-validates an `acw_` key with `_ws_acw_principal` (revoked, exception or `None` -> close 4001) then `may_use` (fail -> close 4003) each tick; cancel it in `finally` with the reader.

## Steps

1. **AIFactory** (lead). Worktree `scratchpad/teams/f3740t/AIFactory`, branch `fix/3740-terminal-owner-binding` off `origin/dev`; fetch and rebase first. Files: `pty/session.py` (fields near `created_at`), `pty/manager.py` (`create_session`, `close_session`), new `pty/access.py`, `routes/terminal.py`, `websockets/terminal.py`; new `apps/web-server/tests/test_terminal_ownership.py` (locate the existing `test_ws_all_task_access.py` and put it beside it). Tests as spec "Tests". Check: `PATH=/mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin:$PATH pytest <dir>/test_terminal_ownership.py <dir>/test_ws_all_task_access.py <dir>/test_ws_task_access.py -q` plus any existing terminal/pty tests (`grep -ril "terminal\|pty" tests`).
   Traps: plain names in parenthesised imports (ruff vs `standards/ruff.toml` `as` sorting); `RUF006` noqa for fire-and-forget tasks; the autonomy matrix is regenerated, never hand-merged; vendored `artifact_store.py` untouched; no `global`; never log PTY output or tokens.
2. **PFactory** (lead). Same, branch `fix/3740-terminal-owner-binding` off `origin/dev`. PF specifics: `routes/terminal.py` uses `confine_to_workspace`, `.projects.load_projects`, `error_message`; `pty/manager.py` imports `unseal_profiles`; `authorize_project_for_user` here always enforces. Check with `PATH=.../PFactory/apps/web-server/.venv/bin:$PATH` (fall back `apps/backend/.venv`); confirm every listed file was collected and ran (conftest ignores WebSocket modules when deps are missing: check the pass count).
3. **TFactory** (lead). Same. TF specifics: manager raises `InputRejectedError` for the capacity limit and `routes/terminal.py` catches it (keep that, add the duplicate branch first); `._specpath.safe_component`; `server.config` already has the standalone `_authorize_project`. Check as step 2 with TF's venv.
4. **Lead.** Review each diff against this plan, rerun each check, commit per repo (messages cite "Plan step N: plan/2026-11-16-3740-terminal-owner-binding.md"). Per repo run the CI lint gates against `origin/dev` (AIF: `scripts/cq_ratchet.py` ruff and mypy as in `.github/workflows/cq-ratchet.yml`, plus `ruff format --check`; PF/TF: `scripts/ratchet_lint.py --base origin/dev --package apps/backend --package apps/web-server --package scripts` and ruff format). `codex review --base origin/dev` per repo, at most 3 rounds (security fix). Rebase on `origin/dev` again before the final push. Push, PRs into `dev` (three) and this docs PR into `main`, each linking the three artifacts and naming that the lead implemented all steps and Codex reviewed, `Refs olafkfreund/Factory#3740`.

## Tests

Per repo: the new `test_terminal_ownership.py` and the touched/neighbouring WS tests, from the repo venv; full backend suite if feasible, otherwise stated in the PR.

## Rollback

Revert the PRs. Terminals return to token-only access. No data or schema change; sessions are in memory.

## Operator notes

- Non-service users lose projectless (home directory) terminals; service principal and local UI are unchanged.
- PF/TF JWT users get strict project authorization on terminals regardless of `RBAC_ENFORCE_TASK_ROUTES`.
- A terminal is still a login shell of the server's OS user: this is access control, not tenant isolation.
