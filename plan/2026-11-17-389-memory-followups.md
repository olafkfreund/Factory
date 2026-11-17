---
status: approved
issue: 389
spec: spec/2026-11-17-389-memory-followups.md
coders:
  1-6: claude   # lead writes AIFactory first, then ports to PFactory and TFactory; vendored code needs one head
reviewers:
  - codex       # read-only `codex review --base origin/dev` per repo; agy is off this round
---

# Plan: RFC-0021 memory follow-ups

Approved decisions (spec): per-directory `fcntl.flock` sidecar with a bounded
wait, fail toward not writing; Graphiti calls filtered by one helper (shared cap
and the unverified marker), no new Graphiti capability; PF/TF project pool
derived from the project directory (seed from `project_dir`, sync anchored on
`source_spec_dir`); pool merge instead of wholesale copy (higher count wins,
`bad`/`ab` max, confirmed later stamp, gotchas unioned); tests with mutation
checks; measures into RFC 6.2. One PR per repo, base `dev`. All paths below are
under `apps/backend/` of each repo.

## Steps

1. `memory/locking.py` (new): `locked(memory_dir, wait=2.0)`, `LockTimeout(OSError)`,
   thread-local re-entrancy. Wrap in `memory/scratchpad.py` (`observe`,
   `record_dead_end` read-modify-write), `memory/retention.py` (`confirm`),
   `memory/gates.py` (`promote` body), `memory/patterns.py` (`append_gotcha`,
   `append_pattern`, each with an outer `except OSError` that logs), and
   `agents/tools_pkg/tools/memory.py` (`record_gotcha`: from the repeat check
   through the append). -> `pytest tests/test_memory_*.py`
   Traps: `flock` is per open file description: nested locks in one thread must
   not reopen (re-entrancy). Sidecar must not break `clear_memory`.
2. `memory/pool.py` (new): `merge_into(src, dst)` as in the spec. AIFactory:
   `agents/utils.py` `sync_memory_to_project` and `sync_memory_to_source` call it.
   PF/TF: also `pool_dir`, `pool_dir_from_spec`, `seed`, `sync`. -> pool tests
   Traps: AIFactory ruff vs `standards/ruff.toml` alias sorting: plain imports.
3. `memory/graphiti_helpers.py`: `gate_for_graphiti`; call it in
   `save_to_graphiti_async`, `patterns.append_*` (also marker on the file bullet,
   per-process count), and `agents/memory_manager.py` before both Graphiti saves.
   -> graphiti tests
4. PF/TF only: seed in `core/workspace/setup.py` after `copy_spec_to_worktree`;
   sync in `agents/session.py` after each `save_session_memory`.
   -> `pytest tests/test_memory_pool.py`
5. Tests per repo: `tests/test_memory_lock.py` (two processes, timeout, mutation),
   `tests/test_memory_graphiti_gate.py` (mutation), `tests/test_memory_pool.py`
   (PF/TF: path derives from project dir only, repeated-failure recall, other
   project sees nothing; all: merge keeps newer data, mutation), measures fixture.
6. Hub: `docs/rfc/0021-...md` section 6.2 (measures and the remaining gaps),
   epic #389 boxes, issue comments #3795-#3797 with the decision record.

## Tests

`pytest tests/test_memory_*.py` and the repo's ruff command (see each CI
workflow) green in each repo; the new mutation tests fail when the gate is
removed (shown in the PR).

## Rollback

Revert the PR in the repo. Sidecar `.memory.lock` files are inert. Pools keep
their merged content, which is valid input for the old copy code.
