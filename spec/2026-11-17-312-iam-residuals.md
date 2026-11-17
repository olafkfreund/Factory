---
status: draft
issue: 312
intent: intent/2026-11-17-312-iam-residuals.md
---

# Spec: IAM residue, DISABLE_AUTH guard and role-enforcement runbook

## Design

1. **Evidence.** On `origin/main` of factory-gitops, `grep -rIiE disable_auth` finds the flag only in `docs/` prose. In AIFactory, PFactory, TFactory and CFactory `origin/dev` it appears in CI test env, `.env.example` comments, a demo script and a Helm values comment, never in a manifest that deploys.
2. **Guard.** `scripts/check-no-disable-auth.sh` in factory-gitops fails if any file outside `docs/` mentions `DISABLE_AUTH` (case-insensitive, so `APP_DISABLE_AUTH` too), has a `--self-test` with clean, dirty, lowercase and missing-root fixtures, and runs from `.github/workflows/no-disable-auth.yml` on every PR and push to `main` (no paths filter, so a required check never goes missing). Any mention fails, even `false`: there is no reason for the name to be in a deployable file. The services also refuse the flag off loopback; this is the second layer.
3. **Runbook.** `docs/compliance/rbac-enforcement-cutover.md`: preconditions (shadow log clean, every project has an `org_id`, the owner has an `owner` membership and a break-glass way back), the flip (`RBAC_ENFORCE_TASK_ROUTES` in the PF/TF Deployment env in factory-gitops, one service at a time, TFactory first because it is smaller), verification, rollback (remove the env var, Argo syncs). Linked from the role catalog and the IAM policy.

## Alternatives rejected

- Kyverno policy: admission-time, after merge and sync; CI fails the PR instead. A cluster policy also needs a Kyverno test suite and a rollout in the live cluster.
- Hub (Factory) check: the hub does not hold production manifests.
- Flip the flag now: the owner's decision, a wrong flip locks people out.

## Risks

A grep misses values injected from a Secret or ConfigMap, and misses a renamed variable; mitigated by the services' own off-loopback refusal. A false positive is fixed by moving the text into `docs/`.

## Verification

`sh scripts/check-no-disable-auth.sh --self-test` and `sh scripts/check-no-disable-auth.sh` pass on the PR; the workflow is green on the PR head; the runbook's file and symbol references are re-read against PFactory and TFactory `origin/dev`.
