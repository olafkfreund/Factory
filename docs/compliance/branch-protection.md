# Branch protection as code (Factory#316, Factory#468)

Status: APPLIED and drift-checked. Protection is live on `main` in all six
repos and on `dev` in the four service repos, and a scheduled job now compares
the live configuration against the declared intent every day.

The intent is codified in `scripts/apply_branch_protection.sh`. **Check is the
default mode**: run with no arguments and it reads live protection, diffs it
against the intent, prints every divergence and exits non-zero, writing
nothing. Writing requires an explicit `--apply`.

```bash
scripts/apply_branch_protection.sh                     # CHECK everything (default)
scripts/apply_branch_protection.sh --repo TFactory     # CHECK one repo
scripts/apply_branch_protection.sh --plan              # print intended payloads
scripts/apply_branch_protection.sh --apply --repo CFactory   # WRITE one repo
```

Exit codes in check mode: `0` matches, `1` drift, `2` could not determine (tool
missing, a declared branch does not exist, or the token cannot read protection).
A check that cannot reach the input it compares against fails rather than
reporting green, per `standards/coding-standards.md` rule 4.7.

## Why check mode had to be the default (Factory#468)

Three repos (AIFactory, PFactory, TFactory) also carried a per-repo
`scripts/setup-branch-protection.sh`, byte-identical apart from the repo name,
which their `CONTRIBUTING.md` told a maintainer to run after a fresh clone and
described as idempotent. It was apply-only and it had drifted:

- it required the check context `frontend (typecheck)` where live required
  `critical (fast PR gate)`, so it would have silently swapped which gate blocks
  a merge; and
- it applied `main`'s payload to `dev` as well, so it would have reimposed a
  review requirement, a CODEOWNERS requirement, `strict` and
  conversation-resolution on the integration branch - reversing a deliberate
  decision (see "Why `dev` is looser" below) with no warning that it had.

Correcting the payload was a one-time patch. The defect was that nothing
compared intent against live, so the file could be truth on the day it was
written and a landmine a month later. Those three copies are deleted; this
script is the fleet's only branch-protection tool, and its default action is to
report rather than overwrite.

## Automated drift detection

`.github/workflows/branch-protection-drift.yml` runs check mode daily (and on
`workflow_dispatch`). It is scheduled rather than PR-triggered because
protection drifts through the UI or `gh api`, never through a pull request.

It requires the repo secret `BRANCH_PROTECTION_TOKEN`: a fine-grained PAT with
repository **Administration: read** (plus Metadata: read) on the six fleet
repos. The Actions `GITHUB_TOKEN` cannot do this job - reading branch protection
is admin-only and `administration` is not one of the permission scopes available
under `permissions:` at all, so no workflow-permission setting makes it work.
When the secret is absent the workflow **fails**; it does not skip.

The comparator itself is tested offline on every pull request by
`tests/test_branch_protection_intent.py`, which proves it both ways (rule 4.9):
a live response matching intent compares equal, and a live response differing in
any one field compares unequal.

## Why this needs care

Several repos have automation that writes to `main` (directly or by merge).
Naively requiring pull requests and reviews on every `main` would break those
bots. Before requiring anything we mapped exactly who pushes where, so the
protection can exempt the automation that has to keep working.

The one repo with genuine direct-to-main automation is `factory-gitops`: the
deploy workflows in TFactory, PFactory, AIFactory and CFactory push image-tag
bump commits straight to `factory-gitops` main (committer `github-actions[bot]`,
authenticated with the `GITOPS_PAT` secret), and ArgoCD auto-syncs from there.

## Current state (read live, 2026-07-30)

Source: `gh api repos/olafkfreund/<repo>/branches/<branch>/protection`. This is
also what `scripts/apply_branch_protection.sh` declares, so check mode is green
against it; if this table and the script ever disagree, the script is the
authority and this table is stale.

| Repo / branch | Required checks | Strict | Reviews | CODEOWNERS | Conv. resolution |
| --- | --- | --- | --- | --- | --- |
| Factory / main | `ruff + mypy ratchet (diff-scoped, blocking)`, `ruff format --check (scripts, blocking)` | yes | 1 | no | yes |
| AIFactory / main | `backend (ruff + pytest)` | yes | 1 | yes | yes |
| AIFactory / dev | `backend (ruff + pytest)` | no | none | - | no |
| PFactory / main | `backend (ruff + pytest)`, `critical (fast PR gate)` | yes | 1 | yes | yes |
| PFactory / dev | same two | no | none | - | no |
| TFactory / main | `backend (ruff + pytest)`, `critical (fast PR gate)` | yes | 1 | yes | yes |
| TFactory / dev | same two | no | none | - | no |
| CFactory / main | `Backend pytest`, `Frontend typecheck + build` | yes | 1 | no | yes |
| CFactory / dev | same two | no | none | - | no |
| factory-gitops / main | none | - | none | - | yes |

