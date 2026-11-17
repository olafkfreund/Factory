---
status: draft
issue: 312
spec: spec/2026-11-17-312-iam-residuals.md
coders:
  1: lead
  2: lead
reviewers:
  - codex   # agy is off by owner decision
---

# Plan: IAM residue, DISABLE_AUTH guard and role-enforcement runbook

Carries the approved spec: evidence by grep (flag only in docs, test env and comments); `scripts/check-no-disable-auth.sh` plus a no-paths-filter workflow in factory-gitops, exempting only the top-level `docs/` and the script, failing on any scan error; a runbook for the owner's `RBAC_ENFORCE_TASK_ROUTES` flip in PFactory and TFactory. The flag is not flipped, no secrets or cluster touched.

Repos: factory-gitops (same PR as #3781: `feat/3781-broker-otp`, the guard is its own commit) and Factory (`docs/3781-312-iam-artifacts`, base `main`, artifacts and runbook).

## Steps

1. factory-gitops `scripts/check-no-disable-auth.sh`, `.github/workflows/no-disable-auth.yml`: the guard → `sh scripts/check-no-disable-auth.sh --self-test` prints `self-test PASS`; `sh scripts/check-no-disable-auth.sh` prints `OK`.
   Traps: workflow text must not itself contain the flag name; pinned action SHA; no `paths:` filter.
2. Factory `docs/compliance/rbac-enforcement-cutover.md`, link from `docs/compliance/rbac-role-catalog.md` and `docs/compliance/README.md`: preconditions, flip, verify, rollback, naming `RBAC_ENFORCE_TASK_ROUTES` (PFactory `apps/web-server/server/config.py`, TFactory same path) and the factory-gitops Deployment env → read against `origin/dev` of both services; mkdocs nav/link check as CI does.
   Traps: do not instruct anyone to flip it as part of this PR; no secrets.

## Tests

`sh scripts/check-no-disable-auth.sh --self-test`, then the plain run, in factory-gitops; the new workflow green on the PR head. Factory docs CI green.

## Rollback

Revert the commits. Removing the workflow removes the guard; nothing at runtime changes.
