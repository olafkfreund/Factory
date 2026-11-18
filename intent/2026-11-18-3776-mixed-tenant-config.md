---
status: draft
issue: 3776
author: olafkfreund
---

# Intent: mixed tenant configuration (RFC-0022 Phase 4)

## Problem
A CFactory git connection names one provider, and that one provider serves both
jobs: work items (issues, comments, import) and code. A tenant that plans in one
system and keeps code in another (for example Jira for planning, GitHub for
code, or GitLab issues with GitHub code) cannot express it. RFC-0022 Phases 1-2
(string identifier, WorkItemProvider/CodeProvider split) are merged; Phase 4,
the tenant configuration half, is not.

## Proposed outcome
A connection can name a work-item side distinct from its code side. A
connection with nothing configured for the work-item side behaves exactly as
today, so no existing row needs a migration to keep working. Every CFactory
path that reads or writes issues uses the work-item side, and the code side is
used for repository verification and the AIFactory build project. The
work-item side has its own project address per repository, so issue
creation, import and sync consistently address it while builds keep the code
repository. The work-item reference must belong to the same tenant, and a
configured work-item target that disappears fails loudly (deleting a referenced
connection is refused); it never silently falls back to the code provider. The
connection API and OpenAPI file expose the new field additively. Azure DevOps
(Boards and Repos) stays one provider.

## Affected users and systems
olafkfreund/CFactory (backend, migration, OpenAPI, connection panel); hub docs
in Factory (these artifacts, RFC-0022 section 6 Phase 4 status). Coordinates
with team rfc22-jira (structured credentials, `jira` kind) and rfc22-bitbucket
(Phase 5, code-only kind).

## Constraints
- Owner decision already recorded: one provider object MAY implement both
  protocols (RFC-0022 Decision, open question 1). Single-provider connections
  are unchanged byte for byte in behaviour.
- Migration reversible and tested. API change additive only.
- Credentials never cross: each side authenticates with its own connection's
  credential and nothing is read from the other.
- Out of scope: widening CFactory's numeric `IssueRef` to string keys
  (`PROJ-123`); that lands with the Jira provider (rfc22-jira). Until then only
  kinds with numeric issues can be a work-item side.
- No Jira code here (flag owned by rfc22-jira); the UI selector is hidden until
  more than one work-item kind is enabled.
- No live cluster or deploy changes.

## Open questions
None. Decision taken by owner delegation 2026-11-18: reference a second
connection for the work-item side (recorded in the spec).
