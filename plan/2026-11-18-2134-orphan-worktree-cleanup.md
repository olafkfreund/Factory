---
status: draft
issue: olafkfreund/AIFactory#2134
spec: spec/2026-11-18-2134-orphan-worktree-cleanup.md
coders:
  1: codex   # small tricky logic plus real-git tests in one new module
  2: lead    # wiring into agent_kubejob, runs the checks and commits
reviewers:
  - codex    # read-only review of each draft and of the final diff
---

# Plan: orphaned worktree cleanup

Approved decisions (from the spec): replace the report-only #1467 ERROR with a
guarded cleanup at the same two call sites. A registration from
`orphaned_worktree_registrations` is deregistered only if (1) its path is
`<project>/.aifactory/worktrees/{tasks,builds}/<spec>` with a safe `<spec>`,
(2) its admin dir has no `locked` file, (3) `<project_id>:<spec>` is not in
the active set (running_tasks, job-state running, queued; a colon-less id
matches any project; unreadable set means skip everything with a WARNING),
(4) the spec dir is absent or its status is in `stale_tasks.TERMINAL_STATES`
(`task_control.json` that exists but does not parse means skip; unknown means
skip). Deregistration deletes only the admin dir
`<git-common-dir>/worktrees/<id>` whose `gitdir` file matches the path, never
the working directory; no `prune`, no `remove --force`. One INFO line
`removed=N deferred=K`; ERROR only for skipped-unsafe or failed ones. No
daemon. Do not touch sandbox/gVisor code.

## Steps

1. NEW `apps/web-server/server/services/worktree_cleanup.py`:
   `cleanup_orphaned_worktrees(project_path: Path, active_job_ids: set[str]) -> list[str]`
   (returns still-orphaned paths) using `build_backend.orphaned_worktree_registrations`,
   `build_backend._git_out`, `specpath.spec_dir_for`, `stale_tasks.TERMINAL_STATES`,
   `task_control`. NEW `tests/test_worktree_cleanup.py` with real git covering
   finished removed, deleted-spec (dir gone) deregistered, running untouched,
   unreadable (corrupt task_control.json) untouched, outside data root untouched,
   locked untouched, same spec under other project not protected, standalone
   clone directory survives, second run no-op
   → `cd /mnt/code/.../AIFactory && python -m pytest tests/test_worktree_cleanup.py tests/test_build_clone_worktree_isolation.py -q`
   Traps: ruff and standards/ruff.toml disagree on `as` aliases in
   parenthesised imports: plain names; sys.path setup as in
   tests/test_build_clone_worktree_isolation.py; never print secrets.
2. `apps/web-server/server/services/agent_kubejob.py`: make
   `_report_orphaned_worktrees` async taking the active id set; add a
   `KubejobMixin` helper that builds it (running_tasks keys, store running and
   queued ids; any exception -> None -> skip with WARNING); `await` it at the
   two call sites; drop the ERROR text in favour of the module's logging
   → run step 1 tests plus `ruff check`/`ruff format --check` and `mypy` on
   touched files per `.github/workflows` and pyproject.
   Traps: generated autonomy matrix not touched; mixin methods called via
   `self`.

## Tests

`python -m pytest tests/test_worktree_cleanup.py tests/test_build_clone_worktree_isolation.py -q`
all pass; repo ruff and mypy clean on touched files; plus any existing
agent_kubejob tests.

## Rollback

Revert the PR. Registrations already removed were only stale git metadata;
`git worktree repair` or re-adding recreates one if ever needed.
