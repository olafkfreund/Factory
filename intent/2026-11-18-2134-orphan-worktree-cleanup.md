---
status: approved
issue: olafkfreund/AIFactory#2134
author: olafkfreund
---

# Intent: automatic, safe cleanup of orphaned task worktree registrations

## Problem

After every task AIFactory logs `ERROR #1467 orphaned worktree registrations
... deregister with git worktree remove --force`, listing about 20 stale task
worktrees in the aifactory-demo workspace. The check
(`_report_orphaned_worktrees` in `apps/web-server/server/services/agent_kubejob.py`)
is report-only, so the registrations are never removed. Each one keeps holding
its branch lock, so later checkouts and pushes of that branch can fail, and the
ERROR is noise that hides real faults.

## Proposed outcome

At the point the error is raised today, registrations that are provably stale
are deregistered, so the listed ones disappear on the next task. One INFO line
with counts replaces the ERROR on success. An ERROR remains only for a
registration that could not be safely removed.

## Affected users and systems

AIFactory web-server (kubejob completion path); the workspace git repos under
each project's `.aifactory/worktrees`. Operators reading the logs.

## Constraints

- Remove only when the task is terminal (done, completed, failed, cancelled,
  qa_failed) or deleted, AND no running/queued job or active run holds it, AND
  the git worktree is not locked, AND the path is under the project's
  `.aifactory/worktrees` directory.
- Fail closed: unreadable task or job state means skip and log.
- `git worktree prune` for registrations whose directory is gone;
  `git worktree remove --force` only for the terminal/deleted-task case.
- No new daemon. Do not touch gVisor / agent sandbox code.

## Open questions

None. Decision (owner delegation 2026-11-18): the terminal set is the existing
`stale_tasks.TERMINAL_STATES`; `review`/`human_review` are never terminal.
