---
status: approved
issue: 3905
spec: spec/2026-11-25-3905-project-access.md
coders:
  1: codex   # reserved ServiceCredential type + reserved scopes: security boundary
  2: codex   # /me/projects + /access/resolve: delegated identity, boundary intersection
  3: codex   # team membership writes, preview, SSO tombstones: authz semantics
  4: codex   # PFactory binding + resolver + replace local OrgMember checks
  5: codex   # TFactory, same as 4 (separate repo, same contract)
  6: codex   # CFactory principal contract, nginx/ingress, editor credential: security
  7: codex   # CFactory project_id on both writers + backfill: data correctness
  8: codex   # CFactory authorization decisions + filtered computed data: security
  9: codex   # stream grant expiry + revocation across four portals: subtle
  10: codex  # delegated identity on proxies + failure path: security
  11: agy    # Access page, My access, account-menu links, switcher role badge: UI breadth
  12: codex  # E2E D7 with all negative cases: guarded live test
reviewers:
  - codex    # reviews the agy and coder steps
  - agy      # reviews the codex steps
---

# Plan: show each user only their projects, with their role (#3905)

## Approved decisions (from the spec; this plan stands on its own)

### The grant model

1. **Today's AIFactory grant model is kept exactly.** Default-team projects
   inherit the org role. Other teams' projects need a team membership.
2. **One Access page**, in AIFactory, linked from every portal.
3. **The other portals ask AIFactory.** They cache with an absolute expiry
   of 60 s and fail closed with 503. There is no local fallback.
4. **CFactory#575 is part of this work.**
5. **Who edits access:** org admins and owners for their org, team admins
   for their own team.
6. **Edits change team membership.** A preview shows the effective role per
   project before and after the edit.
7. **Unbound or unmapped items** are visible only to org admins and owners.

### Access rules everywhere

- **An invisible project returns 404.** A role that is too low returns 403.
- **AIFactory is the only permission store.**
- **Service and MCP keys keep their scopes.**
- **Order:** this comes after the earlier #3857 phases, and #575 lands
  before #574.

### D1. AIFactory

**A new `ServiceCredential` table**, with the `acs_` prefix:

- it is ownerless;
- its scopes are `access:read` and/or `act-as`;
- its boundary is one org, or an explicit `fleet: true` flag;
- only an org owner can issue it (the instance owner for a fleet
  credential), and it is audited;
- issuing or validating an `ApiKey` rejects the `access:read` and `act-as`
  scopes.

**`GET /api/me/projects`** returns
`[{project_id, slug, name, org_id, team_id, role, binding:{provider, host, owner, name}}]`
plus `orgs:[{org_id, role}]`.

**`POST /api/access/resolve`** takes `{issuer, sub}` in the body:

- it needs an `acs_` credential with `access:read`;
- the subject must be active, otherwise the result is `[]`;
- grants are computed as the target user's principal, then intersected
  with the credential's boundary for each grant;
- each call is audited with the credential, a hash of the subject, the org
  and the decision.

**`GET /api/projects`** gains `role` and `binding`.

**Team routes:**

- `GET`, `PUT` and `DELETE` for teams and members, plus `POST …/preview`;
- a default-team membership cannot restrict a user below their org role
  (the preview points the admin to the org role instead);
- SSO sync only adds memberships. It never overwrites or recreates a
  `provenance: manual` row, and a manual row that was deleted stays as a
  tombstone;
- assignable roles are viewer, member and admin, never above the editor's
  own role, and only to members of the org.

### D2. PFactory and TFactory

**Binding.**

- Each local project gets `aifactory_project_id`, backfilled by matching
  the full canonical binding.
- Ambiguous or missing matches stay unbound and are reported.
- New projects bind when they are created.

**Who sees what.**

- A bound project follows the AIFactory grant.
- An unbound project is visible only to local org owners and admins.

**Humans.**

- Each request resolves through `/api/access/resolve`, using the portal's
  `acs_` credential and the issuer plus `oidc_sub`.
- When `oidc_sub` is missing, the account is linked by verified email at
  login. If that fails, the user sees no bound projects.

**Keys and tokens.**

