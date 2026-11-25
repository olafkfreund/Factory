---
status: draft
issue: 3905
intent: intent/2026-11-25-3905-project-access.md
---

# Spec: show each user only their projects, with their role, in every portal

## Approved intent decisions

1. Today's AIFactory grant model stays exactly as it is:
   - default-team projects inherit the org role;
   - other teams' projects need a team membership.
2. There is one access page, in AIFactory, linked from every portal.
3. The other portals ask AIFactory with the caller's identity. They cache
   the answer for at most 60 s, fail closed when AIFactory is unreachable
   (503), and never fall back to local tables.
4. CFactory#575 is part of this work, once CFactory knows who the user is.
5. Who may edit access:
   - org admins and owners for their org;
   - team admins for their own team.
6. Edits change team membership, and the page shows which projects each
   edit affects.
7. CFactory items that map to no project are visible to org admins and
   owners only.

The intent also fixes these:

- an invisible project returns 404, and a role that is too low returns 403;
- AIFactory is the only store of permissions;
- service tokens and MCP keys keep their scopes.

## Facts this design builds on

Taken from `origin/dev` on 2026-11-25.

### Login

- **One Keycloak realm, one client per portal.** Each portal mints its own
  HS256 JWT after the OIDC callback (`oidc_routes.py:209-273`,
  `auth_routes.py:97-111`) and accepts it in a cookie or a bearer header
  (`auth.py:334-361`).
- **A portal JWT cannot be forwarded to another portal.** Each portal signs
  with its own secret.
- **The shared user key is `users.oidc_sub`** (the Keycloak `sub`).
  AIFactory, PFactory and TFactory all have it. `TeamMembership.user_id` is
  AIFactory's local user id.

### AIFactory access logic

- `_team_grant` returns the role and the team (`project_authz.py:75-125`).
- `_effective_role` clamps that role by the scope ceiling (`:128-144`).
- `accessible_project_ids` returns ids only and drops the role (`:226-258`).
- **No endpoint returns the caller's projects with their roles.** There is
  no route to list or create team memberships; only SSO provisioning writes
  them. There is no access UI.
- **The legacy shared token** (`APP_API_TOKEN`, with
  `LEGACY_SHARED_TOKEN_FULL_ACCESS` on by default) sees every project.
  PFactory, TFactory and CFactory all call AIFactory with it, or with
  per-org `acw_` keys. Neither carries a user.

### PFactory and TFactory

Their `visible_project_ids` uses their own local `OrgMember` table
(PFactory `project_authz.py:215-241`, TFactory `:262-300`).

### CFactory

- **Request auth:** API keys with read and write scopes only.
- **The browser path:**
  - oauth2-proxy adds the Keycloak ID token;
  - nginx swaps `Authorization` for the API key and forwards the ID token
    as `X-Forwarded-Id-Token` (`nginx.conf.template:40-66`);
  - `enterprise.oidc_actor` verifies that token against JWKS, but only to
    record the audit actor (`enterprise.py:124-201`).
- **A `WorkItem` has no project id,** only a repo per service and a
  correlation key.

### Paths that leak

- **Search and the needs-you count.** The search proxies in AIFactory,
  PFactory and TFactory (`routes/search.py`) call CFactory with a shared
  read key and drop the user. CFactory's `/api/search`,
  `/api/needs-you/count`, `/api/workitems`, rollups, tokens, anomalies and
  cards take no principal (`routes_workitems.py:35-195`).
- **Streams.**
  - **CFactory `/api/ws`** sends the full snapshot to any key; it filters by
    tenant only.
  - **AIFactory `/ws/events`** already checks each event that carries a
    `projectId` or `taskId` (`event_bus.py:319-330`,
    `task_access.py:21-32`). The gaps are events with no project and the
    60 s re-check, which does not re-check grants.
  - **PFactory and TFactory sockets and SSE** have not been audited.

## Design

### D1. The access API in AIFactory

