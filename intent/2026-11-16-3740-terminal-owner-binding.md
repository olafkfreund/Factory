---
status: draft
issue: 3740
author: olafkfreund
---

# Intent: bind terminal sessions to their owner and project

## Problem

PTY sessions in AIFactory, PFactory and TFactory are host-wide. `POST /api/terminals` uses the project id only to pick a working directory; the session stores no owner and no project. `GET /api/terminals` and `GET /api/terminals/sessions` list every session (`project` is ignored), and `/ws/terminal/{id}` plus the `/api/terminals/{id}...` routes look a session up by id after a token check only. Any authenticated user who learns or lists an id gets a shell owned by someone else, across orgs. A caller can also pass an existing `id` on create and overwrite another user's session entry. The worktree and session-clearing routes take a free-form project path with no project authorization.

## Proposed outcome

- Each session records the creating user id and the project id.
- A non-service caller (a JWT user or per-user `acw_` key) can create a terminal only for a project they are authorized for (`authorize_project_for_user`, as the other project routes), gets that project's directory, and sees, reads, writes, resizes and closes only their own sessions of projects they still hold.
- Another user's session answers as "not found" (REST 404, WebSocket close 4004), so ids do not leak existence.
- The service principal (legacy `API_TOKEN`, auth-disabled dev user) and legacy-token WebSockets keep full access, as in the all-task sockets (Factory#3724).
- Create rejects an `id` that already exists (409).
- Worktree and session-clear routes authorize the project they name for non-service callers.
- Tests cover allowed and denied cases.

## Affected users and systems

`apps/web-server/server` in AIFactory, PFactory, TFactory: `pty/session.py`, `pty/manager.py`, `routes/terminal.py`, `websockets/terminal.py`. No frontend change, no schema change. Local UI users run as the service principal and are unaffected.

## Constraints

- Follow the wave-3 pattern (`task_access.py`, `project_authz.py`); fail closed on any lookup error.
- Never print or log tokens or PTY output.
- Keep diffs tight; vendored files untouched.
- Wave-3 PRs may still be merging: rebase on the current base before implementing and before the final push.

## Open questions

None. The issue's owner choice (bind to user and project, or admin-only) is settled by the owner's advance approval for this round: bind to user and project.
