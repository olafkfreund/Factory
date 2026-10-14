---
status: draft
issue: 1026
spec: spec/2026-10-14-1026-blocking-check-names.md
---

# Plan: a check named "blocking" must be able to block

## Approved decisions (from the spec)

- **Promote by default.** A check named "blocking", or one of the three
  guards the issue names (`every test file is inside a collected path`,
  `vendored factory_common matches the hub canonical`, CFactory
  `card models match the hub contract`), is promoted to required on a branch
  if it reported on every merged PR into that branch since it was added, and
  passed on each one. Otherwise it is renamed to drop "blocking", and a
  follow-up issue is filed.
- **The gate** lives in `scripts/apply_branch_protection.sh` check mode, so
  the nightly `branch-protection-drift.yml` runs it. For each declared
  branch:
  - take the check-run names on the head SHA of the most recently merged PR
    into that branch;
  - any name matching `/\bblocking\b/i` that is missing from that branch's
    **declared** contexts (the `build_payload` output, not live protection) is
    a divergence: print `MISLABEL`, set `DIVERGED=1`;
  - no merged PR, or no check runs, sets `UNDETERMINED=1`, never clean.
- **Offline test hook.** `--blocking-stdin REPO BRANCH` reads a JSON array of
  names from stdin and applies the same rule.
  - exit 0: clean;
  - exit 1: at least one `MISLABEL`;
  - exit 2: the input is empty.
- **Match only the word "blocking"**, case-insensitive. Also matching
  "Gate N" was rejected.