`enforce_admins` is `false` everywhere, force-pushes and branch deletion are
blocked everywhere, no repo has push restrictions, and no repo uses rulesets.
`Factory` and `factory-gitops` have no `dev` branch, so none is declared for
them; a declared branch that does not exist is an error in check mode, not a
skip.

### Why `dev` is looser than `main`

`dev` is the default branch in all four service repos and the branch PRs target.
It carries **the same required CI checks as `main`** - the gate set is not
relaxed - but deliberately has no review requirement, no `strict` up-to-date
requirement and no conversation-resolution gate:

- a solo maintainer has nobody to approve their own PR, and the factory's own
  agents merge their work unattended, so a review requirement on the integration
  branch stalls every merge; and
- `strict` forces a rebase before each merge, which serialises integration for
  no safety benefit on a branch that is itself gated by CI and promoted to `main`
  behind a review.

`main` keeps the full set because it is the release branch and receives only
promotion merges from `dev`.

This is a decision, not drift. Anything that "corrects" `dev` up to `main`'s
payload is reverting it - which is precisely what Factory#468 was filed about.

## Automation identities that write to main

Determined by reading `.github/workflows/*` across the sibling checkouts and the
`factory-gitops` commit log (read-only).

| Repo | What writes to its main | How | Needs bypass? |
| --- | --- | --- | --- |
| factory-gitops | `github-actions[bot]` CD bump commits (`cd(<svc>): sha-... [skip ci]`) | `deploy.yml` in each service clones gitops with `GITOPS_PAT` and `git push` directly to main; ArgoCD auto-syncs | YES - direct push to main |
| AIFactory | The AIFactory app (code writer) | Commits to a feature branch, opens a PR - never pushes main | No (PR path) |
| TFactory | `tools/git_writer.py` (Triager) | Commits accepted tests to the feature branch under test, dry-run by default - never pushes main | No (PR path) |
| PFactory / AIFactory / TFactory / CFactory | `deploy.yml` | Triggered by push to main, but writes to `factory-gitops`, not its own main | No |
| PFactory / AIFactory / TFactory | `release.yml` | Pushes a `v<version>` git tag only (no commit to main) | No (tags are not gated by main protection) |
| all code repos | Factory auto-merge loop (PARR endgame) | Runs `gh pr merge` with an admin token after CI + Copilot review | Bypass via admin (see below) |

Conclusion: the only identity that must be allowed to push directly to `main` is
the `GITOPS_PAT`-authenticated CD bot on `factory-gitops`. Everything else
already flows through feature branches and pull requests.

## How the bypass works (and the one assumption to verify)

We use classic branch protection rather than a ruleset. With classic protection,
`enforce_admins=false` means anyone with the admin role - and any token they own
- bypasses the pull-request and review requirements and can push directly to
`main`. The plan sets `enforce_admins=false` everywhere, which:

- lets the `factory-gitops` CD bot keep pushing bump commits, and
- lets the PARR auto-merge loop merge with an admin token even if a required
  review is momentarily missing.

Assumption to verify before `--apply` on factory-gitops: `GITOPS_PAT` is owned
by an account with the admin role on `factory-gitops` (expected: `olafkfreund`).
Confirm by checking the secret's owner, or simply watch the next CD bump after a
staged apply. If `GITOPS_PAT` is ever moved to a non-admin machine user, switch
factory-gitops to a ruleset with an explicit bypass actor (repository-role admin
`actor_id=5`, or a dedicated GitHub App / deploy key) instead of relying on the
admin bypass.

Ruleset alternative (documented, not used here): create a ruleset targeting
`refs/heads/main` explicitly - NOT `~DEFAULT_BRANCH`, which since Factory#455
resolves to `dev` in all four service repos and would apply main's rules to the
integration branch - with `bypass_actors: [{actor_type: RepositoryRole, actor_id:
5, bypass_mode: always}]` and the same rules (pull_request, required
status checks, non_fast_forward, deletion). Rulesets give a named bypass list
instead of the blanket admin bypass; the trade-off is more moving parts. Classic
protection was chosen because it is already in use on three repos and the admin
bypass cleanly covers the single CD-bot case.

## Intended protection