**Two reads, one shape.** Each returns
`[{project_id, slug, name, org_id, team_id, role}]`, built from
`_team_grant` plus `_effective_role`:

1. **`GET /api/me/projects`** returns the caller's own projects.
2. **`GET /api/access/projects?oidc_sub=<sub>`** returns another user's
   projects, on behalf of a sibling portal. It accepts only an `acw_`
   service key with the new scope `access:read`.
   - The key may resolve users only in its own org, or in every org for a
     fleet key that has been explicitly flagged.
   - The **legacy shared token is refused** on this route: 403, whatever
     `LEGACY_SHARED_TOKEN_FULL_ACCESS` says.
   - An unknown `sub` returns `[]`.

**Roles everywhere.** `GET /api/projects` and the `project_to_response`
fields gain `role`, the caller's effective role.

**Writes for team membership** (decision 6):

- `GET /api/orgs/{org}/teams`;
- `GET /api/teams/{team}/members`;
- `PUT /api/teams/{team}/members/{user}` with `{role}`;
- `DELETE /api/teams/{team}/members/{user}`.

Who may call them follows decision 5. Each change records `provenance:
"manual"` and is audited. SSO-provisioned rows can be changed. The writes
return the list of projects each change affects.

### D2. PFactory and TFactory ask AIFactory

**The resolver.** Their `visible_project_ids` and `require_project_role`
resolve through a shared client, `access_client`:

- it calls D1.2 with the portal's `access:read` key and the caller's
  `oidc_sub`;
- it caches per `sub` for 60 s;
- on a timeout or a 5xx it raises 503 (fail closed).

**Mapping projects.** Local projects map to AIFactory projects by repo
`owner/name`, the same key AIFactory's `resolve_project_id` uses. A local
project with no AIFactory match is visible only to local org owners and
admins (decision 7, applied here too).

**Local accounts** without an `oidc_sub` get no projects. A legacy shared
token or a service caller keeps today's behaviour on non-user routes.

**No local fallback.** The `OrgMember` path is removed as a fallback, which
keeps AIFactory the only permission store.

**Roles in the lists.** The project-list responses gain `role` from the
resolver.

### D3. Search, counts and streams

- **Search and the needs-you count.** The three proxies (`routes/search.py`)
  send the caller's `oidc_sub` to CFactory as `X-Acting-User`, together with
  the read key. CFactory acts on that header only from keys with the new
  scope `act-as` (D4). The proxies drop results with no project.
- **AIFactory `/ws/events`.**
  - Events with no project are sent only to org admins and owners.
  - The 60 s re-check re-resolves project grants for every connection.
  - Tests prove that an org member with no grant on team B receives no
    team-B event.
- **PFactory and TFactory** `/ws/events`, the logs sockets, `agent-console`
  and SSE each get the same per-project check through the D2 resolver, at
  connect and at every re-check.

### D4. CFactory user identity and project authorization (#575)

**Who is asking.** A new dependency, `principal_dep`, decides this per
request:

- **Browser path:** `X-Forwarded-Id-Token`, verified with JWKS. The audience
  check becomes required (`CFACTORY_OIDC_AUDIENCE` must be set when user
  mode is on).
- **A proxied path from a sibling portal:** a key with scope `act-as` plus
  `X-Acting-User`.
- **A key-only caller** (MCP, editor) with no user sees everything only if
  its key has the new scope `all-projects`. Otherwise it sees nothing that is
  scoped to a project.

**Which projects.** The visible projects come from AIFactory D1.2, using
CFactory's `access:read` key and the user's `sub`, cached for 60 s and
failing closed.

**Project on every item.** `WorkItem` and cards gain `project_id`, resolved
at ingest from the AIFactory project id or the repo through AIFactory's
mapping. A migration backfills existing rows. Items that stay unmapped are
visible to org admins and owners only.

**Where the filter applies:**

