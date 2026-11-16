---
status: approved
issue: 3703
intent: intent/2026-11-16-3703-ws-task-org-access.md
---

# Spec: org access on per-task WebSockets, and WS membership freshness

Prior design: `plan/2026-11-07-3679-ws-event-org-filtering.md` (its deviation sections included). Same change in AIFactory, PFactory and TFactory unless a bullet says otherwise.

## Design

### 1. Per-task sockets (#3703)

New module `apps/web-server/server/websockets/task_access.py` with one class, `TaskSocketAccess(websocket, task_id)`, used by the per-task handlers `task_logs_websocket` (`logs.py`) and `task_progress_websocket` (`progress.py`). The all-task sockets `/ws/logs`, `/ws/progress` and `/ws/terminal/*` are unchanged.

- `await access.connect() -> bool`, called where `verify_websocket_token` is called today (before `accept`):
  1. `user = await authenticate_websocket(websocket)`. A `WebSocketAuthError` returns `False` (the socket is already closed 4001). This also accepts `acw_` keys, which `verify_websocket_token` never did.
  2. `user is None` (legacy token or `DISABLE_AUTH`, the service principal) allows.
  3. Otherwise the task id must be `<project>:<spec>` with both parts non-empty; a bare id is denied (`close(4003)`), because a bare id proves no project ownership and the handlers subscribe to the original id. Then `authorize_project_for_user(user, project_id, db)` runs on a short `async_session_factory()` session.
  4. Mode and failures: a key principal (`api_key_id` set) is always strict, and any error (denial or a registry, session or query failure) closes 4003 (fail closed). A JWT principal follows REST: AIF always strict, same as keys. PF and TF strict only when `get_settings().RBAC_ENFORCE_TASK_ROUTES` is on; with the flag off, both an authorization denial and an unexpected failure are logged (`logger.warning`, ids only) and the connect is allowed, as REST's shadow mode does (TF `project_authz.py` fails open in shadow). With the flag on, any error closes 4003.
- `await access.recheck() -> bool`, called at the top of each loop iteration of the two handlers. It is a no-op unless the socket's token starts with `acw_` and its principal has `api_key_id`. Every `_KEY_RECHECK_SECONDS = 300` (monotonic) it re-runs `_ws_acw_principal(token)` and the project check against the fresh principal. A `None` principal or a denial closes 4001 and returns `False`; the handler returns, its `finally` unregisters. A raising validator is already `None` (#312).
- The two handlers receive loops already wake on a 30 s timeout, so no new timer is needed. The re-check fires within one wake-up of the interval.

### 2. `/ws/events` membership freshness (#3705)

In `events_websocket` of each factory, the periodic block runs for every socket that has a user id, not only key sockets. Every `_KEY_RECHECK_SECONDS`:
- a key socket re-validates `_ws_acw_principal(key_token)`; `None` closes 4001 (unchanged);
- then `_load_org_ids(client, user_info)` reloads memberships for key and JWT sockets alike.

`update_client_orgs` is left as is (no production caller; the timer is the mechanism). A removed member stops receiving an org's events within 5 minutes plus one receive timeout.

Reject a token with no `sub`: in `authenticate_websocket` (`server/auth.py`), after `_try_decode_jwt` succeeds, `if not jwt_payload.get("sub")`: `close(4001, "Unauthorized")` and `raise WebSocketAuthError`. The REST middleware is unchanged.

### 3. #3714 leftovers

- **Start-route tests** (all three): tests call `start_cli_login`, `start_cli_login_terminal` and `start_github_auth` with `request.state.user` set to a user principal and assert the emitter receives that principal (user-scoped delivery), and with a service principal assert service-only delivery. Closes the box.
- **Key re-check discards the fresh principal** (all three): on a good re-check, `user_info = principal`; `client.key_org_id = principal.get("org_id")`; `client.user_id = principal.get("id")`, then `_load_org_ids` with the fresh `user_info`. Keys are mutable in place only if the validator returns a different org or owner, so the test patches the validator to do that.
- **JWT without `sub`**: closed by section 2.
- **`_payload_org`** (AIF): use the PF/TF form, `payload.get("org_id") or nested`, so `{"org_id": "", "data": {"org_id": "A"}}` resolves to A in all three. Test in AIF.
- **AIF `_jwt_strict()`**: not done. The issue says extract it only if AIF gets a shadow mode; it will not. The box is ticked "not needed" with that reason.

### 4. Frontends (#3704)

`onTaskLogsStream` in each `lib/api-adapter.ts` passes `payload.projectId` as a third callback argument (type in `shared/types/ipc.ts`: `(specId, chunk, projectId?: string)`). `useTaskDetail.ts` (all three) and `pipeline/useCardLogs.ts` (PF) ignore an event unless `projectId` equals the selected project's id AND `specId` matches. An event without `projectId` is ignored: the backend adds it whenever the task id is `<project>:<spec>`, which is the only form the frontends use, and a missing id in shadow mode would otherwise mix projects again. `useTaskDetail`'s effect gets `selectedProject?.id` in its dependency array so the callback never holds a stale project. Frontend tests where the repo already has a hook test harness (including a project switch with the same task ids).

## Alternatives rejected

- **Reuse `verify_websocket_token` and add only the project check.** It yields no identity, so the check has nobody to authorize.
- **Call `update_client_orgs` from the membership routes (#3705 option A).** Pod-local, and only on the pod that handled the request; the timer also covers other pods and bulk or SQL removals.
- **Re-check JWT sockets by decoding the token again.** The token stays valid after a membership change; only the `OrgMember` rows change.
- **Make PF/TF JWT per-task sockets strict now.** Contradicts the #3679 owner decision (REST mode).
- **Accept events with no `projectId` in the frontend.** In PF/TF shadow mode a former broadcast reaches JWT sockets, so an unscoped chunk would still mix projects.
- **Treat a bare task id as its own project id on the per-task sockets** (as `TaskAccessChecker` does for REST). The socket subscribes to the bare id itself, which nothing ties to that project.

## Risks

- New strictness for JWT users on AIF per-task sockets: a user whose project has no `org_id` (legacy) now gets 4003 on the log socket, as REST already gives 403 on the same project's logs route.
- `acw_` keys can now attach to per-task sockets; they are confined by the project check and re-checked.
- A failed membership lookup at re-check time leaves a JWT socket with no orgs for up to 5 minutes (fails closed in AIF and PF/TF strict mode; in PF/TF shadow mode JWT sockets stay lenient).
- Per-task sockets add one DB session per connect.

## Verification

Per factory, tests through the real endpoints with `TestClient.websocket_connect` (auth and DB stubbed as in `tests/test_ws_acw_auth.py`):
- every case below runs against both the logs and the progress endpoint;
- member allowed, bare task id 4003 (even when it equals an accessible project id), non-member 4003, other-org key 4003, service allowed, unknown project denied; PF/TF JWT non-member allowed with the flag off and denied with it on;
- key re-check with `_KEY_RECHECK_SECONDS` patched to 0: validator returns `None` closes 4001; owner membership removed closes 4001; a raising validator closes 4001;
- `/ws/events`: JWT member removed between two re-checks stops receiving; fresh principal rebinds `key_org_id`; no-`sub` token closed 4001;
- AIF `_payload_org` consistency; start-route principal tests;
- frontends: `npm test`/`vitest` for the touched files, `tsc --noEmit`, lint.
Each factory's CI lint gates (ruff, ratchet) run against `origin/dev`.
