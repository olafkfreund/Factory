---
status: approved
issue: 943
intent: intent/2026-10-22-943-enforce-admins-main.md
---

# Spec: enforce_admins on main for the five code repos

## Design

Chosen: option 2 of #943, the owner's decision. `enforce_admins` is ON for
`main` of AIFactory, PFactory, TFactory, CFactory and Factory, and OFF for
factory-gitops `main` and for every `dev` branch.

`scripts/apply_branch_protection.sh` has one `ENFORCE_ADMINS` per repo, applied
to every branch in `BRANCHES`. Add a per-branch override in the same shape as
`CHECKS_DEV`:

- `repo_config()` resets `ENFORCE_ADMINS_MAIN=""` at the top, next to
  `CHECKS_DEV=""`, so a value cannot leak from one repo to the next.
- The five code repos set `ENFORCE_ADMINS_MAIN=1`. factory-gitops does not set it.
- In `build_payload()`, the `main` arm uses `ENFORCE_ADMINS_MAIN` when it is set
  and falls back to `ENFORCE_ADMINS`. `dev` always uses `ENFORCE_ADMINS` (0).
- The comment near line 115 that justifies `enforce_admins=0` is rewritten. It
  records the decision, why gitops and dev stay 0, and the break-glass step.
  Break glass: rerun `--apply --repo <R>` with `ENFORCE_ADMINS_MAIN=0` in that
  repo's arm (or `gh api -X DELETE repos/<owner>/<R>/branches/main/protection/enforce_admins`),
  merge, then restore it and re-apply. Check mode flags the window as drift
  until it is restored.
- `docs/compliance/branch-protection.md` gets the same decision recorded where it
  says `enforce_admins` is false everywhere.

No GitHub call is made in this change. Check mode reports drift on the five
`main` branches until the owner runs `--apply`.

### What was verified before choosing (nothing relies on admin bypass into main)

Read from `origin/main` of each repo (AIFactory also at `origin/dev`):

- **Pushes to main from workflows.** `release.yml` (AIFactory, PFactory,
  TFactory) pushes only a `v<version>` tag. Every `deploy.yml`, AIFactory
  `build-nix.yml` and TFactory `portal-ui-runner-image.yml` clone and push to
  factory-gitops, not their own main. AIFactory `techdocs.yml` pushes to the PR
  head ref or `dev`, never main. Factory `model-probe.yml` does `git push` to
  Factory main with the default `GITHUB_TOKEN` (github-actions[bot], not an
  admin). The admin bypass never applied to that push, so the change does not
  affect it. Its recent runs all hit "nothing added to commit". This latent
  issue predates this change and is noted here only.
- **dev to main promotion.** Done as `release/<version>` PRs into main, merged
  by the owner through the normal PR flow. The last 15 merged PRs into main of
  each of the five repos show no failing required context. The only failures are
  `secrets (P2 acceptance)` on PFactory#788 and TFactory#1332, and that context
  is not required. A promotion merged with green checks is unaffected.
- **Factory auto-merge loop.** Every AIFactory merge path
  (`pr_endgame.py:1195,1213`, `services/approval.py:141`,
  `pr_data_service.py:421`, `github_provider.py:192,237`, `gh_client.py:602`)
  runs `gh pr merge` without `--admin`. The 2026-10-07 probe on #943 showed
  that call is already refused on a red required check even for an admin. The
  dependabot automerge workflows use `gh pr merge --auto`, which waits for
  checks. Neither depends on the bypass.
- **factory-gitops** does depend on it: the CD bot pushes directly to main.
  It stays 0.

Scope: Trivy stays out of the required set. The script does not name it, and
promoting CodeQL, security lint and Trivy is part 1 of #943, which is not
decided here. This PR therefore refs #943 and does not close it.

## Alternatives rejected

- **Option 1, leave false everywhere.** Rejected by the owner: the floor would
  keep holding only by client convention.
- **Option 3, enable everywhere.** Rejected: it breaks the factory-gitops CD
  bot, and it removes the incident bypass on `dev`.
- **Flip per-repo `ENFORCE_ADMINS=1`.** Rejected: it would also turn the option
  on for `dev`, because one value covers every branch in `BRANCHES`.
- **Ruleset with bypass actors.** Rejected: more moving parts, and the script
  manages classic protection.

## Risks

- After `--apply`, an incident merge into main needs the break-glass step.
  This is the intended trade.
- `strict: true` and conversation resolution on main now bind admins too. A
  release PR must be up to date with main and have its conversations resolved.
  That is already the normal flow.
- Until `--apply` runs, the nightly drift gate (`branch-protection-drift.yml`)
  reports the five main branches as drifted. This is expected, and it is the
  signal to apply.

## Verification

- `bash scripts/apply_branch_protection.sh --emit <repo> <branch>` shows
  `enforce_admins: true` for the five code repos' `main`, and `false` for their
  `dev` and for factory-gitops `main`.
- A new parametrized test asserts this for every declared pair.
- The existing live-shape fixtures for main rows carry `enforce_admins: true`.
- `pytest tests/test_branch_protection_intent.py` passes. `ruff` passes on the
  test file. `shellcheck` passes on the script, if it is available.
- `--plan` mode is offline and is not run, because it fetches nothing but needs
  `gh` auth for some checks. `--emit` is the offline dry run.