Declared in `repo_config()` and `build_payload()` in
`scripts/apply_branch_protection.sh` - that table is the authority. On `main`,
for the five code repos (Factory, PFactory, AIFactory, TFactory, CFactory):

- Require a pull request before merging, with at least 1 approving review.
- Dismiss stale approvals on new pushes.
- Require the repo's CI gate as a status check, and require the branch to be up
  to date (`strict=true`).
- Require code-owner review where a `CODEOWNERS` file exists (PFactory,
  AIFactory, TFactory). Factory and CFactory have no `CODEOWNERS` yet, so
  code-owner review stays off until one is added (adding it is a follow-up).
- Require conversation resolution.
- Block force-pushes and branch deletion.
- `enforce_admins=false` so the auto-merge loop and admin operations keep
  working. Tightening to `true` is a later phase, per repo, once we confirm no
  automation depends on the bypass.

On `dev`, for the four service repos: the same required status checks, force-push
and deletion still blocked, but no review requirement, `strict=false` and no
conversation-resolution gate - see "Why `dev` is looser than `main`" above. The
script derives the `dev` payload from the same per-repo check list, so the two
branches cannot drift apart in the check set they require.

Required status-check contexts per repo (exact context strings, identical on
`main` and `dev`):

| Repo | Required checks |
| --- | --- |
| Factory | `ruff + mypy ratchet (diff-scoped, blocking)`, `ruff format --check (scripts, blocking)` |
| PFactory | `backend (ruff + pytest)`, `critical (fast PR gate)` |
| AIFactory | `backend (ruff + pytest)` |
| TFactory | `backend (ruff + pytest)`, `critical (fast PR gate)` |
| CFactory | `Backend pytest`, `Frontend typecheck + build` |

These are job **display names** as they appear on a PR, not workflow job ids, and
they genuinely differ between CFactory and the Python services. That difference
is why a single script with one hardcoded check list cannot serve the fleet, and
why the deleted per-repo copies were wrong the moment they were vendored: each
declared one repo's names for a repo whose jobs are named differently.

Note that all three Python services also run `frontend (typecheck)`,
`frontend (vitest)` and `frontend (eslint, blocking)` on every PR, and those jobs
are green - they are simply not in the *required* set. The required set is a
deliberate subset (2 of TFactory's 24 jobs), so it cannot be derived from the
workflow file; it has to be declared, which is what this table is for.

factory-gitops is the exception: it is bot-driven CD, so it gets no PR-review
requirement and no required checks. It only blocks force-push and branch
deletion (so ArgoCD's committed history cannot be rewritten or dropped) and
keeps `enforce_admins=false` so the CD bot bypasses.

### TFactory verification as a required check

The task calls for the TFactory verification result to be a required check where
it exists. TFactory posts a commit status `tfactory/suite` (and
`tfactory/coverage`) on the PRs it verifies. This is off by default in the
script because a required status blocks any PR that never receives that status -
so making it blocking before it reliably posts on every PR would freeze merges.

Rollout: once `tfactory/suite` is confirmed to post on every pull request for a
repo, enable it by running the script with `WITH_VERIFY=1` (currently wired for
AIFactory and TFactory, the repos in the verification path). This is phase 3
below.

## Rollout order

Steps 1-4 are DONE: `main` is protected in all six repos and `dev` in the four
service repos, verified green by check mode on 2026-07-30. Remaining phases:

- **Phase 3 - verification gate.** Once `tfactory/suite` is confirmed to post on
  every pull request for a repo, enable it with `WITH_VERIFY=1` (wired for
  AIFactory and TFactory). Still off: a required status blocks any PR that never
  receives it. Applies to `main` only - the script does not add it to `dev`,
  because a verification status that has not run yet would stall integration.
- **Phase 4 - tighten `enforce_admins` to `true`** per repo, only after
  confirming no automation relies on the admin bypass for that repo, and after
  adding `CODEOWNERS` to Factory and CFactory so code-owner review can be
  required there too.

When a phase lands, change the intent table and let check mode confirm; do not
apply a change and leave the table describing the old world. That gap is the
whole of Factory#468.

## Rollback

Classic protection can be removed per branch with
`gh api -X DELETE repos/olafkfreund/<repo>/branches/<branch>/protection`, which
leaves that branch unprotected. Because the PUT replaces the whole protection
object, `--apply` also converges a branch back to the intended baseline if
someone edits it by hand in the UI.

That convergence is the sharp edge: `--apply` does not merge, it overwrites. If
someone changed protection deliberately and the intent table was not updated to
match, `--apply` silently reverts them. So when check mode goes red, read the
diff and decide which side is wrong before running anything - that is why check
is the default and apply is opt-in.
