---
status: draft
issue: 3905
author: olafkfreund
epic: 3857
---

# Intent: show each user only their projects, with their role, in every portal

## Problem

Every portal should show a user only the projects they may use, and every
path that carries project data should respect the same rule. Today the lists
partly do, but the rule differs per portal, roles are invisible, and several
side paths leak across projects.

### What already works (verified on `origin/dev`)

- **AIFactory** `GET /api/projects` filters by team grant: `list_projects` →
  `_visible_projects` → `accessible_project_ids` → `_team_grant`
  (`routes/project_authz.py:75-125,226-258`).
  - On default-team projects, an org member without a team membership
    inherits their org role.
  - On other teams' projects, they get no access.
  - The route's docstring still says "org filter" and is stale.
- **PFactory and TFactory** `GET /api/projects` use `visible_project_ids`.
- **The switcher feed.** All three portals feed the shared switcher from
  that list (`api-adapter` → project store → `App.tsx` → `AppShell` →
  `ProjectSwitcher`).
- **404 for hidden projects.** All three return 404 for an unknown *or*
  hidden project, on purpose, so that project names cannot be probed. 403 is
  reserved for a visible project that needs a higher role.

### Gaps

1. **Three rule sets.** PFactory and TFactory decide visibility from their
   own local `OrgMember` table. They have no team grants and do not ask
   AIFactory. A user can therefore see a different set of projects in each
   portal.
2. **Roles are invisible.**
   - No project list returns the caller's effective role. AIFactory's
     `project_to_response` has no role field.
   - The switcher has no role field.
   - Recent entries only show when they are still in the supplied list.
3. **Search, the Needs-you count and the command palette leak.**
   - AIFactory, PFactory and TFactory proxy `GET /api/search` and
     `GET /api/needs-you/count` to CFactory with a shared read key, without
     the user's identity (`routes/search.py` in each).
   - CFactory searches every ingested work item and returns titles, repo
     names and correlation keys. It also returns a fleet-wide count.
4. **Live streams leak.**
   - AIFactory `/ws/events` routes by org only (`websockets/events.py`), so
     an org member receives events for other teams' projects.
   - CFactory `/api/ws` sends the full work-item snapshot to any valid key.
5. **CFactory has no user identity on requests.**
   - Its cockpit uses shared API keys (`CFACTORY_API_KEYS`). The OIDC token
     is used only to stamp audit actors.
   - It builds its project list from tenant git connections, not from a
     projects route.
   - Work-item lists, details, rollups, token totals, the live-agent proxy
     and its MCP tools are all tenant-wide (CFactory#575).
   - It cannot answer "which projects can this user see" until it knows who
     the user is.
6. **No access view.** AIFactory can list org members and edit org roles,
   but nothing shows the effective access per project (user × project ×
   role), and users cannot see their own.

The E2E campaign's leftover `e2e-…` projects crowd the list. That is
cleanup (#3882 sweeper), not access.

## Proposed outcome

- **One rule.** AIFactory's team-grant model is the single answer to "which
  projects can this user see, with which role". PFactory, TFactory and
  CFactory ask AIFactory instead of their local tables.
- **Lists show roles.** Every portal's switcher and project lists show only
  those projects, each with the user's effective role.
- **Every path obeys the rule:**
  - REST, deep links (legacy and canonical URLs, and indirect task or card
    ids), search, the Needs-you count, the command palette, WebSocket and SSE
    streams (on connect, reconnect and revocation), and MCP;
  - a hidden project returns **404**, and an insufficient role returns
    **403**, as today.
- **CFactory knows the user.** Cockpit requests carry the user's identity,
  and work items, cards, aggregates, costs, search, streams and MCP are
  filtered by project (#575).
- **Access is visible.** AIFactory has one effective-access page (users ×
  projects × roles, editable by admins) and a "my access" view. Every portal
  links to it from its account menu.
- **It is proven.** An E2E check uses a non-admin test user that has one
  visible and one hidden project **in the same tenant**. It fails on any
  list, search hit, count, stream event or deep link that exposes the hidden
  project.

## Affected users and systems

- **AIFactory:**
  - an effective-access read with roles;
  - the role in project responses;
  - the events WebSocket filter;
  - the search and count proxies;
  - the access page.
- **PFactory and TFactory:** visibility from AIFactory; the search and count
  proxies forward the user's identity.
- **CFactory:**
  - user identity on cockpit requests;
  - project authorization (#575) for work items, cards, aggregates, search,
    WebSocket, the live-agent proxy and MCP;
  - its project list.
- **The shared factory-ui:** the switcher shows roles.
- **Factory:** an E2E non-admin check (the Keycloak test user from #3882 G5,
  created by the owner).

## Constraints

- **AIFactory stays the single permission store** (#3857). No mirrored
  grants with their own logic.
- **Nobody's access changes.** Default-team inheritance and team isolation
  stay exactly as AIFactory has them today.
- **Keep 404 for hidden projects.** No existence oracle.
- **Service tokens and MCP keys** keep their scoped behaviour (#2182,
  `require_acw_*`).
- **Order:** after #3857's earlier phases. CFactory#575 lands before the
  CFactory card project picker (CFactory#574).
- **Agents never create Keycloak users or credentials.**

## Decisions (owner, 2026-11-25), revised after review

1. **Org members without a team grant keep today's model.** They inherit
   their org role on default-team projects and see nothing on other teams'
   projects. The earlier "viewer on every org project" recommendation would
   have widened team access and downgraded some members, so it was
   withdrawn.
2. **One access page in AIFactory,** linked from every portal.
3. **The other portals ask AIFactory** with the caller's identity and token
   scope, and cache briefly:
   - a revocation takes effect within 60 s;
   - when AIFactory is unreachable, they fail closed (no project list, 503)
     rather than fall back to local tables.
4. **CFactory#575 is delivered inside this work,** after CFactory gains user
   identity on cockpit requests.

## Open questions

1. **Who can change whose access.** Recommended: org admins and owners for
   their org; team admins for their own team only.
2. **What the access page edits.** Should an edit change team membership,
   which affects every project of that team, or grant access to one project?
   Recommended: team membership only, matching today's model, with the page
   showing which projects a change affects.
3. **Unmapped CFactory items.** Who sees CFactory work items or cards that do
   not map to any AIFactory project? Recommended: org admins and owners only.
