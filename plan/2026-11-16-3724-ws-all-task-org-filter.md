---
status: approved
issue: 3724
spec: spec/2026-11-16-3724-ws-all-task-org-filter.md
coders:
  1: codex   # AIF: small tricky security logic and timing loop
  2: codex   # PF: same port, shadow-mode flag
  3: codex   # TF: same port
reviewers:
  - codex    # authored steps 1-3; the lead's own read against this plan is the independent check
# agy is off by owner decision for this round.
---

# Plan: org filter on /ws/logs and /ws/progress

Closes Factory#3724 and (with a written reason) #3714. The decisions below are the approved spec; this file is self-contained.

## Approved decisions

In AIFactory, PFactory, TFactory, `apps/web-server/server/websockets/task_access.py` gets a standalone `AllTaskSocketAccess` (do not inherit `TaskSocketAccess`: the three differ in field names and check signatures):

- `__init__(websocket)`; fields `user`, `key_token`, `last_check` (monotonic).
- `async connect() -> bool`: `authenticate_websocket`; `WebSocketAuthError` -> `False`; other exception -> `close(4003)`, `False`. No project check. Keep the token when it starts with `acw_` and the principal has `api_key_id`.
- `async recheck() -> bool`: no-op unless a key token is held and `_KEY_RECHECK_SECONDS` elapsed; then `_ws_acw_principal(token)`: `None` or exception -> `close(4001)`, `False`; else `self.user = fresh principal`, reset timer. No project check.
- `async readable(task_ids) -> set[str]`: `user is None` or service principal (`is_service_principal`) -> all. Else drop ids that are not `<project>:<spec>` with both parts non-empty; check each distinct project once with `authorize_project_for_user` on an `async_session_factory()` session, via the repo's existing per-project check parametrised by project id (AIF: factor the body of `_authorized` into a module function returning bool that never closes the socket, and have `_authorized` call it; PF/TF: optional `project_id` argument on `_authorize`, default `self.project_id`). Strictness as the per-task class: key (`api_key_id`) always strict; JWT strict in AIF, and in PF/TF when `get_settings().RBAC_ENFORCE_TASK_ROUTES` is true (read per call). Strict: denial or any exception drops the project. Shadow (PF/TF JWT, flag off): `logger.warning` with `sanitize_log` project and user id and keep the task.

`websockets/logs.py` (`all_logs_websocket`) and `websockets/progress.py` (`all_progress_websocket`), both:

- `access = AllTaskSocketAccess(websocket)`; `if not await access.connect(): return`; then `accept()`. Remove the now-unused `verify_websocket_token` import only if no other endpoint in the file uses it (`/ws/terminal` is a separate file and stays).
- Local `allowed: set[str]`. `async def refresh_subscriptions() -> bool`: `if not await access.recheck(): return False`; unregister all callbacks; `allowed = set(await access.readable(agent_service.get_running_tasks()))` (nonlocal); register callbacks only for `allowed`; return `True`.
- Call it once before the `connected` message (`running_tasks` in that message is `sorted`-as-before order filtered to `allowed`; keep the existing list order, i.e. `[t for t in running if t in allowed]`).
- Loop: `timeout = max(0.0, 5.0 - (loop.time() - last_refresh))`; `wait_for(queue.get(), timeout)`; on `TimeoutError` the item is `None`. Then, `if loop.time() - last_refresh >= 5.0`: `if not await refresh_subscriptions(): return`; `last_refresh = loop.time()`. Then: `None` -> send the heartbeat (progress: `running_tasks` filtered to `allowed`); a message whose `task_id` is not in `allowed` -> skip; else send as today. `finally` unregisters as today.

No frontend change. `/ws/terminal/{id}` unchanged; a follow-up issue records the missing owner binding.

## Steps

