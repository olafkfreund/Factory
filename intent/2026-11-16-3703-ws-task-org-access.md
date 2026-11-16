---
status: approved
issue: 3703
author: olafkfreund
---

# Intent: org access on per-task WebSockets, and WS membership freshness

Covers Factory#3703, #3705, #3714 and #3704. Follow-ups of #3679
(`intent/2026-11-07-3679-ws-event-org-filtering.md`).

## Problem

#3679 confined the global `/ws/events` feed to the caller's orgs. Four gaps are left:

- **#3703.** `/ws/tasks/{task_id}/logs` and `/ws/tasks/{task_id}/progress` (AIFactory, PFactory, TFactory) only check that the token is valid. Any authenticated caller can watch any task of any org. They also never accept `acw_` keys and so have no revocation re-check.
- **#3705.** A JWT `/ws/events` socket reads the user's `OrgMember` rows once, at connect. A user removed from an org keeps getting its events until reconnect. Also, a validly signed access token with no `sub` registers with `user_id=None`, which the router treats as a service client that receives every org's events.
- **#3714.** Leftovers from the #3679 final review: no start-route test with a user principal; the key re-check discards the fresh principal (`key_org_id`, `user_id`); `_payload_org` differs between AIF and PF/TF; AIF inlines `_jwt_strict()`.
- **#3704.** The web frontends match `task-logs:stream` on `specId` alone, so two projects that both have spec `001-x` show each other's log lines to a user who may see both.

## Proposed outcome

- Connecting to `/ws/tasks/{task_id}/logs|progress` applies the same rule as REST `check_project_access` for the task's project (`<project_id>:<spec>`), in the mode REST runs in. `acw_` keys connect and are re-checked every 5 minutes; a revoked key, or an owner removed from the org, is closed with 4001.
- JWT `/ws/events` sockets follow membership changes within the same re-check interval.
- An access token without `sub` is rejected at WebSocket auth.
- The #3714 boxes that are real gaps are closed; the rest are ticked with a reason.
- Frontends match `task-logs:stream` on `projectId` and `specId`.

## Affected users and systems

AIFactory, PFactory, TFactory web-servers (`server/websockets/*`, `server/auth.py`) and web frontends (`useTaskDetail`, `useCardLogs`, `api-adapter`). CFactory and the Factory hub need no code change. Users with access to several orgs and API-key consumers of the per-task sockets.

## Constraints

- Owner decision (#3679): JWT sockets follow REST mode. In PF and TF a JWT user is denied only once `RBAC_ENFORCE_TASK_ROUTES` is on; in AIF always. Key sockets are always strict.
- The service principal (legacy token, `DISABLE_AUTH`) keeps access to everything.
- Out of scope: #3702 (multi-org key); the unscoped `/ws/logs` and `/ws/progress` all-task sockets (new issue to be filed); no live-cluster action.
- Vendored files stay byte-identical with the hub copy.

## Open questions

None. The all-task sockets are named above as a follow-up, not decided here.