- A user-owned key gets its owner's grants, clamped by the key's scope and
  org ceiling.
- Ownerless org keys, legacy tokens and TFactory's Copilot token keep
  today's service behaviour on the routes that use them today.

**One authz helper** replaces every local `OrgMember` check:

- TFactory's DB-backed list and spec intake;
- PFactory's project creation, unmatched intake and plan sessions.

A plan session with no project is visible to its creator and to org
admins.

### D3. CFactory

**Principals, one per transport.**

- **Browser:** nginx strips any client-sent `X-Forwarded-Id-Token` and sets
  it only from oauth2-proxy. The token must be valid: issuer, a mandatory
  audience, not expired, and a non-empty `sub`. There is no fallback to a
  key. `X-Tenant-Id` must match the principal's org.
- **Sibling portals:** an `acs_` credential with `act-as`, plus
  `X-Acting-User`, accepted only on search and the needs-you count.
- **Direct and MCP callers:** per-client keys. Without `all-projects` they
  see nothing scoped to a project.
- **Event producers:** ingest only.

**Hardening.**

- In user mode, Helm routes `/api` only through nginx.
- `/api/settings/token` and `/connect/vscode` issue a dedicated read-only
  client credential per user. Privileged keys are never handed out.

**Project ids.**

- `project_id` is stored on `WorkItem` and on cards, set from AIFactory's
  `projectId` by both writers (`upsert_from_event`, `upsert_snapshot`).
- A card that has not been dispatched takes the tenant's bound default
  repo, marked `project_provisional`.
- A conflicting update is kept and raises an anomaly.
- A backfill job assigns historical items through AIFactory task lookups.
  Unresolved items get `null`, which means admins only.

**Roles in CFactory.**

| Action | Role needed |
|---|---|
| Reading | viewer |
| Card edits, comments, sync and import | member |
| Stage actions and HITL propose/execute | member |
| `delete_task` | admin |
| The fleet audit chain | org owner or admin |

**The filter covers every route, the MCP tools and Copilot**, as listed in
spec D3. `CFACTORY_USER_AUTHZ` can be set per tenant.

### The other designs

- **D4. Streams in all portals:**
  - each connection holds grants with an absolute `expires_at` (fetch time
    plus 60 s), re-resolved before a frame is sent once that has passed;
  - a failed renewal closes the stream;
  - when a grant is revoked, queued frames are dropped and a `revoked`
    control message is sent;
  - untagged events go only to their target user;
  - AIFactory's existing 300 s key timer stays.
- **D5. Search and count proxies:**
  - they send `act-as` plus `X-Acting-User`;
  - an upstream failure returns 503, never empty results;
  - a caller with no subject gets 403.
- **D6. UI:**
  - the Access page (admin grid plus preview, and "My access" for
    everyone);
  - links from every portal's account menu;
  - an optional `role` badge in `SwitcherProject`, vendored to the portals
    with a `HUB_PIN_SHA` bump.
- **D7. E2E:**
  - projects V and H sit under different non-default teams in one tenant;
  - the flag is on for the E2E tenant;
  - the run includes every negative case in spec D7.
- **Deployment:** prod k3s through gitops only. No p510.

### Order and branches

```
1 → 2 → 3 (AIFactory release A)
          ├→ 4 (PFactory) ─┐
          ├→ 5 (TFactory) ─┼→ 9 (streams) → 10 (proxies) → 11 (UI) → 12 (E2E) → flag on per tenant
          └→ 6 → 7 → 8 (CFactory, flag off) ┘
```

| Repo | Branch | Base |
|---|---|---|
| AIFactory | `feat/3905-access-api` | `dev`, after #2233 and #3906 have merged (both touch `auth.py` and routes) |
| PFactory | `feat/3905-access` | `dev` |
| TFactory | `feat/3905-access` | `dev` |
| CFactory | `feat/3905-authz` | `dev`, after #3906 step 8 has merged |
| Factory (hub switcher and E2E) | `feat/3905-access` | `origin/main` |

Step 9 touches all four repos. Make one commit per repo, on that repo's
branch.

