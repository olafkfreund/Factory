---
status: approved
issue: 3585
spec: spec/2026-10-15-3585-unfilter-fgithub-drift.md
---

# Plan: let the factory-github drift gate post on every PR, then require it

Approved decisions (from the spec):

- Service repos: delete the `paths:` list under `pull_request` only; keep
  the `push` filter and the job name `factory-github canonical drift`.
- Hub: add `FGITHUB_CTX="factory-github canonical drift"` and require it on
  `main` and `dev` of CFactory, PFactory, TFactory, AIFactory; never on
  Factory or factory-gitops. Tests lock it in.
- Order: service PRs merge, gate observed posting on an unrelated PR in each,
  then the hub PR merges, then the lead runs `--apply`. No live change here.

## Steps

1. Service repos (AIFactory, PFactory, TFactory, CFactory), worktree
   `git -C /mnt/code/Source-home/GitHub/<R> worktree add -b ci/3585-unfilter-fgithub-drift /mnt/code/Source-home/GitHub/<R>-3585 origin/dev`:
   `.github/workflows/factory-github-drift.yml:13-17`: replace
   ```
     pull_request:
       branches: [dev, main]
       paths:
         - "apps/backend/runners/github/**"
         - ".github/workflows/factory-github-drift.yml"
   ```
   with
   ```
     pull_request:
       branches: [dev, main]
       # No paths: filter (Factory#3585): a required check must post on every PR.
   ```
   → verify `python3 -c 'import yaml,sys; d=yaml.safe_load(open(sys.argv[1])); assert "paths" not in d[True]["pull_request"]' .github/workflows/factory-github-drift.yml`
   and, after push, `gh pr checks` shows `factory-github canonical drift`.
   Traps: lines 11-23 are byte-identical in all four repos; do not touch
   the `push` block. Commit message names step 1. PR body `Refs
   olafkfreund/Factory#3585`.
2. `scripts/apply_branch_protection.sh:138-140`: after `FCOMMON_CTX=...`
   add a comment (unfiltered by #3585, required only after it was seen
   posting, like `$VCORE_CTX`) and `FGITHUB_CTX="factory-github canonical drift"`.
   In `repo_config` (`:228-234`) add `"'"$FGITHUB_CTX"'",` after each
   `"'"$FCOMMON_CTX"'",` in CFactory `CHECKS`, PFactory `CHECKS` and
   `CHECKS_DEV`, TFactory `CHECKS` and `CHECKS_DEV`, AIFactory `CHECKS` and
   `CHECKS_DEV` (7 insertions).
   → verify `grep -c 'FGITHUB_CTX"' scripts/apply_branch_protection.sh` is 7
   (the definition line uses `FGITHUB_CTX=`).
   Traps: the quoting is `'"$X"'` inside single-quoted JSON; one missing
   quote breaks every repo's payload. Do NOT run `--apply`.
3. `tests/test_branch_protection_intent.py`: add
   `_FGITHUB = "factory-github canonical drift"` after `_FCOMMON` (`:135`);
   add `_FGITHUB` after `_FCOMMON` in the CFactory, TFactory, PFactory and
   AIFactory lists of `test_check_contexts_are_per_repo` (`:263-336`), and
   `assert _FGITHUB in contexts` in
   `test_service_repos_require_the_shared_measured_guards` (`:343-346`);
   add `_FGITHUB not in` to the Factory/factory-gitops loop (`:326-327`).
   Other tests that build full live-shaped payloads from `_emit` need no
   edit if they compare intent to itself; fix any that hardcode lists.
   → `pytest tests/test_branch_protection_intent.py -q` passes; reverting
   step 2 makes it fail.
4. Commit, then `ruff check`, `ruff format --check` on the test, and the
   ratchet (`ratchet_lint.py --base origin/main --package scripts,tests`,
   plus `--tool mypy`). Push, PR `Closes #3585`, body lists the merge
   order and the live `--apply` step for the lead.

## Tests

- `pytest tests/test_branch_protection_intent.py -q`: all pass.
- Each service PR: `factory-github canonical drift` posts green.

## Rollback

Revert the hub PR (and re-run `--apply` if it was applied); revert a service
PR to restore the filter, only after the hub requirement is gone.
