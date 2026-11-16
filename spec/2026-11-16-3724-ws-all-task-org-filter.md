---
status: draft
issue: 3724
intent: intent/2026-11-16-3724-ws-all-task-org-filter.md
---

# Spec: Org filter on /ws/logs and /ws/progress

## Design

In each of AIFactory, PFactory and TFactory, `server/websockets/task_access.py` gains a standalone `class AllTaskSocketAccess` (the three `TaskSocketAccess` classes differ in field names and in how they check, so inheriting would only work in AIFactory). It reuses the module helpers (`authenticate_websocket`, `_ws_extract_token`, `_ws_acw_principal`, `_KEY_RECHECK_SECONDS`) and the repo's existing per-project check, parametrised by project id: AIF factors the body of `_authorized` into a module function that returns a bool and does not close; PF/TF give `_authorize` an optional `project_id` argument defaulting to `self.project_id`.

- `__init__(websocket)`: `user`, `key_token`, `last_check`.
- `connect() -> bool` (before `accept()`): `authenticate_websocket`; `WebSocketAuthError` returns `False`; any other exception closes 4003 and returns `False`. No project check yet. For an `acw_` token with an `api_key_id` principal, keeps the token.
- `recheck() -> bool`: no-op unless a key token is held and `_KEY_RECHECK_SECONDS` have passed; then `_ws_acw_principal(token)`: `None` or an exception closes 4001 and returns `False`; otherwise `user` is replaced by the fresh principal and the timer reset. No project check here; projects are checked per task.
- `async readable(task_ids) -> set[str]`: the subset of `task_ids` the caller may read. `user is None` (legacy token, `DISABLE_AUTH`) and the service principal get all of them. Anyone else: a task id that is not `<project>:<spec>` (both parts non-empty) is dropped; otherwise the project is checked once per distinct project per call with `authorize_project_for_user` and the same strictness as the per-task class (key always strict; JWT strict in AIF, and in PF/TF only when `RBAC_ENFORCE_TASK_ROUTES` is on; shadow mode logs the would-deny with `sanitize_log` and keeps the task). Strict principals fail closed on any exception: the project is dropped, the socket stays open.

`logs.py` and `progress.py`, the all-task handlers:

- Replace `verify_websocket_token` with `access = AllTaskSocketAccess(websocket)`; `if not await access.connect(): return`.
- Keep a local `allowed: set[str]`. `update_subscriptions()` first awaits `access.recheck()` (return `False` ends the handler), then `allowed = await access.readable(agent_service.get_running_tasks())`, and registers callbacks only for `allowed`.
- The refresh no longer lives only in the `TimeoutError` branch. Each loop turn waits at most the time left until the next refresh (`max(0, 5 - elapsed)`), then, before sending a dequeued message or a heartbeat, runs the refresh if 5 s have passed. So nothing is sent on an allowed-set older than 5 s plus the refresh's own duration, even under continuous traffic. Heartbeats stay on the wait timeout. Both handlers also refresh once before the `connected` message, so `/ws/logs` subscribes at connect instead of after the first quiet 5 s.
- A message whose `task_id` is not in the (fresh) `allowed` is dropped before sending, so queued messages from a task denied at the refresh cannot drain.
- `/ws/progress` sends `running_tasks` (connected and heartbeat) as the sorted-as-before list filtered to `allowed`.
- `/ws/terminal/{id}` is not changed (see the intent); a follow-up issue records the missing owner binding.

No frontend change: the message shapes are the same.

**Factory#3714.** The remaining box (AIF has no `_jwt_strict()`) is closed with a written reason: AIF has no shadow mode, JWTs are always strict, and a function that returns `True` would only add indirection; the three repos now share the same shape (strictness is inline in AIF, a function in PF/TF where the flag exists). Then close #3714.

## Alternatives rejected

- Filter at send time only, keep subscribing to everything: wastes callbacks and does not cover `running_tasks`.
- Per-message project check against the database: a query per log line. The 5 s decision is the same freshness the intent asks for.
- A standalone helper that does not share `TaskSocketAccess`: duplicates the key re-validation.
- Binding terminals to an owner now: needs a data-model decision; out of scope.

## Risks

- Shadow mode (PF/TF JWT, flag off) leaves cross-org streams open, as on the per-task sockets; documented.
- A task that starts or a membership granted between refreshes is picked up at the next refresh (at most 5 s late), as before.
- `authorize_project_for_user` writes an audit event on each denial; with a refresh every 5 s a denied project is audited every 5 s per socket. Dropped projects are skipped without calling it again within a refresh, but not across refreshes. Accepted; revisit if the audit log fills.
- `readable` opens a DB session per distinct project per refresh.

## Verification

New tests per repo (`tests/test_ws_all_task_access.py`, real `TestClient.websocket_connect`, stubs in the style of `test_ws_task_access.py`), for both `/ws/logs` and `/ws/progress`: member sees own project's task and not another org's (no callback registered for it, not in `running_tasks`); a message from a task not in `allowed` is not delivered; bare task id hidden; legacy/service sees all; key socket for another org sees nothing from it; membership removed then the next refresh unsubscribes; a refresh still runs while a busy task keeps the queue non-empty; lookup exception hides the project (strict); key revoked at re-check closes 4001; PF/TF shadow mode keeps the stream and logs; the flag on drops it. A deterministic timing test with a patched clock: a message just before the 5 s deadline is sent, one just after a denial-producing refresh is dropped, and a heartbeat after the deadline carries the fresh `running_tasks`. A key that survives a re-check and keeps streaming, then is revoked and closes 4001. Plus the existing `test_ws_task_access.py`, `test_ws_org_routing.py` and `test_ws_acw_auth.py` stay green, and each repo's lint gates.