1. **AIFactory** (codex). Worktree `scratchpad/teams/f3724/AIFactory`, branch `fix/3724-ws-all-task-org` off `origin/dev`. Edit `websockets/task_access.py`, `logs.py:~83-154`, `progress.py:~100-179`. New `tests/test_ws_all_task_access.py` (real `TestClient.websocket_connect`, stubs in the style of `tests/test_ws_task_access.py`), for `/ws/logs` and `/ws/progress`: member sees own project and not another org's (no callback registered, absent from `running_tasks`); a queued message from a task denied at the refresh is dropped; bare id hidden; legacy and service see all; other-org key sees nothing; membership removed then next refresh unsubscribes; refresh still runs under continuous traffic; patched-clock deadline test (message just before the deadline sent, after a denying refresh dropped, heartbeat carries fresh `running_tasks`); lookup exception hides the project; valid key survives a re-check and keeps streaming, revoked key closes 4001.
   Check: from the worktree, `PATH=/mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin:$PATH pytest tests/test_ws_all_task_access.py tests/test_ws_task_access.py tests/test_ws_org_routing.py tests/test_ws_acw_auth.py -q` (no GitHub token in the env).
   Traps: tests put `apps/web-server` and `apps/backend` on `sys.path`; use plain names in parenthesised imports (ruff vs standards/ruff.toml `as` sorting); `RUF006` noqa for fire-and-forget tasks; the generated autonomy matrix is regenerated, never hand-merged; do not edit vendored `artifact_store.py`.
2. **PFactory** (codex). As step 1 on PF (`task_access.py` has `_jwt_strict()`, `_task_project_id`, `_key_token`). Extra tests: flag off (JWT non-member keeps the stream and logs a warning; JWT exception keeps it; key non-member dropped) and on (JWT non-member dropped). Check: with `PATH=/mnt/code/Source-home/GitHub/PFactory/apps/web-server/.venv/bin:$PATH` (fall back to `apps/backend/.venv`), `pytest tests/test_ws_all_task_access.py tests/test_ws_task_access.py tests/test_ws_org_routing.py tests/test_ws_acw_auth.py tests/test_ws_relay.py -q`; the run must collect and execute every listed file (conftest silently ignores WebSocket modules when web-server deps are missing: check the pass count, not just exit 0). Traps: no `global` (PLW0603); fully annotate (mypy ratchet on changed files); the commit hook may autofix staged files.
3. **TFactory** (codex). As step 2 on TF (`_authorize` raises on denial; strictness inline in `connect`; factor a small `_strict(principal)`). Check: with `PATH=/mnt/code/Source-home/GitHub/TFactory/apps/web-server/.venv/bin:$PATH` (fall back to `/mnt/code/Source-home/GitHub/TFactory/.venv/bin`), `pytest tests/test_ws_all_task_access.py tests/test_ws_task_access.py tests/test_ws_org_routing.py tests/test_ws_acw_auth.py -q`; confirm every listed file was collected and ran (TF conftest ignores WebSocket modules when deps are missing). Traps: no unused imports (F401); TF's lazy-import style.
4. **Lead.** Review each diff, rerun each check, commit per step. Per repo run the CI lint gates against `origin/dev` (AIF, as `.github/workflows/cq-ratchet.yml`: `apps/backend/.venv/bin/python scripts/cq_ratchet.py --base origin/dev --ruff apps/backend/.venv/bin/ruff --config standards/ruff.toml --paths 'apps/backend/*.py' 'apps/web-server/*.py' 'scripts/*.py'`, the same with `--tool mypy --mypy apps/backend/.venv/bin/mypy --config standards/mypy.ini`, and `ruff format --check`; PF/TF: `scripts/ratchet_lint.py --base origin/dev --package apps/backend --package apps/web-server --package scripts`, plus ruff format check; venvs are in the main clones, `apps/backend/.venv`). Final `codex review --base origin/dev` per repo and the lead's read against this plan, at most 2 rounds (security fix: 3). Push, PRs into `dev` (three) and this docs PR into `main`, each linking the artifacts, naming codex for steps 1-3, `Refs olafkfreund/Factory#3724`. Comment on #3714 and close it with this reason: AIF has no shadow mode, so JWT authorization there is always strict and an always-true `_jwt_strict()` would add indirection and no behaviour; PF has the function (it reads `RBAC_ENFORCE_TASK_ROUTES`), TF checks the flag inline, AIF inlines the rule; file a follow-up issue for terminal ownership.

## Tests

As in each check line, plus the repo's backend test directory CI runs, or the touched tests if the full run is infeasible locally (stated in the PR).

## Rollback

Revert the PRs. The all-task sockets go back to token-only auth. No data or schema change.

## Operator notes

- PF/TF JWT all-task sockets stay unfiltered until `RBAC_ENFORCE_TASK_ROUTES` is on.
- `/ws/terminal/{id}` still has no owner or project binding (follow-up issue).