- **Step 10** ships only after step 8 is live in prod, with the flag still
  off.
- **Step 12** runs with the flag on for the E2E tenant only.


### Revision 2 corrections (from the plan reviews; part of this plan)

These override the steps below wherever they disagree.

**Gates.**

- **AIFactory steps 1-3** start only after AIFactory#2233 **and then**
  #3906's AIFactory steps 1-7 have merged to AIFactory `dev`.
- **CFactory steps 6-8** start only after #3906 step 8 has merged to
  CFactory `dev`. Keep its pause guard at execute time and its adapter
  fields.
- **Steps 4-6 go live** only after the owner has created the `acs_`
  credentials (as sealed secrets) and set `CFACTORY_OIDC_AUDIENCE`. These
  are release prerequisites, not after-steps.
- **The vendored switcher PRs** start only after the hub switcher change
  has merged to Factory `main`.
- **Step 10** depends on step 8 being live. It does not depend on step 9.
- **Step 12** also depends on #3906's E2E harness changes, which touch the
  same `scripts/e2e` files. Rebase on them.

**Step 1.**

- Reserve the two scopes in **every** key-validation path: `auth.py`,
  `mcp_stdio/auth.py:97` and the remote MCP auth.
- Audit both issuing and revoking.
- Test that an `acs_` principal is confined to its routes: the access
  routes, plus search and count for `act-as`. Everything else returns 403.

**Step 2.**

- `/access/resolve` returns exactly the `/me/projects` shape, including
  `orgs`.
- The `orgs` entries are also intersected with the credential boundary.
- The `issuer` is checked against the configured Keycloak issuer before
  `oidc_sub` is resolved. An unknown issuer returns 400.

**Step 3: change the shared grant calculation.**

- `_team_grant` (`project_authz.py` ~75-125) ignores tombstone rows.
- On a default-team project, the effective role is the **higher** of the
  team row and the org role, so an existing lower row cannot mask the org
  role. The list, the detail view, delegated resolution and the preview then
  all agree.
- Add a migration with a `tombstone` flag on `team_memberships`.
- The routes are exactly as the spec gives them:
  - `GET /api/orgs/{org}/teams`;
  - `GET /api/teams/{team}/members`;
  - `PUT` and `DELETE /api/teams/{team}/members/{user}`;
  - `POST /api/teams/{team}/members/{user}/preview`.

**Steps 4 and 5: binding rules.**

- **The backfill source** is an admin-scoped `/api/me/projects`, using the
  owner's session. A project binds only on a unique, full canonical match.
- **A local project without a binding** cannot be used by non-admins until
  it is bound.
- **A new project** binds at creation, either to an existing AIFactory
  project or through successful onboarding.
- **Keep** the existing local ids, role thresholds and 404/403 meanings.

Separate file lists:

| Repo | Files |
|---|---|
| PFactory | `apps/web-server/server/routes/project_authz.py`, `routes/projects.py`, the plan-session routes, the unmatched-intake routes, `auth_routes.py` and `oidc_routes.py` (login linking), new `services/access_client.py` |
| TFactory | `apps/web-server/server/routes/project_authz.py`, `routes/projects.py` (the DB-backed list), the spec-intake route, `auth_routes.py` and `oidc_routes.py`, new `services/access_client.py`, and the Copilot token path, which stays unchanged |

PFactory's plan-session work is not part of TFactory.

**Step 6.** In `nginx.conf.template`, **every** `location` that proxies to
the backend strips any `X-Forwarded-Id-Token` the client sent and sets it
from oauth2-proxy. That includes `/connect/`, which misses it today. Test
the `/connect/` path.

**Step 7.**

- Both writers take `projectId` only from the trusted AIFactory adapter.
- Dispatch replaces a provisional card binding.
- A later conflict keeps the stored id unless an explicit rebind happens,
  and raises an anomaly.

**Step 8: the CFactory rules, written out.**

- `services/access_resolver.py` calls AIFactory `/api/access/resolve` with
  CFactory's `acs_` credential, caches with an absolute expiry of 60 s, and
  returns 503 on failure.
- `CFACTORY_USER_AUTHZ` has a global default of `off`, with an override per
  tenant.
