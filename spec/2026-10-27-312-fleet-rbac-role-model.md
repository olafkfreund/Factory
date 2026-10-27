---
status: approved
issue: 312
intent: intent/2026-10-27-312-fleet-rbac-role-model.md
---

# Spec: fleet RBAC role model and quarterly access review

Scope: the role model and the review procedure for olafkfreund/Factory#312. MFA, `DISABLE_AUTH` and retiring `APP_API_TOKEN` / `CFACTORY_MCP_SECRET` are out of scope. They appear only as inputs to the review and as open questions. Nothing here changes code, gitops or a credential.

## Design

### 1. Principal kinds

Every caller of a factory is one of three kinds, and each kind gets its rights from a different place.

| Kind | Identity | Rights come from | Never |
|---|---|---|---|
| Human | Keycloak subject (GitHub-brokered) | Org role in each service (`ROLE_LEVELS`), plus `platform-admin` for the cluster (open question 2) | Rights from a shared token |
| Service principal | One credential per M2M edge (`svc:<from>-><to>`) | A fixed scope set for that edge (§4) | An org role, or the `is_service` bypass once #555 lands |
| Agent | `agent:<service>/<key_id>` (#1960) | The `acw_` key's scopes and its `autonomy_ceiling` (§5) | The role of the human who invoked it |

### 2. Human roles

Keep the four role names the code already uses. A new vocabulary would need a mapping layer and gives nothing extra.

| Role | Level | Meaning |
|---|---|---|
| `viewer` | 0 | Reads everything in the org: portals, task, plan and test status, logs, reports. Changes nothing. |
| `member` | 1 | Does the work: creates and runs tasks, plans, tests and cards, approves plans and merges at the tier the merge policy allows, and mints own `acw_` keys **without** a ceiling, with scopes no wider than the role (`viewer`: `mcp:read` only). |
| `admin` | 2 | Runs the org: adds and removes members below `owner`, changes roles below `admin`, sets autonomy ceilings on keys, revokes any key in the org, exports the access review and the audit log. |
| `owner` | 3 | Everything `admin` may do, plus granting and removing `admin`, transferring ownership, deleting the org, and signing the access review. |
| `platform-admin` | outside the org model | Cluster, ArgoCD, Keycloak realm and `factory-secrets` administration. Not a factory role, and not grantable from any portal. Held by the owner only (open question 2). |

Role inheritance is strictly upward: each role has every right of the roles below it. `require_org_role(minimum)` already enforces this ordering.

### 3. Per-factory action matrix

The minimum role for each action. **Enforced by** names the check that exists today. "Not enforced" means the action is gated only by authentication. Slice 2 audits route coverage and corrects any row that is wrong.

| Factory | Action | Min role | Enforced by |
|---|---|---|---|
| All three web servers | Read org resources | `viewer` | `require_org_role` / `check_project_access` where routes use them |
| AIFactory | Create, start, stop or recover a task; approve a plan | `member` | `require_project_access("member")` (e.g. `routes/execution.py:1188,1357`, `routes/projects.py:702`) |
| AIFactory | Merge a PR the merge policy holds (`HOLD_ASYNC` / `HOLD_BLOCKING`) | `member`, never the agent that wrote it | Not enforced per role. The merge policy decides the tier. |
| AIFactory | Set an `autonomy_ceiling` on a key | `admin` | `routes/api_keys.py:179` |
| AIFactory | Export the access review | `admin` | `routes/access_review.py` (`require_org_role("admin")`) |
| PFactory | Ingest, process or approve a plan; export an audit pack | `member` | Org routes only. Plan routes: not enforced per role (to audit). |
| TFactory | Create or rerun a test task; run regression | `member` | Not enforced per role (to audit) |
| AIF / PF / TF | Mint own `acw_` key | `member` | **Gap.** `routes/api_keys.py` checks only org membership, so a `viewer` can mint a key, and the requested `scopes` are stored without being checked against the role (a `viewer` can hold `mcp:write`). An `acw_` key cannot mint keys. |
| AIF / PF / TF | Revoke a key in the org | `admin` | **Gap.** `revoke_api_key` lets only the key's creator delete it; an admin cannot revoke another member's key. |
| AIF / PF / TF | Manage members and roles | `admin` (`owner` for `admin` grants) | `routes/organizations.py` |
| CFactory | Read the cockpit, `/api` GETs, MCP read tools | key with `read` | `KeyStore.authorize` (`cfactory/auth.py`) |
| CFactory | Create, move or dispatch a card; MCP write tools | key with `write` | Same. Unregistered MCP tools default to `write`. |
| CFactory | Change `CFACTORY_API_KEYS` | `platform-admin` | Secret in gitops; no portal path |
| Cluster | Anything with `kubectl` / ArgoCD | `platform-admin` | Outside gitops today (open question 2) |

CFactory has no human roles. Until open question 7 is answered, the review treats a `write` key held by a person as `member` and a `read` key as `viewer`.

### 4. Service principals

One credential per M2M edge, taken from the edge table in `AIFactory/docs/compliance/scoped-service-tokens.md` (AIFactory #1244). Each edge gets only the scopes it uses. A service principal holds no org role. When #555 lands, `is_service_principal()` stops treating it as a bypass. Until then, the review records the shared token as an exception (open question 5).

| Principal | Credential today | Target scope |
|---|---|---|
| `svc:pfactory->aifactory` | `APP_API_TOKEN` / `PFACTORY_AIFACTORY_API_TOKEN` | `acw_` key, `mcp:write`, one org |
| `svc:aifactory->tfactory` | `APP_API_TOKEN` | `acw_` key, `mcp:write`, one org |
| `svc:aifactory-intake->pfactory` | `APP_API_TOKEN` | `acw_` key, `mcp:write`, one org |
| `svc:cfactory-cockpit->*` | `APP_API_TOKEN` (`CFACTORY_UPSTREAM_TOKEN`) | `acw_` key per sibling, `mcp:read` only |
| MCP clients -> CFactory | `CFACTORY_MCP_SECRET` | `CFACTORY_API_KEYS` entry, `read` or `write` per client |

Cluster workloads are service principals too. Their Kubernetes RBAC is already least-privilege and stays as it is: `aifactory-sandbox`, `cred-broker`, the evidence collector, and the deploy dry-run SA (create only). The review lists every RoleBinding and ClusterRoleBinding and flags any new one.

### 5. Agents

An agent is a principal of its own, never a stand-in for a person.

- **Identity:** `agent:aifactory/<key_id>`, derived from the key (#1887). Other services use the same form once they issue agent keys.
- **Rights:** the intersection of the key's scopes (`mcp:read` / `mcp:write`) and the key's org. The rights of the human who created the key or started the run are not added. A key minted by an `owner` gives an agent no admin rights.
- **Tier:** the effective autonomy tier is the stricter of the key's `autonomy_ceiling` and the merge decision (`merge_policy.cap_disposition`). An agent never acts above its ceiling. A key with no ceiling is unrestricted today. #1960 requires it to count as `hard` or be refused before the ceiling gates merges, and the review flags such keys until then (open question 6).
- **Always forbidden for an agent, at every tier:** approving or merging its own PR, managing members or roles, minting keys (already enforced), setting or raising a ceiling, changing `CFACTORY_API_KEYS`, and signing an access review.
- **Attribution:** actions record the agent identity and, where intake captures it, the originating human as a separate field (#1960 slice 2). The human is recorded, not inherited.

### 6. Guardrail on the JWT `role` claim

`is_service_principal()` returns true for `role == "admin"`. No fleet role may be emitted as a JWT `role` claim with the value `admin` until that branch is removed. Human roles stay in each service's org membership. This is a hard constraint on slice 5, not a change now.

### 7. Quarterly access review

- **Cadence:** once per calendar quarter, due by the 15th of the first month of the next quarter (Q4 2026 is due 2027-01-15). Also within five working days of anyone leaving or changing role.
- **Reviewer and signer:** the org `owner` (open question 1 on SoD).
- **Inputs, collected read-only, one per plane:**

| Input | Source | Today |
|---|---|---|
| Org members, role, `last_login_at`, active | `GET /api/admin/access-review?org=` | AIFactory only. PF/TF need the route (slice 3). |
| `acw_` keys: id, owner, scopes, ceiling, `last_used_at`, `expires_at` | `GET` on `routes/api_keys.py` per service | Exists per user. A per-org admin listing is slice 3. |
| CFactory keys: `key_actor` hash and scopes | Derived from `CFACTORY_API_KEYS` by the platform admin | Manual. Never the key values. |
| Legacy wildcard use | AIFactory `_warn_legacy_api_token_once` logs; CFactory #504 legacy MCP counter | Exists |
| Keycloak users, groups (`tenant`), enabled flag, linked IdP | `kcadm.sh get users` / `groups` | Manual until the realm is declarative |
| Cluster bindings | `RoleBinding` / `ClusterRoleBinding` in `factory-gitops`, and the live cluster | gitops readable; live listing manual |

- **Checks per review:** every key's scopes are no wider than its owner's current role (a `viewer` holding `mcp:write` is a finding). Every human maps to exactly one role per org and one tenant group. No account inactive for more than 90 days keeps a role above `viewer`. No key is unused for more than 90 days or lacks an expiry without a recorded reason. No agent key has a null ceiling (until #1960's gate lands). No new ClusterRoleBinding to a human. The legacy wildcard counters are recorded.
- **Output:** `review.md` with the date, the reviewer, every finding, and the action taken for each (keep / revoke / downgrade, with a reason), plus the raw exports. Stored at `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/`, the drop point the evidence collector already watches for freshness. Exports contain no credential values.
- **Remediation:** revocations within five working days of signing. Anything slower is recorded as an exception with an owner and a date.
- **Accepted exceptions are listed in every review** until they close: the shared `APP_API_TOKEN`, `CFACTORY_MCP_SECRET` in `allow` mode, and MFA not enforced (open questions 4 and 5).

## Alternatives rejected

- **New role names (viewer / operator / maintainer / owner, as sketched in `iam-access-control.md` Phase 3).** That would put a mapping layer on top of `ROLE_LEVELS` in three services and change nothing about who may do what. Slice 2 updates the policy to the existing names.
- **Roles from Keycloak now (a role mapper emitting `role`).** It would centralise roles, but `role == "admin"` is an authz bypass today. It is unsafe until slice 5 removes that branch.
- **Agents inherit the invoking human's role.** That is the simplest to wire, but an owner's run would give the agent admin rights. It contradicts #1960 and turns a prompt injection into an org takeover.
- **One fleet-wide service role for all M2M callers.** That is the shared wildcard again, with a new name.
- **Monthly reviews.** The frameworks accept quarterly reviews, and with one owner a monthly review would turn into a rubber stamp.
- **Building the fleet export tool first.** The procedure has to exist before tooling can show it is followed. A manual first review is enough for the acceptance criterion, and tooling follows in slice 3.

## Risks

- **The action matrix may claim enforcement that does not exist.** Rows marked "to audit" are not verified. Slice 2 must check each route before the catalog is published as a control.
- **A self-review fails SoD** if the owner is the only reviewer (open question 1).
- **Manual inputs drift.** CFactory keys, Keycloak and live cluster bindings are gathered by hand until they are declarative. A missed account is a review that looks clean but is not.
- **Evidence leakage.** A careless export could contain a key. Only `key_actor` hashes and key ids are allowed, and the runbook says so.
- **Two enforcement gaps found while writing this spec** (any member, including `viewer`, can mint a key with any scope; an admin cannot revoke another member's key) stay open until slice 5. The review catches them after the fact, not before.
- None of this changes runtime behaviour, so it cannot break a host or a login.

## Verification

This wave: `intent/` and `spec/` are committed with draft and approval commits, and the hub CI is green on the PR.

When the epic's RBAC checkbox is done (later slices):

- The role catalog is committed under `docs/compliance/`, and each "Enforced by" cell links a file and line that exists on the service's `origin/dev`.
- A test per service shows that a `viewer` gets 403 on one write route and an `acw_` key gets 403 on key minting (that one already exists).
- One completed review for a quarter exists at `factory-evidence/control-plane-push/access-review/<YYYY>-Q<n>/review.md`, signed by the owner, and the evidence collector's `run-manifest.json` reports it present and recent.
- `grep` over the evidence finds no `acw_` key values and no `CFACTORY_API_KEYS` values.
