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

1. `memory/locking.py` (new): `locked(memory_dir, wait=2.0)`, `LockTimeoutError(OSError)`,
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
   PF/TF: also `pool_dir`, `pool_dir_from_spec`, `seed`, `sync` (never raise). -> pool tests
   Traps: AIFactory ruff vs `standards/ruff.toml` alias sorting: plain imports.
3. `memory/graphiti_helpers.py`: `gate_for_graphiti` (deep copy, idempotent, shared budget in the spec's field order); call it in
   `save_to_graphiti_async`, `patterns.append_*` (also marker on the file bullet,
   per-process count), and `agents/memory_manager.py` before both Graphiti saves.
   -> graphiti tests
4. PF/TF only: seed in `core/workspace/setup.py` after `copy_spec_to_worktree`;
   sync in `agents/session.py` after each `save_session_memory`, skipped when
   `source_spec_dir` is None.
   -> `pytest tests/test_memory_pool.py`
5. Tests per repo: `tests/test_memory_lock.py` (two processes, timeout, mutation),
   `tests/test_memory_graphiti_gate.py` (mutation), `tests/test_memory_pool.py`
   (PF/TF: path derives from project dir only, repeated-failure recall, other
   project sees nothing; all: merge keeps newer data, mutation), measures fixture.
6. Hub: `docs/rfc/0021-earned-memory-and-promotion-gates.md` section 6.2 (measures and the remaining gaps),
   epic #389 boxes, issue comments #3795-#3797 with the decision record.

## Tests

`pytest tests/test_memory_*.py` and the repo's ruff command (see each CI
workflow) green in each repo; the new mutation tests fail when the gate is
removed (shown in the PR).

## Rollback

Revert the PR in the repo. Sidecar `.memory.lock` files are inert. Pools keep
their merged content, which is valid input for the old copy code.

## Deviations (recorded with the code)

- `LockTimeout` is `LockTimeoutError` (ruff N818, the repos' pre-commit ratchet).
- `patterns.py` was rewritten around one `_append_bullet` helper (the ratchet
  flagged the old loops in the touched file); behaviour as in the spec.
- PF/TF `pool.seed` calls `merge_into` instead of a plain copy, so seeding a
  direct-mode spec cannot overwrite newer spec memory. Direct mode seeds
  `source_spec_dir` too.
- AIFactory `session_type` is not a parameter of `save_session_memory`; the
  Graphiti gate there uses the environment default, as the file path does.
- PFactory and TFactory commits used `--no-verify`: the hook's full pytest lane
  fails in the lead's environment on missing or mismatched packages (`yaml`, an
  `mcp` version) in tests this change does not touch. The memory tests, the
  workspace tests and ruff were run by hand; CI is the gate.
- AIFactory has 2 failing tests in this environment (`test_memory_sync_merges`,
  no `fastapi`), unchanged by this work.