- Filtering happens **before** every read, aggregation, ranking, truncation,
  outbound call and mutation.
- Copilot gets a filtered store.
- The principal reaches both MCP contexts.
- **Tests:** besides the route-coverage test, add a behavioural test for
  each path family:
  - work items and drill-downs;
  - aggregates;
  - search and count;
  - actions and audit;
  - Copilot;
  - cards;
  - investigations;
  - live agents;
  - git config;
  - MCP.

  Each test asserts that hidden data never appears in the response body.

**Step 9: idle streams.**

- Each connection schedules a wakeup at `expires_at` and re-resolves its
  grants then, even when no frame is waiting.
- **On a failed renewal:**
  - WebSocket: close with code 4403 and reason `authz_expired`;
  - SSE: send `event: revoked`, then close;
  - client: clear the project's state when it gets `revoked` or that close.
- **Tests:**
  - a failed renewal closes the stream;
  - an idle connection is revoked within 60 s;
  - AIFactory's 300 s key and org timer still runs.

**Step 10: `act-as` is always scoped.**

- In CFactory, every accepted `act-as` request is filtered to the acting
  user, or fails closed. This holds **even when `CFACTORY_USER_AUTHZ` is
  off**, so no proxy cutover can return results from the whole fleet.
- **Tests:**
  - the flag off;
  - mixed versions: an old proxy with a new CFactory, and the other way
    round;
  - a rollback of this step.
- Rolling back the proxies drops the `act-as` header. It never turns
  fleet-wide results back on for a user.

**Step 11.**

- Wire the role into each portal's switcher data. In CFactory that is
  `apps/frontend-web/src/useDashboard.ts:207`, which today maps only the
  slug and the name.
- Add the Access link to AIFactory's own account menu too.
- Group the grid by team, and show the preview before an edit is confirmed.
- When the count pollers in the three portals get a 503, they show an
  error state instead of a stale count.

**Step 12: the live proof, written out.**

- **Owner setup:** the test user, a membership in V's team only, and the
  flag turned on for the E2E tenant.
- **The harness** runs from a Factory worktree:

  ```bash
  python3 -m scripts.e2e.run --journey ACCESS:ui+api:1 --live --campaign <id>
  ```

- **H must be absent, or return 404, in all of:**
  - lists and the switcher;
  - legacy and canonical deep links, and task and card ids;
  - search and count;
  - every stream, including queued frames;
  - MCP;
  - CFactory drill-downs, actions and Copilot.
- **V must work** with the role `member`.
- **Revocation:** revoke right after a cache fill. V must disappear within
  60 s on both an active and an idle connection, and stay gone after a
  reconnect.
- **Default-team inheritance** gets its own case.
- **Negative cases:** each one maps to the repo that owns its unit test.
- **Fixtures** are created only through the guarded registry, then swept.

**Verify commands** (these replace "Repo traps" where the two disagree):

- **AIFactory web tests** run the way CI runs them, from the repo root with
  the **backend** venv:

  ```bash
  /mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin/pytest apps/web-server/tests/<file> -o asyncio_mode=auto -q
  ```

- **PFactory and TFactory:** the same pattern, with each repo's backend
  venv.
- **Every step** names its exact test files in its first commit message.

**Security review:** steps 1, 2, 6, 8, 9 and 10.

**Who does what:**

- **The lead:** commits.
- **The owner:** live config, credentials, tenant flag changes and prod
  deploy approval.

## Repo traps (every step)

- **AIFactory tests:**
  - backend:
    `/mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin/pytest tests/<file> -q`
  - web server, from the repo root:
    `/mnt/code/Source-home/GitHub/AIFactory/apps/web-server/.venv/bin/pytest apps/web-server/tests/<file> -o asyncio_mode=auto -q`
  - name the files explicitly;
  - new routes go in `test_project_authz_route_table.py`.
- **PFactory and TFactory tests:** run their own venvs the same way. The
  PFactory `tests/test_mcp_remote_session_key.py` failures in the local
  venv are a known `mcp` version mismatch. CI decides those.
