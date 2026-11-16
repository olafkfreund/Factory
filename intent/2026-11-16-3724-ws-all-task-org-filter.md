---
status: draft
issue: 3724
author: olafkfreund
---

# Intent: Org filter on the all-task WebSockets /ws/logs and /ws/progress

## Problem

`/ws/logs` and `/ws/progress` in AIFactory, PFactory and TFactory register a callback for every running task and stream every log line and progress update to any caller that passes `verify_websocket_token`. That check only proves the token is valid. A member of org A therefore receives the logs and progress of org B's tasks. The per-task sockets (#3703) and `/ws/events` (#3679) already confine by org; these two were left out of scope.

`/ws/terminal/{id}` was to be looked at in the same pass. It is not a task stream: PTY sessions are host-wide, have no project or owner binding, and the REST routes that create and list them take no project either. There is nothing to filter by.

## Proposed outcome

- Both all-task sockets authenticate with `authenticate_websocket` and stream only tasks whose project the caller may read, using the #3703 rule: key principals always strict; JWT principals strict in AIFactory, and in PFactory/TFactory once `RBAC_ENFORCE_TASK_ROUTES` is on (shadow mode logs a would-deny and allows).
- The decision is re-evaluated on the existing 5 s subscription refresh, so a removed membership stops the stream within one refresh. An `acw_` key is re-validated every 5 minutes as on the per-task sockets.
- The `running_tasks` lists sent on `/ws/progress` carry only readable tasks.
- Factory#3714's last open box (AIFactory has no `_jwt_strict()`) is settled and #3714 is closed.

## Affected users and systems

AIFactory, PFactory, TFactory web servers (`server/websockets/{task_access,logs,progress}.py`). Dashboards that use the unified streams keep working for members; they stop seeing other orgs' tasks. No frontend change: the payload shape is unchanged.

## Constraints

- Reuse the #3703 helpers and rules; no new auth model.
- Legacy tokens and `DISABLE_AUTH` (user `None`) and the service principal keep seeing everything.
- Task ids that are not `<project>:<spec>` are readable only by those principals.
- Fail closed for strict principals on any lookup error.
- No live-cluster change.

## Open questions

- `/ws/terminal/{id}` is left as is and a follow-up issue is filed (host-wide shells, no owner). Decision for the owner: whether terminals should be owner- or role-bound.
