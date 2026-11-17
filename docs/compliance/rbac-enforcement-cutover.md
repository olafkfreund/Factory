# Runbook: enforce task-route roles in PFactory and TFactory

- **Owner:** Security Owner ([roles.md](roles.md)). The owner flips the flag; an agent does not.
- **Design:** [rbac-role-catalog.md](rbac-role-catalog.md), `spec/2026-11-17-312-iam-residuals.md` (Factory#312)

PFactory and TFactory compute the org-role decision for task, plan and project routes but only log it: `RBAC_ENFORCE_TASK_ROUTES` is `False` (`apps/web-server/server/config.py`, read by `routes/project_authz.py` and `websockets/events.py` on `origin/dev`). The environment variable is `APP_RBAC_ENFORCE_TASK_ROUTES`. It is unset in factory-gitops, so it is off in the cluster. AIFactory already enforces. A wrong flip locks people out of their own projects, so this is a staged change with a way back.

## Before the flip

1. **Shadow log is clean.** Over at least one review window, the service logs show no would-deny line for a request that should have been allowed. Read: `kubectl -n factory logs deploy/<pfactory|tfactory> | grep -iE 'rbac.would.deny|RBAC would deny'` (read-only; PFactory logs `rbac.would_deny`, TFactory `RBAC would deny (shadow)` with audit action `authz.task.would_deny`). Every line must be explained: a real viewer on a write route, or an API key of another org.
2. **Every project has an `org_id`.** An unassigned project is refused in enforce mode ("Project is not assigned to an organization"). PFactory's column is `NOT NULL` on `origin/dev`; check TFactory's and any row created before that constraint.
3. **The owner is an `owner` member** of each org, in each service's database, so the owner cannot be the one refused. Service principals (`is_service`) bypass the per-org check by design.
4. **A way back is ready:** the revert in step 3 below is one commit to factory-gitops; you know who merges it.

## The flip

One service at a time, TFactory first (smaller surface), then PFactory after a day with no complaints.

1. In `factory-gitops`, add to that service's Deployment env: `- { name: APP_RBAC_ENFORCE_TASK_ROUTES, value: "true" }`. Open a PR, merge it; Argo CD syncs.
2. Verify: a `viewer` is refused (403) on a task write route and a `member` is not; the audit log shows refusals (`authz.denied`, `gate.rejected` in PFactory) only for such requests; the cockpit and the other services' keys still work. A `viewer` may still read.
3. Record the date, the service and the verification in the quarterly access review ([access-review-runbook.md](access-review-runbook.md)); update the "flag off" rows in the role catalog.

## Rollback

Remove the variable (or set it to `"false"`) in the same Deployment, merge, let Argo sync. No data changes. Shadow mode resumes.
