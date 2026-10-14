---
status: approved
issue: 1026
author: olafkfreund
---

# Intent: a check named "blocking" must be able to block

## Problem

Fleet CI checks advertise enforcement in their names ("blocking") that branch
protection does not give them. `gh pr merge --auto` (used by the autonomous
merger, `github_provider.py`) waits only on required contexts, and no branch
has required reviews or `enforce_admins`. So a red advisory check stops nobody.

Measured 2026-10-14 against each default branch head and its
`required_status_checks.contexts`: **14 of 17** checks whose name contains
"blocking" are advisory.

| repo | advisory "blocking" checks |
|---|---|
| Factory | committed output matches inputs |
| PFactory | Gate 5 banned constructs; frontend eslint; ratchet ruff + mypy; ruff format |
| TFactory | Gate 5 banned constructs; frontend eslint |
| CFactory | Gate 5 banned constructs; frontend lint/format/unit; ruff + mypy ratchet; ruff check; ruff format |
| AIFactory | Gate 5 banned constructs; frontend lint + format |

The issue also names checks without the word that guard known-recurring
failures and are advisory: "every test file is inside a collected path",
"vendored factory_common matches the hub canonical", and CFactory's
"card models match the hub contract".

Nothing stops the mismatch coming back: a new job named "(blocking)" can be
added without anyone making it required.

## Proposed outcome

- Every check whose name claims enforcement is in the branch's required
  contexts, or is renamed so it stops claiming it. No third state.
- The three recurring-failure guards above are decided explicitly (promote or
  state why not).
- A gate fails when a "blocking"-named check is not required, so the mismatch
  cannot return silently. Mutation proof: add an unrequired "(blocking)" job
  and the gate goes red.
- Intended protection stays declared in `scripts/apply_branch_protection.sh`,
  so its check mode and live protection agree afterwards.

## Affected users and systems

- Branch protection on Factory `main` and PFactory, TFactory, CFactory,
  AIFactory `dev` (live GitHub settings, applied via
  `scripts/apply_branch_protection.sh --apply`).
- CI workflow job names in those five repos (a rename changes the context
  string).
- The autonomous merger and every open PR: a newly required check that is red,
  flaky, or never reported (path-filtered workflow) blocks merges.

## Constraints

- Applying protection changes live settings on shared repos: per-repo, and
  only with explicit user approval at that step.
- Measure before promoting (the #943 method): a check is promoted only if it
  is green and actually reported on recent default-branch commits and PRs. A
  required check that a path filter skips leaves PRs pending forever.
- Out of scope, stays in #943: CodeQL, security lint, Trivy, and the
  `enforce_admins` decision.
- No `--admin` merges to get round a newly required check.

## Open questions

1. Default when a check is stable: promote it (recommended, it is what the
   name already promises) or rename it?
2. Where the gate runs: inside `apply_branch_protection.sh` check mode, run
   in hub CI on a schedule (recommended, it already reads both sides), or as
   a per-repo PR job?
3. Should the gate match only the literal word "blocking", or also "Gate N"
   and similar enforcement wording?
