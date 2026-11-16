---
status: draft
issue: 3724
intent: intent/2026-11-16-3724-ws-all-task-org-filter.md
---

# Spec: Org filter on /ws/logs and /ws/progress

## Design

In each of AIFactory, PFactory and TFactory, `server/websockets/task_access.py` gains `class AllTaskSocketAccess(TaskSocketAccess)`, built on the #3703 class so the key re-validation and the project check are shared code.

- `__init__(websocket)`: calls the base with an empty task id; `project_id` is unused.
- `connect() -> bool` (before `accept()`): `authenticate_websocket`; `WebSocketAuthError` returns `False`; any other exception closes 4003 (AIF, as the base does). No project check at connect: there is no project yet. Stores `user` and, for an `acw_` key principal, `key_token`.
- `recheck()` (inherited): every 300 s re-validates the key; `None` or a validator error closes 4001. For the all-task class the project part of the re-check is a no-op (`_authorized` is overridden to return `True`), because projects are checked per task below.
- `async readable(task_ids) -> set[str]`: the subset of `task_ids` the caller may read. `user is None` (legacy token, `DISABLE_AUTH`) and the service principal get all of them. Anyone else: a task id that is not `<project>:<spec>` (both parts non-empty) is dropped; otherwise the project is checked once per distinct project per call with the same `authorize_project_for_user` call and the same strictness as `TaskSocketAccess` (key always strict; JWT strict in AIF, and in PF/TF only when `RBAC_ENFORCE_TASK_ROUTES` is on; shadow mode logs the would-deny with `sanitize_log` and keeps the task). Strict principals fail closed on any exception: the project is dropped, the socket stays open.

`logs.py` and `progress.py`, the all-task handlers:

- Replace `verify_websocket_token` with `access = AllTaskSocketAccess(websocket)`; `if not await access.connect(): return`.
- Keep a local `allowed: set[str]`. `update_subscriptions()` first awaits `access.recheck()` (return `False` ends the handler), then `allowed = await access.readable(agent_service.get_running_tasks())`, and registers callbacks only for `allowed`.
- The refresh no longer lives only in the `TimeoutError` branch. At the top of every loop turn, if 5 s have passed since the last refresh, run it. The 5 s `wait_for` timeout and the heartbeat stay. Both handlers also refresh once before the `connected` message, so `/ws/logs` subscribes at connect instead of after the first quiet 5 s.
- A message whose `task_id` is not in `allowed` is dropped before sending (so queued messages from a task denied at the last refresh cannot drain).
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

New tests per repo (`tests/test_ws_all_task_access.py`, real `TestClient.websocket_connect`, stubs in the style of `test_ws_task_access.py`), for both `/ws/logs` and `/ws/progress`: member sees own project's task and not another org's (no callback registered for it, not in `running_tasks`); a message from a task not in `allowed` is not delivered; bare task id hidden; legacy/service sees all; key socket for another org sees nothing from it; membership removed then the next refresh unsubscribes; a refresh still runs while a busy task keeps the queue non-empty; lookup exception hides the project (strict); key revoked at re-check closes 4001; PF/TF shadow mode keeps the stream and logs; the flag on drops it. Plus the existing `test_ws_task_access.py`, `test_ws_org_routing.py` and `test_ws_acw_auth.py` stay green, and each repo's lint gates.
