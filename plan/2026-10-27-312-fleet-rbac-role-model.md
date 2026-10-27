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
- **Action matrix.** As in spec §3, corrected by the "what landed" table below.
- **Agents never**: approve or merge their own PR, manage members or roles, mint keys, set or raise a ceiling, change `CFACTORY_API_KEYS`, sign a review.
- **JWT `role` claim.** No fleet role is emitted as a JWT `role` claim (see decision 3).
- **Quarterly review.** Due by the 15th of the first month of the next quarter (Q4 2026 due 2027-01-15), and within five working days of anyone leaving or changing role. Inputs per plane and checks as in spec §7. Output `review.md` plus raw exports at `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`. Revocations within five working days of signing. Exports carry key ids and `key_actor` hashes, never key values.

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
| Mint-time scope cap: below `member` only `mcp:read`; `is_service_principal` trusts only `is_service` | AIF #1911 | Closes the AIF half of the "viewer mints `mcp:write`" gap and the JWT `role == "admin"` bypass (spec §6 guardrail now satisfied in AIF) |
| `acw_` auth enforces expiry, owner status and the owner's current org role | AIF #1914 | Demotion or removal takes effect on the next call |
| Access review streams only the gated org; `/api/audit/export` needs org `admin` | AIF #1916 | Review input row 1 is now safe to use |
| Remote MCP authorizes as the calling key, not the service token | AIF #1917 (#1910) | AIF remote MCP is safe to enable |
| `/api/audit/export` gated on org `admin` or service principal; principals marked `is_service` | PF #942, TF #1452 | PF/TF now carry `is_service`, `api_key_id`, `org_id` on the principal |
| Mint-time and auth-time scope cap (`cap_by_owner_role`) | PF #945 (#940) | PF key gap closed. **TF has neither** (`TFactory routes/api_keys.py` checks membership only, line ~154; no `cap_by_owner_role`) |

Still open:

- **PF #939, TF #1450**: no role or org check on task/plan routes, so a `viewer`'s JWT can start, stop, approve or merge any task in any org. These are the first slices.
- **PF/TF remote MCP** proxies tool calls with `settings.API_TOKEN` (`mcp_remote/tools.py:96` PF, `:100` TF), the AIF #1910 defect. Off by default and not enabled in `factory-gitops` (no `*_MCP_REMOTE_ENABLED` on main). No issue exists yet.
- **Admin revoke** (all three): `revoke_api_key` matches `ApiKey.user_id == current_user.id`, so an admin cannot revoke another member's key.
- **Key inventory per org and access-review routes in PF/TF** (spec slice 3).

## Steps

Ordered. S1 and S2 are the first implementation slices; H1–H3 (hub docs) may run in parallel with them.

### S1. TFactory: key caps and task-route role checks (TF #1450), one PR into `dev`

#1450 says the caps must land in the same slice as the route checks.

