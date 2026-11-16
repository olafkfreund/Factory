---
status: draft
issue: 3703
spec: spec/2026-11-16-3703-ws-task-org-access.md
coders:
  1: codex   # AIF backend: security predicate, small tricky logic
  2: agy     # PF backend: port of step 1's design onto PF (shadow-mode flag), larger edit set
  3: codex   # TF backend: same port, TF has no relay
  4: lead    # frontends: three one-line matcher edits plus types
reviewers:
  - codex    # authored steps 1 and 3; reviews cross-repo consistency
  - agy      # authored step 2; independent read on fail-closed coverage
# Each reviewer authored steps, so the independent check is the lead's own read against this plan plus the other reviewer.
---

# Plan: org access on per-task WebSockets, and WS membership freshness

Closes Factory#3703, #3705, #3714, #3704. The decisions below are the approved spec; this file is self-contained.

## Approved decisions

**Per-task sockets.** New `apps/web-server/server/websockets/task_access.py` in AIFactory, PFactory and TFactory:
- `class TaskSocketAccess(websocket, task_id)` with `async connect() -> bool` and `async recheck() -> bool`; `_KEY_RECHECK_SECONDS = 300` (monotonic clock, so tests patch `time.monotonic` or the constant).
- `connect()` (before `websocket.accept()`): `user = await authenticate_websocket(websocket)`; `WebSocketAuthError` returns `False`. `user is None` (legacy token, `DISABLE_AUTH`) allows. Else the task id must be `<project>:<spec>` with both parts non-empty, otherwise deny (a bare id proves no project ownership; do not treat it as a project id). Then `authorize_project_for_user(user, project_id, db)` on an `async_session_factory()` session. Deny means `await websocket.close(code=4003)` and return `False`. Strict principals (any `api_key_id` key; any JWT in AIF; a JWT in PF/TF when `get_settings().RBAC_ENFORCE_TASK_ROUTES` is true) deny on an authorization denial AND on any other exception (fail closed). A JWT in PF/TF with the flag off: log the would-deny or the failure with `logger.warning` (project id and user id only, via `sanitize_log`) and allow, as REST shadow mode does. The flag is read on each call.
- `recheck()`: no-op (`True`) unless the token (`_ws_extract_token`) starts with `acw_` and the principal has `api_key_id`. When due: `principal = await _ws_acw_principal(token)`; `None` or a denied project check with the fresh principal closes 4001 and returns `False`; else store the fresh principal and reset the timer.
- `task_logs_websocket` and `task_progress_websocket` (`logs.py`, `progress.py`): replace `verify_websocket_token` with `access = TaskSocketAccess(websocket, task_id)`; `if not await access.connect(): return`; then `accept()` as today; call `if not await access.recheck(): return` at the top of each `while True` iteration. `/ws/logs`, `/ws/progress`, `/ws/terminal/*` stay on `verify_websocket_token`.

**`/ws/events`** (`events.py`, each factory):
- The periodic block runs for every socket with a user id. Every `_KEY_RECHECK_SECONDS`: if `key_token`, `principal = await _ws_acw_principal(key_token)`; `None` closes 4001 and breaks (unchanged), else `user_info = principal`, `client.key_org_id = principal.get("org_id")`, `client.user_id = principal.get("id")`. Then `await _load_org_ids(client, user_info)` for key and JWT sockets. `_load_org_ids` itself stays.
- `authenticate_websocket` (`server/auth.py`): after the JWT decode, if `jwt_payload.get("sub")` is falsy: `await websocket.close(code=4001, reason="Unauthorized")` and `raise WebSocketAuthError("Token has no subject")`. The REST middleware is unchanged.
- AIF `_payload_org` (`websockets/event_bus.py` ~:151) becomes `payload.get("org_id") or nested` like PF/TF.
- AIF `_jwt_strict()`: not extracted (no shadow mode in AIF).

**Frontends.** `lib/api-adapter.ts` `onTaskLogsStream` passes `payload.projectId` as a third callback argument; `shared/types/ipc.ts` types it `(specId: string, chunk: TaskLogStreamChunk, projectId?: string) => void`. `components/task-detail/hooks/useTaskDetail.ts` returns early unless `projectId === selectedProject?.id` (and `specId` matches); `selectedProject?.id` is added to that effect's dependency array. PF `components/pipeline/useCardLogs.ts` returns early unless `projectId` equals the effect's `projectId`. An event with no `projectId` is ignored (the backend adds it for every `<project>:<spec>` task id).

## Steps

