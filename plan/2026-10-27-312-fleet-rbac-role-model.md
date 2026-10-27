---
status: approved
issue: 312
spec: spec/2026-10-27-312-fleet-rbac-role-model.md
---

# Plan: fleet RBAC role model and quarterly access review

Epic olafkfreund/Factory#312, checkbox "Fleet RBAC role model + quarterly access reviews (evidence)". This plan orders the slices that follow the approved spec. Every slice is its own PR, with its own intent/spec/plan in the repo it touches, `Refs olafkfreund/Factory#312` (never `Closes`), into `dev` for the services and `main` for this hub. Facts below were checked on 2026-10-27 against `origin/dev` of AIFactory (AIF), PFactory (PF) and TFactory (TF), and `origin/main` of `factory-gitops`.

## Decisions carried over

From the approved spec (unchanged):

- **Principal kinds.** Human: Keycloak subject, rights from the org role in each service. Service principal: one credential per M2M edge (`svc:<from>-><to>`), a fixed scope set, no org role. Agent: `agent:<service>/<key_id>`, rights are the key's scopes and org capped by its `autonomy_ceiling`, never the invoking human's role.
- **Roles.** Keep `viewer < member < admin < owner` (`ROLE_LEVELS`, already in all three web servers). Inheritance is strictly upward. `platform-admin` (cluster, ArgoCD, Keycloak realm, `factory-secrets`) sits outside the org model and is not grantable from any portal. No new role names.
- **Action matrix** (minimum role; the spec's §3 table, corrected for what landed since; H1 publishes it with file:line links):

  | Factory | Action | Min role | Enforced by (2026-10-27) |
  |---|---|---|---|
  | AIF, PF, TF | Read org resources | `viewer` | `require_org_role` / `check_project_access` where routes use them |
  | AIF | Create, start, stop, recover a task; approve a plan | `member` | `require_project_access("member")`, `require_task_access("member")` (`routes/execution.py`, `routes/plan_approval.py`) |
  | AIF | Merge a PR the merge policy holds | `member`, never the agent that wrote it | Merge policy tier only, not per role |
  | AIF | Set a key's `autonomy_ceiling` | `admin` | `routes/api_keys.py` |
  | AIF | Export the access review; export the audit log | `admin` | `routes/access_review.py`, `routes/audit.py` (#1916) |
  | PF, TF | Export the audit log | `admin` | `routes/audit.py` (PF #942, TF #1452) |
  | PF | Ingest, process, approve a plan; start, stop, merge a task | `member` | **Not enforced** (#939, S2) |
  | TF | Create, rerun, start, stop, merge a test task; regression | `member` | **Not enforced** (#1450, S1) |
  | AIF, PF | Mint own `acw_` key (below `member`: `mcp:read` only; an `acw_` key cannot mint) | `member` | AIF #1911/#1914, PF #945 |
  | TF | Same | `member` | **Not enforced** (S1) |
  | AIF, PF, TF | Revoke any key in the org | `admin` | **Gap**: only the key's creator can revoke (S4) |
  | AIF, PF, TF | Manage members and roles | `admin` (`owner` for `admin` grants) | `routes/organizations.py` |
  | AIF | Remote MCP tool calls | key scope + caller's org role | AIF #1917 |
  | PF, TF | Remote MCP tool calls | same | **Not enforced**, surface off by default (PF #946, TF #1456, S5) |
  | CFactory | Cockpit, `/api` GETs, MCP read tools | key with `read` | `KeyStore.authorize` (`cfactory/auth.py`) |
  | CFactory | Create, move, dispatch a card; MCP write tools | key with `write` | Same; unregistered MCP tools default to `write` |
  | CFactory | Change `CFACTORY_API_KEYS` | `platform-admin` | Secret in gitops; no portal path |
  | Cluster | `kubectl`, ArgoCD, Keycloak admin | `platform-admin` | Outside gitops (decision 2) |
- **Agents never**: approve or merge their own PR, manage members or roles, mint keys, set or raise a ceiling, change `CFACTORY_API_KEYS`, sign a review.
- **JWT `role` claim.** No fleet role is emitted as a JWT `role` claim (see decision 3).
- **Quarterly review.** Due by the 15th of the first month of the next quarter (Q4 2026 due 2027-01-15), and within five working days of anyone leaving or changing role. Inputs and checks are inlined in H2 step 1. Output `review.md` plus raw exports at `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`. Revocations within five working days of signing. Exports carry key ids and `key_actor` hashes, never key values.

Owner answers to the spec's seven open questions (approved 2026-10-27):

1. **Separation of duties.** The owner is the sole reviewer and grantor. This is a recorded exception (SOC 2 CC6.3, SOX ITGC), listed in each review.
2. **`platform-admin`.** Held by the owner only. kubectl, ArgoCD and Keycloak admin accounts are listed by hand in each review until they are declarative.
3. **Source of human roles.** Roles stay in each service's database. A Keycloak role mapper comes only after the `is_service_principal` JWT-role fix. AIF has it (#1911: `is_service_principal` trusts only `is_service`). PF and TF have no `is_service_principal` and trust no JWT role today (grep for `get("role")` and `role == "admin"` under `apps/web-server/server` finds nothing), but they have no route-level role checks either. So the mapper also waits for the PF/TF slices below, and any helper ported to PF/TF must use the post-#1911 form.
4. **MFA.** Each review records every account's MFA state as an input. Recording only, nothing enforced.
5. **`APP_API_TOKEN` and `CFACTORY_MCP_SECRET`.** A standing accepted exception, listed in each review with the #555 retirement target date. No target date is recorded anywhere yet (AIFactory#555 is closed without a milestone, R-002 has none): the owner sets it in slice H2, and the review shows "date not set" as a finding until then.
6. **Null autonomy ceiling.** The review flags every `acw_` key whose `autonomy_ceiling` is null.
7. **CFactory.** A `write` key held by a person maps to `member`, a `read` key to `viewer`.

## What landed since the spec

| Change | Repo PR | Effect on the matrix |
|---|---|---|
| Mint-time scope cap: below `member` only `mcp:read`; `is_service_principal` trusts only `is_service` | AIF #1911 | Closes the AIF half of the "viewer mints `mcp:write`" gap and the JWT `role == "admin"` bypass (the JWT-role guardrail is now satisfied in AIF) |
| `acw_` auth enforces expiry, owner status and the owner's current org role | AIF #1914 | Demotion or removal takes effect on the next call |
| Access review streams only the gated org; `/api/audit/export` needs org `admin` | AIF #1916 | Review input row 1 is now safe to use |
| Remote MCP authorizes as the calling key, not the service token | AIF #1917 (#1910) | AIF remote MCP is safe to enable |
| `/api/audit/export` gated on org `admin` or service principal; principals marked `is_service` | PF #942, TF #1452 | PF/TF now carry `is_service`, `api_key_id`, `org_id` on the principal |
| Mint-time and auth-time scope cap (`cap_by_owner_role`) | PF #945 (#940) | PF key gap closed. **TF has neither** (`TFactory routes/api_keys.py` checks membership only, line ~154; no `cap_by_owner_role`) |

Still open:

- **PF #939, TF #1450**: no role or org check on task/plan routes, so a `viewer`'s JWT can start, stop, approve or merge any task in any org. These are the first slices.
- **PF/TF remote MCP** proxies tool calls with `settings.API_TOKEN` (`mcp_remote/tools.py:96` PF, `:100` TF), the AIF #1910 defect. Off by default and not enabled in `factory-gitops` (no `*_MCP_REMOTE_ENABLED` on main). Tracked as PFactory #946 and TFactory #1456.
- **Admin revoke** (all three): `revoke_api_key` matches `ApiKey.user_id == current_user.id`, so an admin cannot revoke another member's key.
- **Key inventory per org and access-review routes in PF/TF** (spec slice 3).

## Steps

Ordered. S1 and S2 are the first implementation slices; H1–H3 (hub docs) may run in parallel with them.

### S1. TFactory: key caps and task-route role checks (TF #1450), one PR into `dev`

#1450 says the caps must land in the same slice as the route checks.

1. `apps/web-server/server/routes/api_keys.py` `create_api_key`: port PF #945's mint cap. An `acw_` principal (`principal.get("api_key_id")`) cannot mint (403); below `member` only `mcp:read` (403 otherwise), using TF's own `ROLE_LEVELS`/`_role_level` from `routes/organizations.py`. → `pytest tests/test_api_key_mint_scope_cap.py` (new, copy PF's).
2. `apps/web-server/server/mcp_remote/auth.py`: add `cap_by_owner_role` as in PF #945 (scopes capped by the owner's current `OrgMember` role in `key.org_id`; no membership, no scopes). Call it once, inside `_lookup_by_digest` (`mcp_remote/auth.py:121`). That one call covers both surfaces. TF has no `_try_authenticate_api_key` (that is PF only). TF's REST `acw_` path is the middleware at `auth.py:262-281`, which calls `mcp_remote.auth.authenticate()` → `_lookup_by_digest` (`mcp_remote/auth.py:115`). The capped scopes therefore reach the `api:full` (`REST_API_SCOPE`) check at `auth.py:276` already capped. Do not add a second call site. → `pytest tests/test_api_key_rest_role_cap.py tests/test_mcp_key_lookup.py` (both new in TF, copy PF's and adapt them to TF's middleware path).
   Trap: the caps take effect on merge, with no flag. Right before S1 merges, recount `api_keys` rows in the prod tfactory database, read-only and aggregates only. AIF #1914 found 0 rows on 2026-10-27. If any rows exist, list each key's owner role and scopes in the PR, so nobody loses access by surprise.
3. New `apps/web-server/server/routes/project_authz.py`: port AIF's `check_project_access`, `authorize_project_for_user`, `require_task_access(minimum_role)` (task id `"{project_id}:{spec_slug}"`, project id = text before the first `:`). `is_service_principal(user)` returns `bool(user.get("is_service"))` only, the post-#1911 form. Look projects up through TF's existing `projects.json` loader (`routes/projects.py:213`), not a new registry.
4. Wire `Depends(require_task_access("member"))` on `routes/execution.py:119` start, `:556` stop, `routes/tasks_plan.py:29` approve-plan, `routes/tasks_worktree.py:1771` merge, and every other `POST/PUT/PATCH/DELETE` route with a `task_id` path param (enumerate with `git grep -n '@router\.\(post\|put\|patch\|delete\)("/{task_id}' -- apps/web-server/server/routes`; list them in the PR).
5. Flag `RBAC_ENFORCE_TASK_ROUTES` in `server/config.py`, default `False`. Off (shadow mode): compute the decision, then let the original handler run. Every `HTTPException` the decision raises must be caught and logged as a would-deny. That means the 403s, and also the 404 for a missing project and the 403 for a project with no `org_id`. Audit each would-deny in the shape of AIF's `_audit_authz_denial`. Any other error during the lookup (DB, `projects.json` read) fails open with a warning log. Shadow mode must never change a response. On: deny as AIF does. → `pytest tests/test_task_route_rbac.py` (new) covers:
   - a viewer gets 403 on start with the flag on, and 200 with it off;
   - a member passes;
   - `is_service` passes;
   - a key bound to another org gets 403;
   - a JWT carrying `role: admin` gets no bypass;
   - **flag off, unknown project id**: the response is exactly what it is without the dependency (the handler's own 404 or result, never the authz 404);
   - flag off, the project lookup raises: the request still succeeds.

Traps:
- **Lockout.** TF projects live in `projects.json` (`PROJECTS_BACKEND="json"`, `config.py:66-69`) and carry no `org_id`. AIF's rule returns 403 for a project without an org, so enforcing now would lock every human out of every task. That is why the flag defaults off. Turning it on needs slice S6 first.
- Wave rules: must not lock out any human or service login, enforce MFA, touch `APP_API_TOKEN` or gitops, or deploy.
- PF #945 stored `expires_at`/`last_used_at` as naive UTC for Postgres; copy that, and run `tests/postgres/` if TF has the suite.
- Worktree: never `git add -A` (the `.venv` symlink is not ignored).

### S2. PFactory: task/plan-route role checks (PF #939), one PR into `dev`

Caps already landed (#945). Same as S1 steps 3–5, with PF's routes: `routes/execution.py:108` start, `:550` stop, `routes/tasks.py:1622` approve-plan, `:3754` worktree merge, plus every other task-keyed write route and the plan-pipeline write routes in `routes/plan_pipeline.py` that take a task or project id (14 write routes; list each with its minimum role in the PR). Test file `tests/test_task_route_rbac.py`, same cases.

Traps: same lockout trap (PF has no `org_id` on `projects.json` entries either; `routes/projects.py` never writes one). Reuse PF's `_role_level` and its `is_service` marker from #942. The flag name is the same in both services so gitops can flip them together.

### H1. Hub: role catalog, PR into `main`

`docs/compliance/rbac-role-catalog.md` (new): the principal kinds, roles, agent rules and JWT guardrail from "Decisions carried over" above. It also has:
- **Service-principal edge table.** One credential per M2M edge, taken from `AIFactory/docs/compliance/scoped-service-tokens.md` (AIF #1244). Each edge gets only the scopes it uses and holds no org role.

  | Principal | Credential today | Target |
  |---|---|---|
  | `svc:pfactory->aifactory` | `APP_API_TOKEN` / `PFACTORY_AIFACTORY_API_TOKEN` | `acw_` key, `mcp:write`, one org |
  | `svc:aifactory->tfactory` | `APP_API_TOKEN` | `acw_` key, `mcp:write`, one org |
  | `svc:aifactory-intake->pfactory` | `APP_API_TOKEN` | `acw_` key, `mcp:write`, one org |
  | `svc:cfactory-cockpit->*` | `APP_API_TOKEN` (`CFACTORY_UPSTREAM_TOKEN`) | `acw_` key per sibling, `mcp:read` only |
  | MCP clients -> CFactory | `CFACTORY_MCP_SECRET` | `CFACTORY_API_KEYS` entry, `read` or `write` per client |
- **Cluster workloads are service principals, and nothing is grandfathered.** Narrowly scoped today: `aifactory-sandbox` (jobs, pods read), `cred-broker` (get/patch one Secret), the evidence collector, and the deploy dry-run SA (create only). Not least-privilege: `odin-dashboard-role` (`factory-gitops/apps/odin/manifests/manifests.yaml:213-220`) grants cluster-wide `update, patch` on deployments, `deployments/rollback` and Argo applications. job-watchdog, argocd-drift, nfs-provisioner and keda hold ClusterRoleBindings. The first review assesses every existing RoleBinding and ClusterRoleBinding, and later reviews also flag any new one. No human RoleBinding is in gitops.
- **The action matrix** with each "Enforced by" cell linking a file and line on the service's `origin/dev` at the time of writing, and "not enforced (flag off)" for the S1/S2 routes until the flag is on. Link it from `docs/compliance/README.md` and `docs/compliance/roles.md` (`platform-admin` holder = owner, decision 2). → every link resolves: `gh api` or `git -C <repo> show origin/dev:<path>` per link, listed in the PR.

Traps: the policy's gap 5 text ("Org RBAC exists in AIFactory only") is wrong since PF/TF have `ROLE_LEVELS`; fix it in H3, not here.

### H2. Hub: access-review runbook and exceptions, PR into `main` (may share H1's PR)

1. `docs/compliance/access-review-runbook.md` (new). Cadence: quarterly, due by the 15th of the first month of the next quarter, and within five working days of anyone leaving or changing role. Reviewer and signer: the owner (AR-003). Inputs, collected read-only:

   | Input | Source | State on 2026-10-27 |
   |---|---|---|
   | Org members: role, `last_login_at`, active | `GET /api/admin/access-review?org_id=` | AIF only (fixed by #1916). PF/TF in S3. |
   | `acw_` keys: id, owner, scopes, ceiling, `last_used_at`, `expires_at` | `routes/api_keys.py` per service | Per user only. A per-org admin listing is S3. |
   | CFactory keys: `key_actor` hash and scope, mapped `write`→`member`, `read`→`viewer` (decision 7) | Derived from `CFACTORY_API_KEYS` by the platform admin | Manual. Never the key values. |
   | Legacy wildcard use | AIF `_warn_legacy_api_token_once` logs; CFactory #504 legacy MCP counter | Exists |
   | Keycloak users, `tenant` groups, enabled flag, linked IdP, MFA state (decision 4, record only) | `kcadm.sh get users`, `groups`, `users/<id>/credentials` | Manual |
   | `platform-admin` accounts: kubectl, ArgoCD, Keycloak admin (decision 2) | Listed by hand | Manual |
   | Cluster bindings | `RoleBinding` / `ClusterRoleBinding` in `factory-gitops` and the live cluster | gitops readable; live listing manual |

   Each review checks:
   - No key's scopes are wider than its owner's current role. A `viewer` holding `mcp:write` is a finding.
   - Every human maps to exactly one role per org and one tenant group.
   - No account inactive for more than 90 days keeps a role above `viewer`.
   - No key has gone unused for more than 90 days, or lacks an expiry, without a recorded reason.
   - Every key with a null `autonomy_ceiling` is a finding (decision 6).
   - Every RoleBinding and ClusterRoleBinding has a recorded justification, and none binds a human. Nothing is grandfathered: the first review assesses all of them, `odin-dashboard-role` included.
   - The legacy wildcard counters are recorded.
   - Accepted exceptions are listed: AR-003 (SoD), AR-004 (`APP_API_TOKEN` and `CFACTORY_MCP_SECRET`), and MFA not enforced.

   Output: `review.md` plus the raw exports, at `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`. Revocations are done within five working days of signing; anything slower is recorded as an exception with an owner and a date. A `review.md` template with sections Findings, Actions, Accepted exceptions, Signature. Commands that produce each export, with a "never a key value" grep at the end (`grep -rE 'acw_[A-Za-z0-9]{8,}'` must find nothing).
2. `docs/compliance/risk-register.md`: add AR-003 (SoD: the owner is sole reviewer and grantor, decision 1) and AR-004 (`APP_API_TOKEN` and `CFACTORY_MCP_SECRET` standing exception, decision 5, linked to R-002). Each gets accepted date 2026-10-27, a review date, and compensating controls: the #1911/#1914 caps, the #504 legacy MCP counter, and `_warn_legacy_api_token_once`. AR-004's retirement date is the owner's input. Until the owner gives it, write "not set", and the runbook lists that as a finding.
   Trap: AR-001 (`risk-register.md:46`) and AR-002 (`:73`, R-015 pen test) are taken. On 2026-10-27 no open hub PR claimed AR-003 or AR-004. Re-check `main` and the open PRs before committing, and take the next free ids if these have gone.

→ `grep -n 'AR-003\|AR-004' docs/compliance/risk-register.md docs/compliance/access-review-runbook.md` finds both entries, and `grep -cE '^(\| |### )AR-002\b' docs/compliance/risk-register.md` prints 1 (no duplicate id). Follow the register's form: a row in the acceptance log table (like AR-001 at `:56`) and a `### AR-00n` section for the compensating controls (like AR-002 at `:73`).

### H3. Hub: policy and control matrix, same PR as H1/H2

`docs/compliance/policies/iam-access-control.md`: gap 4 (CFactory fails closed on `/api` since CFactory #500), gap 5 (PF/TF have `ROLE_LEVELS`; catalog published; route checks behind a flag), gap 6 (runbook exists; open until the first signed review). `docs/compliance/control-matrix.md:49`: add `rbac-role-catalog.md` and the runbook to the IAM row. → `grep -n 'rbac-role-catalog' docs/compliance/policies/iam-access-control.md docs/compliance/control-matrix.md`.

### Later slices (each its own issue, intent/spec/plan, in order)

- **S3. Evidence tooling (read-only, additive).** AIF, PF, TF: admin-only per-org key inventory (id, owner, scopes, ceiling, `last_used_at`, `expires_at`, no secret). PF, TF: `GET /api/admin/access-review` ported from AIF **after** #1916 (streams `membership.org_id`, takes only `?org_id`).
- **S4. Admin revoke.** AIF, PF, TF `revoke_api_key`: an org `admin` may revoke any key in the org; the key's creator keeps self-revoke.
- **S5. PF/TF remote MCP authz.** Port AIF #1917 before anyone sets `PFACTORY_MCP_REMOTE_ENABLED` or `TFACTORY_MCP_REMOTE_ENABLED`. Issues: PFactory #946, TFactory #1456. Needs the `project_authz` helper from S1/S2, so it lands after them.
- **S6. Project ownership backfill and flag flip.** Give every PF/TF project an `org_id` (the WS3 `PROJECTS_BACKEND="db"` cutover or a one-off backfill), check no human loses a task they use, then set `RBAC_ENFORCE_TASK_ROUTES=true` in `factory-gitops`. Needs owner approval (gitops and a login-affecting change).
- **S7. First review**, Q4 2026, due 2027-01-15, signed and stored at `factory-evidence/control-plane-push/access-review/2026-Q4/`. This is the epic's acceptance criterion for the RBAC checkbox.
- **S8. Enforcement follow-ups.** Null ceiling counts as `hard` (#1960 gate). Keycloak role mapper (decision 3), only after S1, S2 and S6 are live. CFactory human roles from the IdP.

## Tests

- S1/S2: the new `tests/test_task_route_rbac.py` per service passes, fails if the dependency is removed from any wired route, and the service's full suite stays green with the flag off (current behaviour). TF also runs the two copied cap tests.
- H1–H3: hub CI green; every "Enforced by" link resolves; the never-a-key grep on the runbook's sample output is empty.
- S7: the evidence collector's `run-manifest.json` reports the access-review drop point present and recent.

## Rollback

- Hub slices: revert the PR. Docs only.
- S1/S2: the flag is off by default, so merging changes nothing for callers except TF's key caps (no keys exist in prod: AIF #1914 found 0 rows in `api_keys` in all three databases). Revert the PR to undo; with the flag on (S6), set it back to `false` in gitops first.
