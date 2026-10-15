---
status: approved
issue: 3589
intent: intent/2026-10-15-3589-fix-stuck-terminal.md
---

# Spec: fix-stuck-tasks.py must not turn a terminal status back into running

## Design

Same change in each fork of `apps/backend/scripts/fix-stuck-tasks.py`
(AIFactory, PFactory, TFactory; the forks differ only in the specs folder,
plan file name and the argparse description).

1. **One list, with `failed` on it.** The valid-status list is written twice
   today: `valid_statuses` in `check_task_state` (`:54-67`) and an inline
   copy in `fix_task` (`:179-190`). Replace both with one module-level
   `VALID_STATUSES` and add `failed` to it, so a closed-as-failed plan is
   not even reported.
2. **Report unknown statuses, never rewrite them.** The `elif status not in
   [...]` branch in `fix_task` (`:179-198`) currently writes
   `plan["status"] = "in_progress"`. It becomes a print saying the status is
   left unchanged for manual repair, with no write and `fixed` unchanged.
   `check_task_state` still lists it as an issue, so the script still exits 1
   and the operator sees it.

Why 2 and not only 1: the script cannot tell an unknown terminal value from
junk, and guessing "running" is exactly the phantom-running bug. Any value a
service adds later (e.g. `error`, `stopped`) is then safe without another
list edit. The `backlog`-with-progress repair is untouched: it moves a
non-terminal status to another non-terminal status.

## Alternatives rejected

- **Only add `failed` to the list.** Fixes this instance; the next terminal
  value a service writes is rewritten to running again.
- **Import `is_terminal` from `factory-contracts`.** The backends do not
  depend on that package and the script is stdlib-only; adding a dependency
  for one check is not worth it.
- **Retire the three forks** (suggested on the issue). Nothing calls them,
  but deleting operator tooling is a product decision; left on the issue.
- **Also stop creating `approved:false` review states / repair control
  rows.** Separate findings from the same audit; out of scope here.

## Risks

- An operator who relied on the script to "unstick" a plan with a garbage
  status now has to fix it by hand. The script prints which plan and value.
- Forks drifting: the three PRs carry the same diff; the test is the same
  in each repo.

## Verification

- New `tests/test_fix_stuck_tasks.py` in each repo, loading the script with
  `importlib` (the pattern of `tests/test_gen_autonomy_matrix.py` in
  AIFactory): a plan with `failed` is not flagged and is unchanged after
  `fix_task`; a plan with an unknown status is flagged but its file is
  byte-identical after `fix_task`. Fails on `origin/dev`, passes after.
- `ruff check` and `ruff format --check` on the script and test.