1. `apps/web-server/server/routes/api_keys.py` `create_api_key`: port PF #945's mint cap. An `acw_` principal (`principal.get("api_key_id")`) cannot mint (403); below `member` only `mcp:read` (403 otherwise), using TF's own `ROLE_LEVELS`/`_role_level` from `routes/organizations.py`. → `pytest tests/test_api_key_mint_scope_cap.py` (new, copy PF's).
2. `apps/web-server/server/mcp_remote/auth.py`: add `cap_by_owner_role` as in PF #945 (scopes capped by the owner's current `OrgMember` role in `key.org_id`; no membership, no scopes). Call it in `_lookup_by_digest` and in `auth.py::_try_authenticate_api_key` before the `api` scope check. → `pytest tests/test_api_key_rest_role_cap.py tests/test_mcp_key_lookup.py`.
3. New `apps/web-server/server/routes/project_authz.py`: port AIF's `check_project_access`, `authorize_project_for_user`, `require_task_access(minimum_role)` (task id `"{project_id}:{spec_slug}"`, project id = text before the first `:`). `is_service_principal(user)` returns `bool(user.get("is_service"))` only, the post-#1911 form. Look projects up through TF's existing `projects.json` loader (`routes/projects.py:213`), not a new registry.
4. Wire `Depends(require_task_access("member"))` on `routes/execution.py:119` start, `:556` stop, `routes/tasks_plan.py:29` approve-plan, `routes/tasks_worktree.py:1771` merge, and every other `POST/PUT/PATCH/DELETE` route with a `task_id` path param (enumerate with `git grep -n '@router\.\(post\|put\|patch\|delete\)("/{task_id}' -- apps/web-server/server/routes`; list them in the PR).
5. Flag `RBAC_ENFORCE_TASK_ROUTES` in `server/config.py`, default `False`. Off: compute the decision, log and audit a would-deny (reuse AIF's `_audit_authz_denial` shape), then allow. On: deny. → `pytest tests/test_task_route_rbac.py` (new): viewer gets 403 on start with the flag on and 200 with it off; member passes; `is_service` passes; key bound to another org gets 403; a JWT carrying `role: admin` gets no bypass.

Traps:
- **Lockout.** TF projects live in `projects.json` (`PROJECTS_BACKEND="json"`, `config.py:66-69`) and carry no `org_id`. AIF's rule returns 403 for a project without an org, so enforcing now would lock every human out of every task. That is why the flag defaults off. Turning it on needs slice S6 first.
- Wave rules: must not lock out any human or service login, enforce MFA, touch `APP_API_TOKEN` or gitops, or deploy.
- PF #945 stored `expires_at`/`last_used_at` as naive UTC for Postgres; copy that, and run `tests/postgres/` if TF has the suite.
- Worktree: never `git add -A` (the `.venv` symlink is not ignored).

### S2. PFactory: task/plan-route role checks (PF #939), one PR into `dev`

Caps already landed (#945). Same as S1 steps 3–5, with PF's routes: `routes/execution.py:108` start, `:550` stop, `routes/tasks.py:1622` approve-plan, `:3754` worktree merge, plus every other task-keyed write route and the plan-pipeline write routes in `routes/plan_pipeline.py` that take a task or project id (14 write routes; list each with its minimum role in the PR). Test file `tests/test_task_route_rbac.py`, same cases.

Traps: same lockout trap (PF has no `org_id` on `projects.json` entries either; `routes/projects.py` never writes one). Reuse PF's `_role_level` and its `is_service` marker from #942. The flag name is the same in both services so gitops can flip them together.

### H1. Hub: role catalog, PR into `main`

`docs/compliance/rbac-role-catalog.md` (new): spec §1–§6 as the published model, the action matrix with each "Enforced by" cell linking a file and line on the service's `origin/dev` at the time of writing, and "not enforced (flag off)" for the S1/S2 routes until the flag is on. Link it from `docs/compliance/README.md` and `docs/compliance/roles.md` (`platform-admin` holder = owner, decision 2). → every link resolves: `gh api` or `git -C <repo> show origin/dev:<path>` per link, listed in the PR.

Traps: the policy's gap 5 text ("Org RBAC exists in AIFactory only") is wrong since PF/TF have `ROLE_LEVELS`; fix it in H3, not here.

### H2. Hub: access-review runbook and exceptions, PR into `main` (may share H1's PR)

1. `docs/compliance/access-review-runbook.md` (new): cadence, reviewer = owner, the input table from spec §7 plus three rows from the decisions: hand-listed `platform-admin` accounts (2), MFA state per Keycloak account from `kcadm.sh get users/<id>/credentials` (4, record only), CFactory keys mapped `write`→`member`, `read`→`viewer` (7). Checks from spec §7 plus: every key with a null `autonomy_ceiling` is a finding (6). A `review.md` template with sections Findings, Actions, Accepted exceptions, Signature. Commands that produce each export, with a "never a key value" grep at the end (`grep -rE 'acw_[A-Za-z0-9]{8,}'` must find nothing).
2. `docs/compliance/risk-register.md`: add AR-002 (SoD: sole reviewer and grantor, decision 1) and AR-003 (`APP_API_TOKEN` and `CFACTORY_MCP_SECRET` standing exception, decision 5, linked to R-002), each with accepted date 2026-10-27, a review date, and compensating controls (#1911/#1914 caps, #504 legacy MCP counter, `_warn_legacy_api_token_once`). AR-003's retirement date is the owner's input; until given, write "not set" and the runbook lists it as a finding.

→ `grep -n 'AR-002\|AR-003' docs/compliance/risk-register.md docs/compliance/access-review-runbook.md`.

### H3. Hub: policy and control matrix, same PR as H1/H2

`docs/compliance/policies/iam-access-control.md`: gap 4 (CFactory fails closed on `/api` since CFactory #500), gap 5 (PF/TF have `ROLE_LEVELS`; catalog published; route checks behind a flag), gap 6 (runbook exists; open until the first signed review). `docs/compliance/control-matrix.md:49`: add `rbac-role-catalog.md` and the runbook to the IAM row. → `grep -n 'rbac-role-catalog' docs/compliance/policies/iam-access-control.md docs/compliance/control-matrix.md`.

### Later slices (each its own issue, intent/spec/plan, in order)

- **S3. Evidence tooling (read-only, additive).** AIF, PF, TF: admin-only per-org key inventory (id, owner, scopes, ceiling, `last_used_at`, `expires_at`, no secret). PF, TF: `GET /api/admin/access-review` ported from AIF **after** #1916 (streams `membership.org_id`, takes only `?org_id`).
- **S4. Admin revoke.** AIF, PF, TF `revoke_api_key`: an org `admin` may revoke any key in the org; the key's creator keeps self-revoke.
- **S5. PF/TF remote MCP authz.** Port AIF #1917 before anyone sets `PFACTORY_MCP_REMOTE_ENABLED` or `TFACTORY_MCP_REMOTE_ENABLED`. Open the issues first (none exist).
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
