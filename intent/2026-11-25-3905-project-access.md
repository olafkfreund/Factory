---
status: draft
issue: 3905
author: olafkfreund
epic: 3857
---

# Intent: show each user only their projects, with their role, in every portal

## Problem

A user who opens the project dropdown, or any project list, in AIFactory,
PFactory, TFactory or CFactory should see only the projects they may use.
Today each portal answers "which projects can this user see" differently,
and some don't answer it at all.

- **AIFactory** owns the project registry. `GET /api/projects` returns the
  projects owned by an org the caller belongs to (`routes/projects.py`
  `list_projects`, #319). The per-project roles from team grants (#2182,
  `project_authz`) gate actions such as terminals, but they don't filter the
  list.
- **PFactory and TFactory** have a `visible_project_ids` filter. It is used
  on their MCP and mcp-stdio routes. Whether their portal project lists and
  the switcher use it is not verified.
- **CFactory** has no project-level access control (CFactory#575 is open).
  Its cockpit shows every work item and project.
- **The shared switcher** (`shared/factory-ui/ProjectSwitcher.tsx`) shows
  whatever list the portal passes in. It has no idea of roles.
- **Nobody can see who has access to what.** No page lists the users,
  projects and roles, and users cannot see their own access.
- **The owner sees everything,** so none of this shows in daily use. It
  surfaces as soon as a second user or team is added.

The E2E campaign (#3882) also left many `e2e-…` test projects that crowd
the list. They are cleanup, not access, but they make the dropdown hard to
use.

## Proposed outcome

- **One answer.** "Which projects can this user see, and with which role"
  has a single source: AIFactory's registry and team grants. Every portal
  asks it.
- **Every list obeys it.** The switcher and every project list in all four
  portals show only those projects, each with the user's role (viewer,
  member, admin, owner).
- **The server enforces it.** Every project-scoped route in every portal
  refuses a project the user cannot see with 403. This applies to UI routes,
  APIs, MCP and deep links alike. Hiding a project in the dropdown is only
  for convenience.
- **Access is visible.**
  - Admins get a page that shows users × projects × roles and lets them
    change access.
  - Every user can see their own access.
- **It is proven.** An E2E check runs as a non-admin test user. It fails if
  any portal lists, or serves, a project that user has no access to.

## Affected users and systems

- **AIFactory:** the project registry, team grants, a "my projects" read,
  and the access admin page.
- **PFactory, TFactory, CFactory:** project lists, the switcher feed and
  route checks. For CFactory this means project authorization (#575).
- **The shared factory-ui switcher:** role display.
- **Factory:** the E2E harness, which gets a non-admin identity (the
  Keycloak test user from the campaign's G5).
- **People:** the owner, and any future team members or customers.

## Constraints

- **AIFactory stays the registry and access owner** (#3857 decision). No
  second permission store is created in the other portals.
- **Existing grants keep working.** No current user loses access to a
  project they use today. The owner stays owner everywhere.
- **Service tokens and MCP keys** keep their scoped behaviour (#2182,
  `require_acw_*`).
- **Order:** this lands after #3857's phases already in progress (project in
  the URL, AIFactory registry), and before the CFactory card project picker
  (CFactory#574).
- **Agents** never create Keycloak users or credentials. The owner creates
  the test user.

## Open questions

1. **Which roles a list shows.** Should a user with only org membership and
   no team grant see the org's projects as viewer, or nothing? Recommended:
   viewer, which keeps today's behaviour for org members.
2. **Where the admin page lives.** Is the access page in AIFactory settings
   enough, or should every portal link to it from its account menu?
   Recommended: one page in AIFactory, linked from every portal.
3. **How the other portals get the list.** Should they call AIFactory per
   request (with a short cache), or mirror grants into their own database?
   Recommended: call it with a short cache. Mirroring creates a second
   store.
4. **Scope of CFactory#575.** Should CFactory's project authorization be
   delivered inside this work, or as its own track first? Recommended:
   inside this work, because the switcher is meaningless in CFactory without
   it.
