---
status: draft
issue: 3585
author: olafkfreund
---

# Intent: let the factory-github drift gate post on every PR, then require it

## Problem

`factory-github canonical drift` (`.github/workflows/factory-github-drift.yml`
in AIFactory, PFactory, TFactory and CFactory) compares each repo's vendored
`apps/backend/runners/github/` against the hub canonical. Its `pull_request`
trigger is filtered by `paths:` (`:13-17`, identical in all four), so it posts
on only 1–2 of the last 20 merged PRs. It therefore cannot be a required
check (a required check that never posts blocks the PR forever), and it is
required nowhere: `scripts/apply_branch_protection.sh` has no context for it.
Drift between a vendored copy and the hub is caught only if the PR happens to
touch the copy. #1026 already dropped "(blocking)" from its name for that
reason.

## Proposed outcome

- The gate posts on every PR into `dev` and `main` in the four service repos.
- After it has been seen posting on an unrelated PR in each repo, the declared
  intent in `scripts/apply_branch_protection.sh` requires it on both
  branches of all four repos, and the intent tests lock that in.

## Affected users and systems

- CI in AIFactory, PFactory, TFactory, CFactory (one more short job per PR).
- Branch protection on `main` and `dev` of those four repos, via the hub
  script. The hub itself and factory-gitops do not carry the workflow.

## Constraints

- Order matters (the #525 precedent for the verification-core gate):
  unfilter first, observe it posting, then require. Requiring first would
  wedge every PR that touches no vendored path.
- No live change from this lane: `apply_branch_protection.sh --apply` is run
  by the lead after the service PRs merge and the observation is made.
- Workflow and script changes only.

## Open questions

None.