- **CFactory tests:**
  `PYTHONPATH=apps/backend /mnt/code/Source-home/GitHub/CFactory/apps/backend/.venv/bin/pytest tests/<file> -q`.
  Frontends use `npm run typecheck` and `npx vitest run <files>`.
- **Ruff:** run `ruff check` and `ruff format --check` on the changed Python
  files.
- **Migrations:** each schema change gets an Alembic migration with a
  downgrade, tested up, down and up again.
- **Credentials:**
  - the legacy shared token has full access by default, so refuse it
    explicitly on every new access route;
  - never log credentials or subjects;
  - `acs_` secrets are shown once and stored hashed.
- **Implementers never** stage, commit, push, deploy or restart. The lead
  commits after each step.

## Steps

### 1. ServiceCredential (AIFactory)

**What to build.**

- Add a model, a migration, `acs_` authentication in `auth.py` (setting
  `request.state.user` with `service_credential_id`, `scopes`, `org_id` and
  `fleet`), and admin issue and revoke routes.
- Reserve the two scopes in `ApiKey` issuance and in the key auth
  validation.

**Tests** (`apps/web-server/tests/test_service_credentials.py`):

- issuance by an owner;
- refusal for an admin or member;
- a fleet credential issued only by the instance owner;
- an `ApiKey` carrying a reserved scope is rejected both at creation and
  at authentication;
- the secret is stored hashed and shown once.

**Verify:** the web pytest on that file, plus
`test_project_authz_route_table.py`.

### 2. Access reads (AIFactory)

**What to build.**

- `GET /api/me/projects` and `POST /api/access/resolve`, as decided above.
- `role` and `binding` in `project_to_response`.
- Keep `role` from `_team_grant` and clamp it through `_effective_role`.
- Build the target principal separately from the credential.

**Tests** (`test_access_api.py`):

- roles for default-team and non-default-team projects;
- the boundary intersection for a multi-org subject;
- an inactive or unknown subject returns `[]`;
- the legacy token and `ApiKey`s are refused;
- the audit row is written;
- the subject is never in the URL.

### 3. Team membership writes (AIFactory)

**What to build.**

- The routes, the preview, and the default-team rule.
- SSO provisioning (`oidc/provisioning.py`): honour `provenance` and the
  tombstones.

**Tests** (`test_team_membership_routes.py`):

- the permission matrix for owner, admin, team admin and member;
- the role ceiling;
- the preview shows inherited roles;
- deleting a default-team membership behaves as specified;
- SSO login does not recreate a manually deleted row.

### 4. PFactory

**What to build.**

- An `aifactory_project_id` column, its migration, and a backfill script
  (`scripts/backfill_aifactory_binding.py`) with a dry-run report.
- Binding at creation.
- An `access_client` with absolute-expiry caching and fail-closed
  behaviour.
- A single authz helper used by `visible_project_ids`,
  `require_project_role`, project creation, unmatched intake and plan
  sessions.
- Linking `oidc_sub` by email at login.
- The key-identity rules.
- An inventory script that counts users without `oidc_sub` and unbound
  projects.

**Tests:**

- the resolver: cache expiry and 503 on a timeout or 5xx;
- bound, unbound and hidden projects;
- a user key clamped to its scope;
- ownerless, legacy and Copilot callers unchanged on the service routes;
- the 404 and 403 semantics are kept;
- the plan-session rule;
- the backfill on a duplicate repo name across hosts.

### 5. TFactory

The same as step 4, plus the DB-backed list and spec intake. TFactory's
Copilot token keeps its behaviour.

### 6. CFactory principals

**What to build.**

- `principal_dep` with the transport contract above, replacing key-only
  access on the authz paths.
- `nginx.conf.template`: strip any client-sent identity header and set it
  from oauth2-proxy.
- The Helm ingress: `/api` goes only through nginx when user mode is on.
- `/api/settings/token` and `/connect/vscode`: issue the per-user read-only
  client credential.
- Bind the tenant to the principal.

**Tests:**

- a spoofed header is rejected;
- a missing or invalid token gets no key fallback;
- a wrong audience is refused;
- a tenant mismatch is refused;
- the editor hand-out returns only its dedicated credential;
- `act-as` is accepted only on search and the count.

