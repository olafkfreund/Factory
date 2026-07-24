# Branch protection as code (Factory#316)

Status: PLAN. Nothing in this document has been applied. It describes the
current state of `main` branch protection across the Factory fleet, the
intended protection, which automation identities must keep pushing, and the
order in which to roll it out.

The plan is codified in `scripts/apply_branch_protection.sh`, which is dry-run
by default and only writes protection when passed `--apply`.

## Why this needs care

Several repos have automation that writes to `main` (directly or by merge).
Naively requiring pull requests and reviews on every `main` would break those
bots. Before requiring anything we mapped exactly who pushes where, so the
protection can exempt the automation that has to keep working.

The one repo with genuine direct-to-main automation is `factory-gitops`: the
deploy workflows in TFactory, PFactory, AIFactory and CFactory push image-tag
bump commits straight to `factory-gitops` main (committer `github-actions[bot]`,
authenticated with the `GITOPS_PAT` secret), and ArgoCD auto-syncs from there.

## Current state (discovered read-only, 2026-07-24)

Source: `gh api repos/olafkfreund/<repo>/branches/main/protection` and
`.../rulesets`.

| Repo | Protection today | Rulesets |
| --- | --- | --- |
| Factory | None (HTTP 404, branch not protected) | none |
| AIFactory | None (HTTP 404, branch not protected) | none |
| factory-gitops | None (HTTP 404, branch not protected) | none |
| PFactory | Weak: required checks `backend (ruff + pytest)`, `critical (fast PR gate)`; `strict=false`; `enforce_admins=false`; no required PR reviews; force-push/deletion already blocked | none |
| TFactory | Weak: same as PFactory | none |
| CFactory | Weak: required check `Backend pytest` only; `strict=false`; `enforce_admins=false`; no required PR reviews; force-push/deletion already blocked | none |

Key gaps versus the target: three repos have no protection at all; the three
weak repos do not require a pull request or any review to land on `main`, do not
require the branch to be up to date (`strict=false`), do not enforce for admins,
and do not require code-owner review. No repo uses rulesets.

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
`~DEFAULT_BRANCH` with `bypass_actors: [{actor_type: RepositoryRole, actor_id:
5, bypass_mode: always}]` and the same rules (pull_request, required
status checks, non_fast_forward, deletion). Rulesets give a named bypass list
instead of the blanket admin bypass; the trade-off is more moving parts. Classic
protection was chosen because it is already in use on three repos and the admin
bypass cleanly covers the single CD-bot case.

## Intended protection

Applied by `scripts/apply_branch_protection.sh`. Baseline for the five code
repos (Factory, PFactory, AIFactory, TFactory, CFactory):

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

Required status-check contexts per repo (exact context strings):

| Repo | Required checks |
| --- | --- |
| Factory | `ruff + mypy ratchet (diff-scoped, blocking)`, `ruff format --check (scripts, blocking)` |
| PFactory | `backend (ruff + pytest)`, `critical (fast PR gate)` |
| AIFactory | `backend (ruff + pytest)` |
| TFactory | `backend (ruff + pytest)`, `critical (fast PR gate)` |
| CFactory | `Backend pytest`, `Frontend typecheck + build` |

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

Apply incrementally, least-risky first, verifying the deploy bots still work
before widening. Every step is a manual `--apply` on one repo; nothing is
automated.

1. CFactory (pilot). Lowest blast radius: no direct-to-main automation, small
   check set. Apply, then open a throwaway PR and confirm it must pass CI + one
   review to merge, and that the CFactory `deploy.yml` still bumps
   factory-gitops on the next merge to main.
2. Factory (hub). Human-driven, no service deploy. Apply and confirm normal PR
   flow.
3. factory-gitops. Apply the force-push/deletion-only protection. Immediately
   trigger or wait for the next service deploy and confirm the
   `github-actions[bot]` CD bump still lands on main (this is the critical
   bypass check). If it fails, the `GITOPS_PAT` owner is not an admin - switch
   to the ruleset-with-bypass-actor form before proceeding.
4. PFactory, then TFactory, then AIFactory. Apply one at a time. After each,
   confirm: (a) the PARR auto-merge loop can still merge a green PR, and (b)
   `release.yml` tag pushes and `deploy.yml` gitops bumps still work.
5. Phase 3 - verification gate: once `tfactory/suite` is confirmed to post on
   every PR, re-apply AIFactory and TFactory with `WITH_VERIFY=1`.
6. Phase 4 - tighten `enforce_admins` to `true` per repo, only after confirming
   no automation relies on the admin bypass for that repo, and after adding
   `CODEOWNERS` to Factory and CFactory so code-owner review can be required
   there too.

## Rollback

Classic protection can be removed per repo with
`gh api -X DELETE repos/olafkfreund/<repo>/branches/main/protection`, which
returns each branch to its current unprotected/weak state. Because the PUT
replaces the whole protection object, re-running the script also converges a
repo back to the intended baseline if someone edits it by hand in the UI.
