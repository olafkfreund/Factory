---
status: approved
issue: 3585
intent: intent/2026-10-15-3585-unfilter-fgithub-drift.md
---

# Spec: let the factory-github drift gate post on every PR, then require it

## Design

Two halves, in this order, mirroring #525 / #543 for the verification-core
gate.

**Half 1: unfilter (service repos, one PR each to `dev`).** In
`.github/workflows/factory-github-drift.yml` of AIFactory, PFactory,
TFactory and CFactory, delete the `paths:` list under `pull_request`
(`:15-17`), leaving `pull_request: branches: [dev, main]`, and add a
one-line comment pointing at Factory#3585. The `push` trigger keeps its
`paths:` filter: only the PR trigger feeds a required check, and a push to
`dev` that touches no vendored path cannot introduce drift the PR did not
already show. The job name `factory-github canonical drift` is unchanged.

**Half 2: require (hub, one PR).** In `scripts/apply_branch_protection.sh`
add `FGITHUB_CTX="factory-github canonical drift"` next to
`COLLECTED_CTX`/`FCOMMON_CTX` (`:138-140`), with a comment recording the
order, and add `"$FGITHUB_CTX"` to `CHECKS` and `CHECKS_DEV` of CFactory,
PFactory, TFactory and AIFactory (`repo_config`, `:228-234`), right after
`$FCOMMON_CTX`. CFactory has no `CHECKS_DEV` (same set on both branches).
In `tests/test_branch_protection_intent.py` add `_FGITHUB`, put it in the
four service-repo lists of `test_check_contexts_are_per_repo` and assert it
in `test_service_repos_require_the_shared_measured_guards` (both branches),
and keep it out of Factory and factory-gitops.

The hub PR is merged only after the four service PRs are merged and the
gate has been seen posting on a PR in each repo whose diff touches no
vendored path. Before `--apply`, `dev` must also have been promoted to
`main` in each repo: `git show origin/main:.github/workflows/factory-github-drift.yml`
has no `paths:` under `pull_request`. Otherwise a hotfix PR into `main`
waits forever on a check that never posts. Then the lead runs
`scripts/apply_branch_protection.sh --apply` for the four repos. PRs
already open at that point need a push, a close/reopen or
`@dependabot rebase` to get the check. This lane makes no live change.

## Alternatives rejected

- **Require it now, unfilter later / in the same breath.** A required check
  that never posts wedges every PR; that is the hazard the script's comments
  for `$VERIFY_CTX` and `$VCORE_CTX` warn about.
- **Leave the filter and keep it advisory.** Drift between a vendored copy
  and the hub is then caught only when a PR happens to touch the copy, and
  a red advisory check is scrolled past (#805).
- **Also drop the `push` paths filter.** Extra runs on every push to
  `dev`/`main` for no protection gain; the required check is the PR one.
- **Merge into a separate "drift" workflow.** More churn than deleting
  three lines.

## Risks

- If the hub PR merges and `--apply` runs before a service PR merges, PRs
  in that repo wedge waiting for a check that does not post. Mitigation: the
  ordering above, written in the hub PR body.
- Between merging the hub PR and running `--apply`, the nightly
  `branch-protection-drift` job reports the four repos as drifted. That is
  the intended "intent changed, apply it" signal.
- The gate fetches from the hub; a hub outage now fails every PR instead of
  a few. Same exposure the verification-core gate already has.
- The gate runs the hub's checker from hub `main` (`HUB_CHECKER_REF`,
  Factory#405), so a broken `check_factory_github_drift.py --self-test` on
  hub `main` blocks every PR in all four service repos, not a few.
  Accepted, as for the verification-core gate; fix forward in the hub.

## Verification

- Service PRs: the gate posts on the PR itself (the workflow file is in its
  diff either way), and, after merge, on the next PR that touches no
  vendored path. The lead records that observation before merging the hub PR.
- Hub: `pytest tests/test_branch_protection_intent.py` passes with the new
  assertions and fails if `FGITHUB_CTX` is removed from any service repo.
  `ruff check`, `ruff format --check` and the ratchet clean.