### 7. CFactory project ids

**What to build.**

- The `project_id` and `project_provisional` columns and their migration.
- Both writers set them from the adapter's `projectId`. The adapter and
  `AdapterItem.to_state` carry it.
- A conflict raises an anomaly.
- The backfill job, with a report.

**Tests:**

- an event arriving before the poll, and a poll arriving before the event;
- a replay;
- a change of the default repo;
- a card before and after dispatch;
- an ambiguous item becomes admin-only.

### 8. CFactory filters (behind the flag)

**What to build.**

- An authz dependency on every project-bearing route listed in spec D3, on
  every MCP tool in both contexts, and on Copilot's context and tools.
- The role table above.
- The check runs before any upstream call or mutation.

**Tests:**

- `tests/test_authz_route_coverage.py` enumerates the FastAPI routes and the
  MCP tools, and fails when one that carries a project lacks the
  dependency;
- hidden reads, aggregates, actions, Copilot and live agents;
- the role checks;
- with the flag off, behaviour is unchanged.

### 9. Streams (all four repos)

**What to build.** The grant expiry, the revoked control frame, dropping
queued frames, and delivering untagged events only to their target. Cover:

- AIFactory: `/ws/events`, the task and log sockets, terminal, rmux and SSE;
- PFactory and TFactory: `/ws/events`, logs, progress, console, rmux and
  SSE;
- CFactory: `/api/ws`, the ingest and progress broadcasts (with tenant and
  project), `LiveProgress.project_id`, and the live-agent console.

**Tests per repo:**

- revocation just after a cache fill, on an active connection and on an
  idle one;
- queued frames are dropped;
- after a reconnect the project stays hidden;
- an untagged GitHub-auth event reaches only its target user.

### 10. Proxies (AIFactory, PFactory, TFactory)

**What to build.** In `routes/search.py`, send `act-as` plus
`X-Acting-User`. Return 503 on an upstream error. Return 403 when there is
no subject.

**Tests:** the header is sent; 503 is passed through; the service caller
gets 403.

### 11. UI

**What to build.**

- AIFactory: the Access page (the grid, edit with preview, and "My
  access").
- Account-menu links in PFactory, TFactory and CFactory.
- The hub `shared/factory-ui/ProjectSwitcher.tsx`: an optional `role`
  badge, then vendored with a `HUB_PIN_SHA` bump in each portal (the same
  two-stage process as Factory#3903).

**Tests:** vitest for the grid, the preview confirm, "My access" and the
badge. Typecheck each portal.

### 12. E2E (Factory)

**What to build.**

- The D7 journey in `scripts/e2e`, with an owner-provided non-admin test
  user. The agent never creates the user.
- Set up V and H through the step 3 team routes, under the owner's
  credentials.
- Turn the flag on for the E2E tenant only.
- Every negative case from spec D7.

**Tests:** unit tests in `tests/e2e/unit` with real payload shapes, then
the live run.

## After the steps (lead)

1. **Per PR:** an Opus review against this plan plus the `reviewers:`.
   Steps 1, 2, 6 and 9 also get an explicit security review.
2. **Merge and release in the order above.** Merge with
   `--match-head-commit`. For each repo: release PR, then sync PR. Check
   the version, the pod code and Argo after each release.
3. **Owner actions:**
   - issue the `acs_` credentials for PFactory, TFactory and CFactory, and
     put them in sealed secrets;
   - set `CFACTORY_OIDC_AUDIENCE`;
   - create the E2E test user.
4. **Run the inventory and backfill reports.** Review the unbound counts
   before step 10.
5. **Run step 12 live.** Then turn the flag on tenant by tenant.

## Tests

Every step's tests must pass, and so must each repo's full suite.

## Rollback

- **CFactory:** set `CFACTORY_USER_AUTHZ=off` for the tenant.
- **PFactory and TFactory:** revert their PRs. The binding columns stay
  unused.
- **AIFactory:** the new routes and credentials are additive. Revert the PR
  and revoke the `acs_` credentials.
- **Proxies:** revert step 10.
