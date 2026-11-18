---
status: approved
issue: olafkfreund/AIFactory#2134
intent: intent/2026-11-18-2134-orphan-worktree-cleanup.md
---

# Spec: orphaned worktree cleanup

## Design

New module `apps/web-server/server/services/worktree_cleanup.py` with
`cleanup_orphaned_worktrees(project_path, active_spec_ids) -> list[str]`
(returns registrations still orphaned). `_report_orphaned_worktrees` in
`agent_kubejob.py` becomes async, computes `active_spec_ids` and calls it at
its two existing call sites, so no new trigger or daemon exists.

Candidates come from the existing `orphaned_worktree_registrations` (#1467:
registered path whose `.git` is not a file, including a missing directory).
Per candidate, all of these must hold, else it is skipped:

1. Path resolves under `<project>/.aifactory/worktrees/{tasks,builds}/<spec>`;
   `<spec>` passes `spec_dir_for` (barrier). Otherwise: ERROR, untouched.
2. Not locked (`locked` file in its admin dir `<git-common-dir>/worktrees/<id>`).
3. Not active: the set of running_tasks, job-state running and queued job ids
   (`project:spec`) does not contain `<project_id>:<spec>`; a bare id without a
   colon matches any project (false deferral is the safe direction). If the
   set cannot be read the whole cleanup is skipped with a WARNING.
4. Task terminal: spec dir absent (deleted), or its status in
   `stale_tasks.TERMINAL_STATES`. Status is read from `task_control.json`; if
   that file exists but cannot be parsed, skip (no fallback to the legacy plan
   status, which may be stale). Absent file falls back to `read_control`.
   Missing/unknown status means skip.

Deregistration (deviation from the issue text, found by the Codex review):
`git worktree remove --force` fails on exactly these candidates (git validates
that `.git` is a gitfile; here it is a directory or missing), and
`git worktree prune` is repository-wide so it can also drop registrations that
were never vetted. So the registration is removed by deleting only its own
admin dir `<git-common-dir>/worktrees/<id>`, found by matching its `gitdir`
file to the candidate path. The working directory itself is never deleted
(a standalone clone may hold the only copy of finished work). The snapshot of
active ids is taken immediately before the synchronous cleanup, so no
coroutine on the same event loop can admit a restart in between; a second
replica is a residual risk, accepted because only terminal tasks qualify.

Result: one INFO line `removed=N deferred=K`; ERROR only for skipped-unsafe or
failed removals. Active-task candidates count as `deferred` (INFO), not
errors. Idempotent: a second run finds nothing.

Decision (owner delegation 2026-11-18): the terminal set is
`stale_tasks.TERMINAL_STATES` (reuse, one definition of terminal).

## Alternatives rejected

- Background sweeper daemon: the issue forbids it; completion already runs.
- `git worktree prune` or `remove --force`: prune is repo-wide and does not
  clear a registration whose directory exists as a standalone clone (#1467);
  `remove --force` fails on that case (see Design).
- Keep report-only: leaves the lock-holding registrations forever.

## Risks

Removing a worktree a build still uses: guarded by the active set, lock,
terminal-state and path checks, all fail closed. Blocking git calls on the completion path: same as the
existing check.

## Verification

Real-git pytest: finished-task worktree removed; deleted-task registration
deregistered (directory gone); running-task untouched; unreadable state untouched; path outside the
data root untouched; locked untouched; second run is a no-op; same spec id under another project is not protected by this project's active job; corrupt task_control.json is skipped; a standalone clone's directory survives deregistration. Ruff and mypy on
touched files. Read-only before/after count on aifactory-demo if readable.
