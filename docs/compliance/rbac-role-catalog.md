# Fleet RBAC Role Catalog

- **Owner:** Security Owner ([roles.md](roles.md))
- **Review cadence:** each quarterly access review ([runbook](access-review-runbook.md))
- **Frameworks:** ISO/IEC 27001:2022 A.5.15, A.5.18, A.8.2; SOC 2 CC6.1-CC6.3; NIST AC-2, AC-6
- **Design:** `spec/2026-10-27-312-fleet-rbac-role-model.md`, `plan/2026-10-27-312-fleet-rbac-role-model.md` (Factory#312)

References name a file and symbol on the service's `origin/dev`, checked 2026-11-16. Re-check them at each review; a line number is not stable enough to cite.

## Principals

| Kind | Identity | Rights come from |
|---|---|---|
| Human | Keycloak subject | The org role stored in each service's database |
| Service principal | `svc:<from>-><to>`, one credential per machine-to-machine edge | A fixed scope set. No org role |
| Agent | `agent:<service>/<key_id>` | The key's scopes, capped by its `autonomy_ceiling` and its owner's current role. Never the invoking human's role |
| `platform-admin` | kubectl, ArgoCD, Keycloak admin accounts | Outside the org model. Held by the owner only. Not grantable from any portal |

## Roles

`viewer < member < admin < owner` (`ROLE_LEVELS` in `apps/web-server/server/routes/organizations.py` of AIFactory, PFactory and TFactory). Inheritance is strictly upward. No new role names. No fleet role is emitted as a JWT `role` claim, and no route trusts a JWT `role`: only `is_service` marks a service principal (`is_service_principal`, AIFactory `routes/project_authz.py`). Roles stay in each service's database; a Keycloak role mapper waits until the task-route checks are enforced.

**Agents never:** approve or merge their own PR, manage members or roles, mint keys, set or raise a ceiling, change `CFACTORY_API_KEYS`, sign a review.

## Action matrix

Minimum role per action. "Flag off" means `RBAC_ENFORCE_TASK_ROUTES` is `False`: the decision is computed and logged but not enforced. The flag is unset in `factory-gitops`, so it is off in the cluster.

| Factory | Action | Min role | Enforced by |
|---|---|---|---|
| AIF, PF, TF | Read org resources | `viewer` | `require_org_role` (`routes/organizations.py`), `check_project_access` (`routes/project_authz.py`) |
| AIF | Create, start, stop, recover a task; approve a plan | `member` | `require_task_access("member")` (`routes/project_authz.py`), enforced |
| PF, TF | Same task and plan routes | `member` | `require_task_access("member")` (`routes/project_authz.py`), **flag off: shadow mode** |
| AIF | Merge a PR the merge policy holds | `member`, never the agent that wrote it | Merge policy tier, not per role |
| AIF | Set a key's `autonomy_ceiling` | `admin` | `routes/api_keys.py` |
| AIF | Export the access review | `admin` | `routes/access_review.py` (`require_org_role("admin")`) |
| AIF, PF, TF | Export the audit log | `admin` | `routes/audit.py`, `/api/audit/export` |
| AIF, PF, TF | Mint own `acw_` key (a `viewer` may mint `mcp:read` only; `mcp:write` needs `member`; an `acw_` key cannot mint) | `viewer` for `mcp:read`, `member` for `mcp:write` | `routes/api_keys.py`; auth-time cap `cap_by_owner_role` (`mcp_remote/auth.py`, PF and TF) |
| AIF, PF, TF | Revoke a key | creator only | **Gap:** `revoke_api_key` matches `ApiKey.user_id == current_user.id`, so an `admin` cannot revoke another member's key (plan slice S4) |
| AIF, PF, TF | Invite a member (never as `owner`, never above the inviter's own role) | `admin` | `invite_member`, `routes/organizations.py` |
| AIF, PF, TF | Change a member's role, transfer ownership | `owner` | `update_member_role`, `routes/organizations.py` |
| AIF, PF, TF | Remote MCP tool calls | key scope and the caller's org role | AIFactory#1917; PFactory#946 and TFactory#1456 are closed, and the surface is off by default |
| CFactory | Cockpit, `/api` GETs, MCP read tools | key with `read` | `KeyStore.authorize` (`cfactory/auth.py`) |
| CFactory | Create, move, dispatch a card; MCP write tools | key with `write` | Same. Unregistered MCP tools default to `write` |
| CFactory | Change `CFACTORY_API_KEYS` | `platform-admin` | Secret in gitops; no portal path |
| Cluster | kubectl, ArgoCD, Keycloak admin | `platform-admin` | Outside gitops |

A person holding a CFactory `write` key maps to `member`, a `read` key to `viewer`.

## Service principals (machine-to-machine edges)

| Principal | Credential today | Target |
|---|---|---|
| `svc:pfactory->aifactory` | `APP_API_TOKEN` / `PFACTORY_AIFACTORY_API_TOKEN` | `acw_` key, `mcp:write`, one org |
| `svc:aifactory->tfactory` | `APP_API_TOKEN` | `acw_` key, `mcp:write`, one org |
| `svc:aifactory-intake->pfactory` | `APP_API_TOKEN` | `acw_` key, `mcp:write`, one org |
| `svc:cfactory-cockpit->*` | `APP_API_TOKEN` (`CFACTORY_UPSTREAM_TOKEN`) | `acw_` key per sibling, `mcp:read` only |
| MCP clients to CFactory | `CFACTORY_MCP_SECRET` | `CFACTORY_API_KEYS` entry, `read` or `write` |

The scoped keys are merged in code (PFactory#991, TFactory#1496, AIFactory#2017, CFactory#510). Whether production callers still present the wildcards is checked at each review; until they are retired the wildcards are the standing exception AR-005 in the [risk register](risk-register.md).

## Cluster workloads

Cluster workloads are service principals, and nothing is grandfathered. Narrowly scoped: `aifactory-sandbox` (jobs, pods read), `cred-broker` (get and patch one Secret), the evidence collector, the deploy dry-run service account (create only). Not least-privilege: `odin-dashboard-role` (`factory-gitops/apps/odin/manifests/manifests.yaml`) grants cluster-wide `update` and `patch` on deployments, `deployments/rollback` and Argo applications; job-watchdog, argocd-drift, nfs-provisioner and keda hold ClusterRoleBindings. Each review assesses every RoleBinding and ClusterRoleBinding. No human RoleBinding belongs in gitops.

## Known gaps

- PF and TF task-route checks are in shadow mode. Enforcing them needs every project to carry an `org_id` (plan slice S6) and is the owner's decision, because a wrong flip locks people out.
- Org `admin` cannot revoke another member's key (slice S4).
- No service lists other members' keys: `list_api_keys` returns the caller's own keys (`ApiKey.user_id == current_user.id`) in AIFactory, PFactory and TFactory, so `keys.json` is collected from the database by the platform admin (slice S3 adds an admin inventory). `GET /api/admin/access-review` exists only in AIFactory; PF and TF membership is collected by hand.
