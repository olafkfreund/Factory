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

0. Evidence (no file change; recorded in the #312 comment and the PR descriptions): `git grep -nIiE disable_auth <ref>` on factory-gitops `origin/main` (c37ae46 at the time of writing), AIFactory `origin/dev` (60fc1a6b), PFactory (655c7db4), TFactory (f4aab585), CFactory (1e8def2), excluding docs and tests, listing every hit as CI env, `.env.example`, demo script or comment; plus the same grep on the final PR head. Scope: manifests, kustomize and Helm values, workflows, scripts. → no hit in a file that deploys.
1. factory-gitops `scripts/check-no-disable-auth.sh`, `.github/workflows/no-disable-auth.yml`: the guard → `sh scripts/check-no-disable-auth.sh --self-test` prints `self-test PASS`; `sh scripts/check-no-disable-auth.sh` prints `OK`.
   Traps: workflow text must not itself contain the flag name; pinned action SHA; no `paths:` filter.
2. Factory `docs/compliance/rbac-enforcement-cutover.md`, linked from `docs/compliance/rbac-role-catalog.md`, `docs/compliance/README.md` and `docs/compliance/policies/iam-access-control.md`. Contents (all from the approved spec): preconditions (shadow logs show no `rbac.would_deny` for legitimate users over a review window; every project has an `org_id`; the owner holds an `owner` membership in each org; a way back is ready), the flip (one service at a time, TFactory first, by adding `APP_RBAC_ENFORCE_TASK_ROUTES: "true"` to that Deployment in factory-gitops), verification (a `viewer` is refused on a task route, a `member` is not, the audit log shows `authz.denied`/`gate.rejected`), rollback (remove the variable, Argo syncs, no data change). Names `RBAC_ENFORCE_TASK_ROUTES` (PFactory `apps/web-server/server/config.py`, TFactory same path) and the factory-gitops Deployment env → read against `origin/dev` of both services; mkdocs nav/link check as CI does.
   Traps: do not instruct anyone to flip it as part of this PR; no secrets.

## Tests

`sh scripts/check-no-disable-auth.sh --self-test`, then the plain run, in factory-gitops; the new workflow green on the PR head. Factory docs CI green.

## Rollback

Revert the commits. Removing the workflow removes the guard; nothing at runtime changes.