- **Out of scope:** CodeQL, security lint, Trivy and `enforce_admins` (#943),
  and rulesets.
- **Live protection changes only via `--apply --repo R`**, one repo at a time
  and only with explicit user approval. `assert_no_strip` already refuses any
  removal.

## Measurement (2026-10-14, last 20 merged PRs per branch)

Every candidate below reported on and passed every merged PR since the job
was added. Counts below 20/20 are age, not filtering: the runs are
contiguous and newest-first. For example, CFactory@main Gate 5 is
`YYYYYYYYYYYYY-------`.

| repo@branch | promote (new required contexts) |
|---|---|
| Factory@main | `committed output matches inputs (--check, blocking)` (`contracts.yml:64`) |
| PFactory@dev + @main | `Gate 5 — banned constructs (blocking, Factory#786)`; `frontend (eslint, blocking)`; `ratchet ruff + mypy (changed files, blocking)`; `ruff format --check (apps/backend + apps/web-server + scripts, blocking)`; collected-path; factory_common |
| TFactory@dev + @main | `Gate 5 — banned constructs (blocking, Factory#786)`; `frontend (eslint, blocking)`; collected-path; factory_common |
| CFactory@dev + @main (one `CHECKS`) | `Gate 5 — banned constructs (blocking, Factory#786)`; `frontend lint + format + unit tests (blocking)`; `ruff check (apps/backend/cfactory + scripts, blocking)`; `ruff format --check (apps/backend/cfactory + scripts, blocking)`; `ruff + mypy ratchet (diff-scoped, blocking)`; collected-path; factory_common; `card models match the hub contract` |
| AIFactory@dev | `Gate 5 — banned constructs (blocking, Factory#718)`; `frontend lint + format (blocking, #647)` (after step 1); collected-path; factory_common |
| AIFactory@main | as for @dev, plus `shared-baseline drift gate (blocking)` (already required on dev) |

Already required, no change:
- Factory: the ruff + mypy ratchet and the ruff format check;
- AIFactory: `autonomy matrix matches the policy (--check, blocking)` on both
  branches, and `shared-baseline drift gate (blocking)` on dev.

**Rename (path-filtered):** `factory-github canonical drift (blocking)`.
It posted on 1–2 of the last 20 PRs, because its `pull_request` trigger has
`paths:`, in all four service repos (`.github/workflows/factory-github-drift.yml:43`).
It becomes `factory-github canonical drift`. A follow-up issue proposes
removing the filter and promoting it, the same move Factory#525 made for
VCORE.

**Defect:** in AIFactory, `.github/workflows/ci.yml:838` reads
`name: frontend lint + format (blocking, #647)` unquoted. YAML treats
` #647)` as a comment, so the context posts as `frontend lint + format (blocking,`.

## Steps

Who does what: **agy** does steps 1–2 (service repos), **Codex** does steps
3–5 (hub), and the session reviews every diff, runs the checks, commits and
does steps 6–7. A fresh Opus agent reviews the hub diff against this plan.

1. **AIFactory `.github/workflows/ci.yml:838`**: quote the name, as
   `name: "frontend lint + format (blocking, #647)"`.
   - Verify: on the PR, the check posts as the full name
     (`gh pr checks <n> -R olafkfreund/AIFactory | grep '#647'`).
   - Traps:
     - the PR targets `dev`;
     - check whether any job's `needs:` or any script refers to the
       truncated name (`grep -rn "format (blocking," .github scripts`).
2. **{PFactory,TFactory,CFactory,AIFactory} `.github/workflows/factory-github-drift.yml:43`**:
   change `name: factory-github canonical drift (blocking)` to
   `name: factory-github canonical drift`. One PR per repo to `dev`.
   - Verify: `grep -n "canonical drift" .github/workflows/factory-github-drift.yml`
     shows the new name. The job only posts on PRs that touch its paths,
     which this PR does (the workflow file is in its own `paths:`).
   - Trap: a "no workflow is a wholesale copy of another" gate exists. Each
     repo edits only its own copy, so the four stay byte-identical to each
     other.
   - File the follow-up issue in Factory: "factory-github drift is
     path-filtered: unfilter and promote" (link #1026, #525).
3. **Factory `scripts/apply_branch_protection.sh`, `repo_config()`
   (lines 198–250)**: add the contexts in the measurement table.
   - Introduce `COLLECTED_CTX="every test file is inside a collected path"`
     and `FCOMMON_CTX="vendored factory_common matches the hub canonical"`
     beside `VCORE_CTX`, with one comment line saying why they're shared.
     The Gate 5 strings differ by repo (`#786` vs `#718`), so spell them out
     per repo.
   - Add to `CHECKS` (main) and `CHECKS_DEV` (dev) as the table says.
     CFactory has only `CHECKS`, which covers both branches.
   - Factory/main gets `committed output matches inputs (--check, blocking)`.
   - Verify: run
     `bash scripts/apply_branch_protection.sh --emit <R> <B> | jq '.required_status_checks.contexts'`
     for all 9 pairs; each must list exactly the old contexts plus the new
     ones.
   - Traps:
     - the strings must match the posted names byte for byte, including
       the em dash `—` in Gate 5;
     - keep the existing JSON-in-shell quoting style;
     - leave factory-gitops untouched.
4. **Factory `scripts/apply_branch_protection.sh`, the gate.**
   - Add `blocking_verdict REPO BRANCH NAMES_JSON`. It prints one
     `MISLABEL <repo>@<branch>: "<name>" claims blocking but is not required`
     line per offending name and returns 0, 1 or 2 as above. Use
     `jq`'s `test("\\bblocking\\b"; "i")`.
   - Add `check_blocking_names REPO BRANCH`:
     - `gh pr list -R $OWNER/$repo --base $branch --state merged -L 1 --json headRefOid`;
     - then
       `gh api --paginate "repos/$OWNER/$repo/commits/$sha/check-runs?per_page=100" -q '[.check_runs[].name]'`,
       merged with `jq -s 'add|unique'`;
     - then `blocking_verdict`;
     - rc 1 sets `DIVERGED=1`, rc 2 (or a failed fetch) sets
       `UNDETERMINED=1`, with an `ERROR` line on stderr.
   - Call it in `run_repo`'s check-mode loop right after `check_one`.
   - Add the `--blocking-stdin) MODE="blocking-stdin"; ONLY_REPO=$2; EMIT_BRANCH=$3; shift 2 ;;`
     arg, handled where `--emit` and `--normalise-stdin` are dispatched.
   - Add a header comment block for the gate (#1026). If the header grows,
     update the `--help` `sed -n '2,56p'` range.
   - Verify:
     - `bash scripts/apply_branch_protection.sh --repo AIFactory` with a
       local token prints the expected `MISLABEL` or `ok` lines for
       AIFactory;
     - `shellcheck scripts/apply_branch_protection.sh` reports no new
       warnings.
   - Traps:
     - `set -euo pipefail`: capture return codes with `|| rc=$?` the way
       `check_one` does;
     - don't let the summary print OK when this function was undetermined
       (rule 4.7);
     - `--signatures` mode must not run it (it exits before the loop
       already; keep it that way).
5. **Factory `tests/test_branch_protection_intent.py`.**
   - Update `test_check_contexts_are_per_repo` (lines 240–284) to the new
     exact lists, and drop or rewrite the "AIFactory has no required
     frontend check" comment.
   - Add `--blocking-stdin` tests:
     - an unrequired `"x (blocking)"` gives exit 1 and a `MISLABEL` line
       (mutation proof);
     - a declared blocking name gives exit 0;
     - an advisory name without the word gives exit 0;
     - `"X (BLOCKING)"` gives exit 1, and `"nonblocking-ish"` gives exit 0
       (word boundary);
     - `[]` gives exit 2.
   - Add a test that each new context in the table appears in the
     measurement-table names. Keep it simple: assert `_COLLECTED` and
     `_FCOMMON` are present for the four service repos on both branches.
   - Verify: `pytest tests/test_branch_protection_intent.py -q` passes, and
     the ratchet passes
     (`python scripts/ratchet_lint.py --base origin/main --package scripts,tests`,
     plus the same with `--tool mypy`, using the `scratchpad/rv` venv).
   - Trap: helpers like `_emit` and `_VCORE` already exist; reuse them.
6. **Rollout, session, live.** Ordering decides whether anything breaks.
   1. Merge steps 1 and 2 (service-repo PRs). Then merge the hub PR with
      steps 3–5.
   2. Run `bash scripts/apply_branch_protection.sh --repo <R>` (check mode)
      and confirm that the only diff is the added contexts.
   3. Ask the user for approval to apply `<R>`.
   4. `read_new` and `post` on the agent bus.
   5. Run `bash scripts/apply_branch_protection.sh --apply --repo <R>`.
   - Order: CFactory, TFactory, PFactory, AIFactory, Factory (smallest blast
     radius first).
   - Verify: the next PR in `<R>` lists the new contexts as Required and goes
     green.
   - Traps:
     - an open PR whose head predates a job will wait for that context; push
       or rebase it;
     - never use `--admin`.
7. **Verify end to end.** Dispatch `branch-protection-drift.yml`
   (`gh workflow run branch-protection-drift.yml`). It must exit 0 with no
   `MISLABEL` and no `DRIFT` lines. Close #1026 with the run link.

## Tests

- `pytest tests/test_branch_protection_intent.py -q`: all pass, including
  the new `--blocking-stdin` cases.
- The full hub suite in CI, plus the ruff + mypy ratchet and the format
  check.
- Live: check mode before apply shows only additions. After all applies,
  the drift workflow run is green.

## Rollback

- **Per repo:** remove the added contexts from `repo_config()`, then
  `--apply --repo R`. The removal guard requires its explicit override, as
  documented in `assert_no_strip`.
- **Gate:** revert the hub PR. The nightly job falls back to protection
  drift only.
- **Renames and the AIFactory quote fix:** revert the PRs. Neither is
  required anywhere, so reverting blocks nothing.
