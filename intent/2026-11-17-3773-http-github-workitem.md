---
status: draft
issue: 3773
author: olafkfreund
---

# Intent: RFC-0022 Phase 2d: complete HttpGitHubProvider as a WorkItemProvider

## Problem

`HttpGitHubProvider` implements only part of the work-item protocol. It lacks `close_issue`, `add_comment`, `assign_to_user`, `apply_labels`, `remove_labels`, `create_label` and `list_labels`, so it is not a `WorkItemProvider` and a hosted caller holding a tenant token cannot do what the gh-CLI provider can.

## Proposed outcome

`HttpGitHubProvider` satisfies `WorkItemProvider` over HTTP (REST, plus the GraphQL endpoint for the Copilot assignment alias) with an explicit token, with tests for each new member. The VCS half stays deliberately unimplemented.

## Affected users and systems

Factory hub `shared/factory-github/providers/http_github_provider.py`; every service re-vendors it with the next pin bump (the drift gates compare it byte for byte).

## Constraints

Token only, never ambient `gh` auth (Factory#370). `follow_redirects=False` and `repr=False` on the token stay. Same semantics as `GitHubProvider`, including the Copilot alias in `assign_to_user`. No new dependencies.

## Open questions

None. The issue says the members are optional until a caller needs them; the owner delegation says implement them because Phase 2b callers may need them.
