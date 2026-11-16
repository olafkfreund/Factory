---
status: draft
issue: 3740
intent: intent/2026-11-16-3740-terminal-owner-binding.md
---

# Spec: bind terminal sessions to their owner and project

## Design

Same change in AIFactory, PFactory, TFactory (`apps/web-server/server`).

**Binding.** `PTYSession` gets `owner_id: str | None` and `project_id: str | None` (set at create, not serialized to clients). `PTYManager.create_session(..., owner_id=None, project_id=None)` stores them. If `session_id` is given and a live session with that id exists, it raises `ValueError` under the manager lock before spawning (route: 409); a dead one is closed and replaced.

**Rule** (`pty/access.py`, new, one small module per repo):

- `unrestricted(user)`: `is_service_principal(user)`. WebSockets additionally treat `user is None` (legacy token, auth disabled) as unrestricted, as `AllTaskSocketAccess.readable` does. REST `None` is denied.
- `async project_ok(user, project_id) -> bool`: `authorize_project_for_user` on an `async_session_factory()` session; `False` on denial or any exception (fail closed). Strict in all three repos: a terminal is a shell, so PF/TF do not use the `RBAC_ENFORCE_TASK_ROUTES` shadow mode here.
- `async may_use(user, session) -> bool`: unrestricted, or `user["id"] == session.owner_id` and `project_ok(user, session.project_id)`.
- `async authorize_path(user, path)`: unrestricted passes; else the path must resolve to a registered project's path and `project_ok` must hold, otherwise HTTP 403.

**REST** (`routes/terminal.py`):

- Create: non-service callers must send `projectId` (400 otherwise), `project_ok` or 403, the directory is the registered project path (`cwd`/`projectPath` ignored, the existing `within_roots` confinement still runs); session stores `owner_id=user["id"]`, `project_id`. Service callers keep today's behaviour and store `owner_id=user.get("id")` and the given project id. `ValueError` from the manager gives 409.
- List and `/sessions`: filtered with `may_use`; `/sessions` also honours `project` (matches `session.project_id`) for everyone.
- `GET/DELETE /{id}`, `/resize`, `/buffer`, `/alive`: a missing or not-`may_use` session is the same 404 (`/alive` returns `data: false`, as for a missing one). `/buffer` ignores the body `projectId` for non-service callers and saves under the session's own project.
- `/worktrees` (GET, POST, DELETE) and `DELETE /sessions?project=`: `authorize_path` on the named path. `DELETE /sessions` without `project` and `POST /cleanup`: 403 for non-service callers.

**WebSocket** (`websockets/terminal.py`): replace `verify_websocket_token` with `authenticate_websocket` (`WebSocketAuthError` returns; this also admits per-user `acw_` keys). After `accept`, a session that is missing or fails `may_use` gets the existing "not found" error frame and close 4004. For restricted principals a watcher task re-runs `may_use` every 5 s (`_RECHECK_SECONDS`) and, for `acw_` keys, re-validates the key with `_ws_acw_principal` every 300 s; on loss it closes 4003 (denied) or 4001 (key revoked). The watcher is cancelled in `finally` with the reader.

**Tests** (per repo, `tests/test_terminal_ownership.py`, fake manager session objects, stubbed authorization in the style of `tests/test_ws_all_task_access.py`; no real shell):

- REST: owner lists, gets, resizes, closes own; another user gets 404 on each, and list/`/sessions` omit it; create without project 400, for an unauthorized project 403, `cwd` override ignored; duplicate live id 409; buffer lands in the session's project not the body's; worktree and clear-with-project 403 for an unauthorized path; clear-all and cleanup 403; service principal does all of it.
- WS: owner connects; other user, other-org key get 4004; legacy-token connects; membership removed mid-session closes 4003 (patched `_RECHECK_SECONDS`); revoked key closes 4001.

## Alternatives rejected

- **Admin-only terminals.** Breaks the working local UI and org users who legitimately use a project terminal.
- **Project authorization alone (no owner binding).** Any member of a project could attach to a colleague's shell and its history.
- **A shared access class reused by WS and REST.** The REST callers have a request principal, the WS callers a socket; a plain function pair is smaller.
- **Honouring PF/TF `RBAC_ENFORCE_TASK_ROUTES` shadow mode.** A silent allow on a shell defeats the fix.
- **Filesystem isolation per tenant.** Out of scope (intent); needs a sandbox.

## Risks

- PF/TF JWT users whose org membership is not set up lose their terminals (strict by design). The service principal and the local UI are unaffected.
- Sessions created before the upgrade have no owner: only the service principal can reach them.
- The 5 s recheck costs one membership query per live terminal per 5 s per restricted user.
- Vendored files and the autonomy matrix are untouched.

## Verification

The new test file per repo, plus the repo's existing terminal/WS tests (`test_ws_task_access.py`, `test_ws_all_task_access.py`, existing terminal tests), run with the repo venv. CI lint gates (cq-ratchet for AIF, ratchet_lint for PF/TF, ruff format). `codex review --base origin/dev` per repo.
