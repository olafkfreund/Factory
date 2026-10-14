---
status: approved
issue: 1026
intent: intent/2026-10-14-1026-blocking-check-names.md
---

# Spec: a check named "blocking" must be able to block

Decisions on the intent's open questions (approver took the recommendations):

1. A stable check is **promoted** to required. Rename only when it is not.
2. The gate runs in **hub CI on the existing schedule**, inside
   `scripts/apply_branch_protection.sh` check mode, so
   `branch-protection-drift.yml` runs it with no new workflow.
3. The gate matches the word **"blocking"** only, case-insensitively. Every
   "Gate N" name today already carries it, and widening the match later is a
   one-regex change. The approver can still overrule this at spec review.

## Design

### 1. The gate: `check_blocking_names` in check mode

`apply_branch_protection.sh` gets a function that runs once per declared
branch in check mode, next to `check_one`:

- Input A: the job names that actually post on PRs into that branch. These
  are the check-run names on the head SHA of the **most recently merged PR**
  into the branch
  (`gh pr list --base <b> --state merged -L1`, then
  `commits/<sha>/check-runs`, paginated). A PR head, not the branch head: a
  required check must post on PRs, and push-only jobs never can. A branch
  with no merged PR is UNDETERMINED, not clean.
- Input B: the branch's **declared** contexts (`CHECKS` or `CHECKS_DEV`, via
  `build_payload`), not live protection. Live-vs-declared is already
  `check_one`'s job, and comparing against the table keeps the two checks
  independent.
- Rule: any name in A matching `/\bblocking\b/i` that is not in B is a
  divergence. Print `MISLABEL <repo>@<branch>: "<name>" claims blocking but
  is not required` and set `DIVERGED=1`, so the existing exit codes and the
  "what to do when red" step apply unchanged.
- A test hook (`--blocking-stdin <repo> <branch>`, in the style of
  `--normalise-stdin`) reads a JSON list of names from stdin and applies the
  rule offline, so the gate is tested without a token.

### 2. Per-check decision: measure, then promote or rename

For each "blocking"-named check, plus the three guards the issue names
(collected-path, vendored `factory_common` drift, CFactory card-models
contract), measure the last 20 merged PRs into the default branch:

- reported on 20/20, and its failures (if any) were real catches rather than
  flakes: **promote**, adding it to `CHECKS`/`CHECKS_DEV` in `repo_config()`;
- not reported on every PR (path filter, `if:` skip): **rename**, dropping
  "blocking" in that repo's workflow, and file a follow-up issue to remove
  the filter if it should be promoted later;
- flaky: **rename**, plus a follow-up issue.

The measured table and each verdict are recorded in the plan.

Two defects found while measuring, fixed in the same pass:

- AIFactory posts a context literally named `frontend lint + format
  (blocking,`, a truncated job name (probably unquoted YAML). Fix the name
  first; promote whatever it becomes.
- `main` vs `dev`: promote on the branches where the job posts on PRs. Promote
  PRs into `main` are measured separately (input A per branch).

### 3. Rollout

1. Hub PR: table changes, the gate and its tests. Check mode will report
   DRIFT (table ahead of live) until each repo is applied. That is expected,
   and the drift job is advisory-on-schedule, not a PR gate.
2. Rename PRs in the service repos, where a check is renamed rather than
   promoted. These must merge before the hub gate is turned on, or the gate
   is red on day one.
3. `--apply --repo <R>` per repo, **each with explicit user approval**, after
   an agent-bus announcement. `assert_no_strip` already blocks any apply that
   would remove a context, so this can only add.
4. The nightly drift job goes green: proof that table, live protection and
   names agree.

## Alternatives rejected

- **A per-repo PR job.** Reading protection needs the admin PAT, which fork
  PRs cannot see, and five copies of the logic would drift. The hub already
  owns this comparison.
- **Parse workflow YAML for job names.** Matrices, expressions and reusable
  workflows make that a parser project. Check runs are what GitHub actually
  reports, which is what protection matches on.
- **Rename everything** (drop "blocking" fleet-wide). It is cheaper, but it
  gives up the enforcement the names were written to promise. The intent
  makes promotion the default.
- **Rulesets instead of classic protection.** The script and the gitops bot
  rely on classic protection (header of `apply_branch_protection.sh`). That
  is out of scope.
- **Also match "Gate N" or "must".** No name today needs it, and it would add
  false positives (#943 owns the security gates).

## Risks

- **A promoted check that stops posting blocks every PR forever.** Mitigated
  by the 20/20 rule and by the existing
  `test_every_required_context_matches_a_real_job_name` pattern. A path
  filter added later would reintroduce it, so the gate's message names it.
- **A newly required flaky check stalls the autonomous merger** in that
  repo. It is visible as a PR pending on that context. Rollback: drop the
  context from the table and `--apply` (removal needs the guard's explicit
  override, which is the intended friction).
- **Token scope.** The drift PAT has Administration and Metadata read.
  Reading check runs and PR lists on these public repos needs no more. If
  that fails, the gate reports UNDETERMINED (exit 2), never green.
- **A rename changes the context string.** Any branch that already requires
  the old name would block. The gate's input B catches this, because the
  table must match the new name.

## Verification

- Offline (`tests/test_branch_protection_intent.py`): through the
  `--blocking-stdin` hook, an unrequired "(blocking)" name is reported
  (mutation proof), a required one is clean, a non-blocking advisory name is
  clean, the match is case-insensitive and word-bounded, and an empty input
  is UNDETERMINED.
- The existing suite stays green, including job-name matching for
  Factory/main.
- Live: `bash scripts/apply_branch_protection.sh` (check mode) prints no
  `MISLABEL` lines and exits 0 after the rollout. Before the rollout it lists
  exactly the advisory names measured in the plan.
- Per promoted repo: the next PR shows the new contexts as **Required** in
  the checks list.
