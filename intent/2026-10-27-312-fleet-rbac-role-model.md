---
status: draft
issue: 312
author: olafkfreund
---

# Intent: fleet RBAC role model and quarterly access review

Epic: olafkfreund/Factory#312 (IAM & access control). This intent covers one checkbox of the epic: "Fleet RBAC role model + quarterly access reviews (evidence)". The other checkboxes (retire `APP_API_TOKEN`, enforce MFA, gate `DISABLE_AUTH`) are out of scope here. Related: #1960 (agent identity and autonomy ceiling), #555 (shared token deprecation), #324 (evidence collector). Policy: `docs/compliance/policies/iam-access-control.md` gaps 5 and 6.

This wave writes documents only: this intent and its spec. No plan and no code.

## Problem

Each factory has some access control, but nothing ties the pieces into one model, and nobody reviews who holds what. Checked on 2026-10-27 against `origin/dev` of each service and `origin/main` of `factory-gitops`:

| Plane | What exists | Source |
|---|---|---|
| AIFactory, PFactory, TFactory | Org roles `viewer < member < admin < owner` (`ROLE_LEVELS`), enforced by `require_org_role(...)` | `apps/web-server/server/routes/organizations.py:38` in each repo |
| AIFactory, PFactory, TFactory | `acw_` keys: per user and per org, scopes `mcp:read` / `mcp:write`, optional expiry | `routes/api_keys.py`, `mcp_remote/auth.py` |
| AIFactory | `acw_` key `autonomy_ceiling` (`low`/`medium`/`hard`, nullable, set by org admin only), `agent_identity = agent:aifactory/<key_id>`, `cap_disposition` takes the stricter of ceiling and merge decision. Not wired into the merge path yet. An `acw_` key cannot mint keys. | AIFactory #1887; `database/models.py:399-406`, `routes/api_keys.py:170-186` |
| AIFactory only | Access-review NDJSON export of one org's members (email, role, `last_login_at`, active), admin or owner only | `routes/access_review.py` |
| CFactory | `CFACTORY_API_KEYS` keystore with bare `read` / `write` scopes; empty store denies (CFactory #500). MCP: legacy `CFACTORY_MCP_SECRET` still grants read and write by default; use is now counted (CFactory #504). Audit actor is a hash of the key, never the key. | `apps/backend/cfactory/auth.py`, `mcp.py` |
| Keycloak | One `factory` realm, GitHub-brokered logins, one group per tenant emitted as a `tenant` claim. No role mapper, configured imperatively with `kcadm.sh`. | `factory-gitops/docs/keycloak-sso.md` §2b |
| Cluster | Workload service accounts are least-privilege: `aifactory-sandbox` (jobs, pods read), `cred-broker` (get/patch one Secret), evidence collector, deploy dry-run (create only). No human RoleBindings are in gitops. | `factory-gitops/apps/*/manifests/manifests.yaml` |

The gaps:

1. **No role is defined fleet-wide.** The same four role names exist in three services, but nothing says what a `member` may do in TFactory compared with AIFactory, or how a CFactory `write` key relates to an org role. CFactory has no human roles at all, only key scopes.
2. **Service principals are not roles.** `is_service_principal()` (`AIFactory/.../routes/project_authz.py:48-57`) treats any `is_service` caller as allowed past all per-org and per-project checks. Retiring that is #555, but the role model has to say what a service principal gets instead.
3. **`role == "admin"` from a JWT also bypasses per-org authz** (same function, line 57). No Keycloak role mapper emits a `role` claim today, so every human JWT falls back to `"user"`. If someone adds a role mapper that emits `admin`, that user skips every org check in every factory. The role model must not use that claim value until the bypass is fixed.
4. **Agents have no defined place.** #1960 gives agent keys an identity and a ceiling, but nothing says an agent's rights are capped by its key and tier and never inherit the role of the human who started the run.
5. **No access review happens.** One export exists, in one service, for one org per call. There is no cadence, no reviewer, no list of what must be reviewed (keys, CFactory keys, Keycloak users, cluster bindings), and no retained evidence. The evidence collector names an access-review drop point (`factory-evidence/control-plane-push/`) that nothing fills.

## Proposed outcome

- One committed document defines the fleet roles, gives a per-factory table of the actions each role may take, and maps each role onto the check that enforces it today, or marks it "not enforced" where nothing does.
- Service principals (one per M2M edge) and agents are mapped to explicit scopes. An agent's effective right is at most its key's scopes and autonomy ceiling. It is never the role of the human who invoked it.
- A quarterly access-review procedure names the reviewer, the inputs per plane, the output, the remediation deadline, and where the signed evidence is stored, so that a first review can be run and retained.
- The open decisions are listed for the owner, not guessed.

## Remaining slices, in order

1. **This lane:** intent and spec for the role model and the review procedure (documents only).
2. **Plan + doc:** commit the role catalog and the review runbook under `docs/compliance/` once the owner answers the open questions. Update `iam-access-control.md` where it is out of date (CFactory now fails closed on `/api`).
3. **Evidence tooling:** export `acw_` key inventories (scopes, ceiling, `last_used_at`, `expires_at`) and add access-review routes to PFactory and TFactory, or a single fleet export, and push results into the evidence drop point. Code, additive, read-only.
4. **First completed review** for the current quarter, signed and retained. This is the epic's acceptance criterion.
5. **Enforcement follow-ups**, each its own issue: remove the `role == "admin"` bypass, make keys without a ceiling count as `hard` (the #1960 hard gate), and give CFactory human roles from the IdP. These depend on #555 and the owner's IdP decisions.

## Affected users and systems

- Documents in this repo (`intent/`, `spec/`, later `docs/compliance/`).
- Read only, as sources: AIFactory, PFactory, TFactory, CFactory, `factory-gitops`, Keycloak configuration docs.
- People: the owner, who is the reviewer and the approver of role assignments.

## Constraints

- Documents only in this wave. No code, no plan, no changes to `factory-gitops` or the cluster (AIFactory 3.10.11 is mid-deploy).
- Must not lock out any human or service login, enforce MFA, or remove or rotate `APP_API_TOKEN`, `CFACTORY_MCP_SECRET` or any live credential. The role model describes the target. Enforcement is a later slice.
- Reuse what exists: the existing role names and the existing key scopes. Do not invent a parallel permission system.
- The access-review evidence must never contain a credential value. Keys appear by id or by `key_actor` hash only.

## Open questions

1. **Reviewer and segregation of duties.** The fleet has one owner. A review by the person who granted the access does not satisfy SoD for SOC 2 CC6.3 or SOX ITGC. Accept a single-owner review with a recorded exception, or name a second reviewer?
2. **Human cluster and platform access.** No human RoleBindings are in gitops, so kubectl, ArgoCD and Keycloak admin access are granted outside it. Should the model name a `platform-admin` role held only by the owner, and should the review list these accounts by hand until they are declarative?
3. **Where human roles come from.** Org roles live in each service's database today. Keep them per service and review each, or emit them from Keycloak (a role mapper)? The second is blocked until the `role == "admin"` bypass is removed.
4. **MFA (out of scope here).** Should the review record each account's MFA state, as an input for the MFA slice, while MFA is not yet enforced? This lane does not enforce or configure MFA.
5. **Retiring `APP_API_TOKEN` and `CFACTORY_MCP_SECRET` (out of scope here).** Until they retire, every review will show two credentials with fleet-wide reach. Record them as a standing accepted exception with the #555 date, or treat their presence as a failed review?
6. **Keys without an autonomy ceiling.** #1960 requires them to count as `hard` or be refused before the ceiling gates merges. Should the review flag every key with a null ceiling until then?
7. **CFactory human roles.** CFactory knows a tenant and a key, not a person's role. Is a `write` key held by a person equivalent to `member`, or should CFactory read org roles from a sibling?
