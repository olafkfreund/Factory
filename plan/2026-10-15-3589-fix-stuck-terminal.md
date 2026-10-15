---
status: draft
issue: 3589
spec: spec/2026-10-15-3589-fix-stuck-terminal.md
---

# Plan: fix-stuck-tasks.py must not turn a terminal status back into running

Approved decisions (from the spec):

- One module-level `VALID_STATUSES` list replaces the two copies, and
  includes `failed`.
- `fix_task` never rewrites a status it does not know; it prints that the
  status was left unchanged. `check_task_state` still reports it (exit 1).
- The `backlog`-with-progress repair and the `review_state.json` creation are
  unchanged. Retiring the forks is out of scope.
- Script stays stdlib-only. One PR per repo (AIFactory, PFactory, TFactory),
  base `dev`, each linking these hub artifacts.

## Steps

Per repo `R` in AIFactory, PFactory, TFactory, in a worktree
`git -C /mnt/code/Source-home/GitHub/R worktree add -b fix/3589-fix-stuck-terminal /mnt/code/Source-home/GitHub/R-3589 origin/dev`:

1. `tests/test_fix_stuck_tasks.py` (new): load
   `apps/backend/scripts/fix-stuck-tasks.py` with
   `importlib.util.spec_from_file_location` (hyphenated name). Two tests,
   using `tmp_path` with the repo's specs folder (`.aifactory`, `.pfactory`
   or `.tfactory`) and plan file (`implementation_plan.json` or
   `test_plan.json`) taken from the loaded module's behaviour, i.e. write the
   plan where `find_spec_directories` looks:
   - `failed` plan: `check_task_state` reports no status issue, and the file
     bytes are unchanged after `fix_task`.
   - `bogus` plan: `check_task_state` reports an "Invalid status" issue, and
     the file bytes are unchanged after `fix_task`.
   → verify it fails on unfixed code:
   `apps/backend/.venv/bin/pytest tests/test_fix_stuck_tasks.py` (or the
   repo venv that exists).
   Traps: the `tests/conftest.py` in PFactory may skip on missing deps; run
   from the repo root.
2. `apps/backend/scripts/fix-stuck-tasks.py:54-67`: move the list to a
   module-level `VALID_STATUSES` (after the imports), add `"failed"`;
   `check_task_state` uses it (`:69-70`).
3. `apps/backend/scripts/fix-stuck-tasks.py:179-198`: replace the inline list
   with `VALID_STATUSES` and the rewrite with a print
   `"  → Unknown status '{status}': left unchanged, repair by hand"`; no
   write, `fixed` not set. → `pytest tests/test_fix_stuck_tasks.py` passes;
   `ruff check` and `ruff format --check` on both files.
   Traps: do not reformat other lines (AIFactory's `main()` argparse call is
   multi-line; leave it).
4. Commit naming the step, push, PR against `dev` with `Closes
   olafkfreund/Factory#3589` only on the last repo's PR (the others "Refs").
   Wait for CI.

Hub: this branch carries only the three artifacts; its PR links the three
service PRs and `Refs #3589`.

## Tests

`pytest tests/test_fix_stuck_tasks.py` in each repo: 2 passed (2 failed
before step 2-3). `ruff check` / `ruff format --check` clean on touched files.

## Rollback

Revert the per-repo PR; the script returns to rewriting unknown statuses.