- the work-item list and detail (404 for invisible items);
- rollups, tokens, anomalies and cost;
- search and the needs-you count;
- cards;
- the live-agent proxy;
- MCP list and rollup;
- `/api/ws`, with a per-connection filter on the snapshot and on every
  broadcast, re-checked every 60 s.

**The switcher list** comes from D1.2 (each with its role) instead of being
derived from git connections. Git connections stay the source of repo
details.

**Rollout.** A flag, `CFACTORY_USER_AUTHZ=on`, switches user mode on.

### D5. Access page and roles in the switcher

**AIFactory "Access" page** (in settings):

- **Admins** see a grid of users × projects × roles, grouped by team.
  Editing a team membership through D1 shows the projects that change will
  affect before it is confirmed.
- **Everyone else** sees "My access", their own list from D1.1.

**The other portals** link to it from their account menu.

**The shared `ProjectSwitcher`:**

- `SwitcherProject` gains an optional `role`, shown as a small badge;
- a project that is no longer visible is dropped from the recent list (as
  today), so a revoked project disappears.

The change is vendored to the portals with a `HUB_PIN_SHA` bump.

### D6. E2E proof (Factory)

**The setup.**

- The owner creates the non-admin Keycloak test user (#3882 G5).
- The harness gives that user, through D1 writes, member access to one team
  that owns project V. Project H stays in another team **in the same
  tenant**.

**The checks, in all four portals.** The test fails if H appears in, or is
served by, any of these:

- the project list or the switcher;
- a deep link (legacy and canonical URLs; task and card ids) — this must
  return 404;
- search or the needs-you count;
- the WebSocket or SSE stream;
- MCP.

V must work with the role `member`.

**Revocation.** After D1 removes the user's access, V disappears within
60 s, including from an open stream.

## Order of delivery

```
D1 (AIFactory API + roles)
  → D2 (PFactory/TFactory)
  → D3 (proxies + AIFactory/PFactory/TFactory streams)
  → D4 (CFactory)
  → D5 (UI)
  → D6 (E2E)
```

Each repo ships behind its own release. D4 starts with the flag off, and
the flag is switched on after D6 passes.

## Alternatives rejected

- **Forwarding portal JWTs to AIFactory.** Each portal signs with its own
  secret. Sharing one secret would let any portal forge users for all the
  others.
- **Verifying Keycloak access tokens in AIFactory for sibling calls.** The
  sibling portals hold their own session cookies, not Keycloak access
  tokens, so they have nothing to forward. That would need a token exchange
  per request.
- **Copying grants into each portal.** That would be a second permission
  store (constraint).
- **Using the legacy shared token for access reads.** It is all-or-nothing.
- **Filtering only in the frontends.** It leaves the APIs, streams and MCP
  open.

## Risks

- **`act-as` and `access:read` keys are powerful.** They are scoped to one
  org (or flagged fleet keys), held only by the portals' control planes as
  sealed secrets, never handed to agents, and audited per call.
- **Fail-closed means an AIFactory outage blanks the other portals.** This
  is accepted (decision 3). Health checks and alerts cover it.
- **Local accounts with no `oidc_sub` lose project visibility** in
  PFactory, TFactory and CFactory. Today that is only the bootstrap owner,
  and the plan checks this.
- **The CFactory backfill** may leave items unmapped. Those go to admins
  only, which is safe; the plan reports the count.
- **Hosts:** prod k3s through gitops only. No p510.

## Verification

- **Unit tests per repo** for each D item:
  - roles from D1.1 and D1.2;
  - the legacy token refused on D1.2;
  - team-member writes, with both permission levels;
  - the resolver: caching, fail-closed and mapping;
  - the 404 and 403 behaviour;
  - the proxies sending `X-Acting-User`;
  - CFactory: the principal per path, the filter on every listed route, and
    the stream filter;
  - the switcher role badge.
- **Live:** the D6 E2E check, before `CFACTORY_USER_AUTHZ` is switched on in
  prod.