1. **AIFactory backend** (codex). Worktree `scratchpad/teams/fws/AIFactory`, branch `fix/3703-ws-task-org-access` off `origin/dev`.
   - Create `websockets/task_access.py`; edit `websockets/logs.py:17-30`, `websockets/progress.py:17-36`; edit `websockets/events.py` (`events_websocket`, the loop at ~:196-211); edit `auth.py:~470` (`authenticate_websocket`); edit `websockets/event_bus.py:151` (`_payload_org`).
   - Tests: new `tests/test_ws_task_access.py` (real `TestClient.websocket_connect`, stubs in the style of `tests/test_ws_acw_auth.py`), every case against both the logs and the progress endpoint: member allowed; bare task id 4003 even when it equals an accessible project id; registry/session/query exception at connect and at re-check closes (strict); non-member 4003; other-org key 4003; service/legacy allowed; unknown project 4003; key owner removed after the interval closes 4001; validator `None` closes 4001; validator raising closes 4001. Append to `tests/test_ws_org_routing.py`: JWT socket stops receiving after a membership removal at the re-check; the fresh principal rebinds `key_org_id`/`user_id`; token without `sub` closed 4001; `_payload_org({"org_id": "", "data": {"org_id": "A"}}) == "A"`; `start_cli_login`, `start_cli_login_terminal` and `start_github_auth` with a user principal in `request.state.user` and with a service principal.
   - Check: `PATH=<main AIFactory>/apps/backend/.venv/bin:$PATH pytest tests/test_ws_task_access.py tests/test_ws_org_routing.py tests/test_ws_acw_auth.py tests/test_event_bus.py tests/test_auth_hardening.py -q` (use a venv built from the branch's requirements if `mcp` is too old; run with no GitHub token in the environment).
   - Traps: tests put `apps/web-server` and `apps/backend` on `sys.path`; `RUF006` noqa pattern for fire-and-forget tasks; ruff sorting of `as` aliases: use plain names; do not edit `artifact_store.py`; the generated autonomy matrix is regenerated, never hand-merged.
2. **PFactory backend** (agy). Worktree `.../PFactory`, off `origin/dev`. The same as step 1, with these differences: `events.py` loop at ~:489-505; `auth.py:~487`; `_payload_org` already uses `or`; `_jwt_strict()` flag semantics for JWT principals in `task_access.py`; tests also cover the flag off (JWT non-member allowed, JWT with an exception allowed and logged, key non-member denied) and on (JWT non-member 4003, exception 4003). Check: `pytest tests/test_ws_task_access.py tests/test_ws_org_routing.py tests/test_ws_acw_auth.py tests/test_ws_relay.py -q`.
   - Traps: PF ruff is stricter (no `global`, PLW0603); mypy strict is ratcheted on changed files, so annotate fully; the commit hook may autofix staged files.
3. **TFactory backend** (codex). Worktree `.../TFactory`, off `origin/dev`. As step 2 on TF: `events.py` loop at ~:287-312, `auth.py:~419`; `load_projects` there is a lazy import in `events.py`; `authorize_project_for_user` raises on denial (the REST mode switch lives in `ProjectAccessChecker.check`, so `task_access.py` applies the flag itself as above). Check: `pytest tests/test_ws_task_access.py tests/test_ws_org_routing.py tests/test_ws_acw_auth.py -q`; use `nix develop -c` if imports fail. Traps: no unused imports (F401); TF's lazy-import style.
4. **Frontends** (lead; agy may take it if idle). Edit `lib/api-adapter.ts`, `shared/types/ipc.ts`, `components/task-detail/hooks/useTaskDetail.ts` in all three, plus PF `components/pipeline/useCardLogs.ts`. Add tests where a vitest harness exists: wrong project, missing `projectId`, and a project switch with identical task ids. Check in each `apps/frontend-web`: `npx tsc --noEmit`, `npx vitest run <touched tests>`, `npm run lint` as CI does.
5. **Lead.** Review each implementer diff, rerun its check, commit per step. Per repo run the CI lint gates against `origin/dev` (AIF: ruff check/format + `scripts/cq_ratchet.py`; PF/TF: `scripts/ratchet_lint.py --base origin/dev`, ruff format). Final review: `codex review --base origin/dev` plus agy and the lead's read against this plan; at most 2 rounds (security fix: 3). Push, open PRs into `dev` (three) and this docs PR into `main`; each PR links all three artifacts, names who did each step, and says "Refs olafkfreund/Factory#3703" (also #3705, #3714, #3704). Tick the #3714 boxes in a comment on the issue after merge.

## Tests

As in each step's check line, then each repo's full backend `tests/` run that CI runs (or the touched directory if the full run is infeasible locally; say so in the PR).

## Rollback

Revert the PRs. Per-task sockets go back to token-only auth, `/ws/events` JWT memberships back to connect-time, and the frontends back to `specId`-only matching. No data or schema change.

## Operator notes

- PF/TF JWT per-task sockets stay unfiltered until `RBAC_ENFORCE_TASK_ROUTES` is on.
- `/ws/logs` and `/ws/progress` (all tasks) still lack org filtering: new issue filed with these PRs.
