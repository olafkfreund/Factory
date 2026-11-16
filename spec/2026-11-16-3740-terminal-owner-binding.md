---
status: draft
issue: 3740
intent: intent/2026-11-16-3740-terminal-owner-binding.md
---

# Spec: bind terminal sessions to their owner and project

## Design

Same change in AIFactory, PFactory, TFactory (`apps/web-server/server`).

**Binding.** `PTYSession` gets `owner_id: str | None` and `project_id: str | None` (set at create, not serialized to clients). `PTYManager.create_session(..., owner_id=None, project_id=None)` stores them. If `session_id` is given and any session with that id exists, it raises `ValueError` under the manager lock before spawning (route: 409). `close_session(session_id, expected=None)` takes the session the caller authorized and closes only if the stored object is that one, so an id recycled during an await is never closed by the wrong caller.

**Rule** (`pty/access.py`, new, one small module per repo):

- `unrestricted(user)`: `is_service_principal(user)`. WebSockets additionally treat `user is None` (legacy token, auth disabled) as unrestricted, as `AllTaskSocketAccess.readable` does. REST `None` is denied.
- `async project_ok(user, project_id) -> bool`: `authorize_project_for_user` on an `async_session_factory()` session; `False` on denial or any exception (fail closed). Strict in all three repos: a terminal is a shell, so PF/TF do not use the `RBAC_ENFORCE_TASK_ROUTES` shadow mode here.
- `async may_use(user, session) -> bool`: unrestricted, or `user["id"] == session.owner_id` and `project_ok(user, session.project_id)`.
- `project_id_for_path(path) -> str | None`: the registered project (`load_projects()`) whose resolved path equals or contains the resolved `path` (longest match), else `None`. The existing frontends send filesystem paths (`cwd`, `projectPath`, `/sessions?project=<path>`), not ids, so this keeps their contract.
- `async authorize_path(user, path) -> str | None`: unrestricted returns the matched id or `None`; else the path must match a registered project and `project_ok` must hold, otherwise HTTP 403; returns the project id.

**REST** (`routes/terminal.py`):

- Create: the working directory is resolved exactly as today (`cwd`, `projectPath`, `projectId`, else home), then `within_roots` confinement runs. Non-service callers must land inside a registered project they pass `project_ok` for (`projectId` if given, else `project_id_for_path(cwd)`), otherwise 403: this covers a foreign `cwd`, a foreign `projectId`, and projectless terminals (home directory, e.g. onboarding), which stay service-only. The session stores `owner_id=user.get("id")` and that project id. Service callers keep today's behaviour; their project id is the given one or `project_id_for_path(cwd)` (may be `None`). `ValueError` from the manager gives 409. No frontend change.
- List and `/sessions`: filtered with `may_use`; `/sessions` also honours `project` for everyone: the value is a path or a project id, resolved with `project_id_for_path` (an id matching a registered project is taken as is), then compared with `session.project_id`.
- `GET/DELETE /{id}`, `/resize`, `/buffer`, `/alive`: a missing or not-`may_use` session is the same 404 (`/alive` returns `data: false`, as for a missing one); `DELETE` passes the authorized session as `expected`. `/buffer` ignores the body `projectId` for non-service callers and saves under the session's own project.
- `/worktrees` (GET, POST, DELETE) and `DELETE /sessions?project=`: `authorize_path` on the named path. `DELETE /sessions` without `project` and `POST /cleanup`: 403 for non-service callers.

**WebSocket** (`websockets/terminal.py`): replace `verify_websocket_token` with `authenticate_websocket` (`WebSocketAuthError` returns; this also admits per-user `acw_` keys). After `accept`, a session that is missing or fails `may_use` gets the existing "not found" error frame and close 4004. For restricted principals a watcher task re-runs `may_use` every 5 s (`_RECHECK_SECONDS`) and, for `acw_` keys, first re-validates the key with `_ws_acw_principal` on the same tick, using the fresh principal; a revoked key, a validator exception or a missing principal closes 4001, a failed `may_use` closes 4003. The watcher is cancelled in `finally` with the reader.

**Tests** (per repo, `tests/test_terminal_ownership.py`; a real `PTYManager` with `PTYSession.start` patched so no shell spawns; the real `may_use`/`authorize_path` rule over a patched project registry and membership stub, with `RBAC_ENFORCE_TASK_ROUTES=false` in PF/TF; WS in the style of `tests/test_ws_all_task_access.py`):

- Rule: REST `None` denied; `role: admin` without `is_service` denied; lookup exception denied; JWT member and per-user key owner allowed; org-mismatched key denied.
- REST: owner lists, gets, resizes, closes own; another user gets 404 on each, and list/`/sessions` omit it; create with a foreign `projectId` or foreign `cwd` 403, projectless 403, a path inside an authorized project 201 (no frontend change); duplicate id 409 with no shell spawned; delete of an id recycled between authorization and close leaves the new session alive; `/sessions?project=<path>` filters; buffer lands in the session's project not the body's; worktree and clear-with-project 403 for an unauthorized path; clear-all and cleanup 403; service principal does all of it.
- WS: owner connects; other user, other-org key get 4004; legacy-token connects; membership removed mid-session closes 4003 (patched `_RECHECK_SECONDS`); revoked key and validator exception close 4001 within `_RECHECK_SECONDS`.

## Alternatives rejected

- **Requiring `projectId` on create.** The frontends send paths, so this would give every human user a 400.
- **Replacing dead sessions on a recycled id.** Contradicts the intent and races with an in-flight authorized delete.
- **Admin-only terminals.** Breaks the working local UI and org users who legitimately use a project terminal.
- **Project authorization alone (no owner binding).** Any member of a project could attach to a colleague's shell and its history.
- **A shared access class reused by WS and REST.** The REST callers have a request principal, the WS callers a socket; a plain function pair is smaller.
- **Honouring PF/TF `RBAC_ENFORCE_TASK_ROUTES` shadow mode.** A silent allow on a shell defeats the fix.
- **Filesystem isolation per tenant.** Out of scope (intent); needs a sandbox.

## Risks

- PF/TF JWT users whose org membership is not set up lose their terminals (strict by design). The service principal and the local UI are unaffected.
- Sessions created before the upgrade have no owner: only the service principal can reach them.
- The 5 s recheck costs one membership query (and for keys one key lookup) per live terminal per 5 s per restricted user.
- Non-service users lose projectless (home directory) terminals, e.g. onboarding's embedded terminal; the service principal keeps them.
- Vendored files and the autonomy matrix are untouched.

## Verification

The new test file per repo, plus the repo's existing terminal/WS tests (`test_ws_task_access.py`, `test_ws_all_task_access.py`, existing terminal tests), run with the repo venv. CI lint gates (cq-ratchet for AIF, ratchet_lint for PF/TF, ruff format). `codex review --base origin/dev` per repo.
