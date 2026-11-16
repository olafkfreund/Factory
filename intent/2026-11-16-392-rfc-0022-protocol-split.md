---
status: draft
issue: 392
author: olafkfreund
---

# Intent: RFC-0022 option C, first slice (hub protocol split)

## Problem

Factory#392 waited on the owner to pick option A, B or C for RFC-0022. The
owner delegated the choice on 2026-11-16 ("use the recommendations"). The
recorded recommendation (decision brief on #392) is **C: accept RFC-0022 with
Phase 2 (protocol split and caller audit) before Phase 1 (string identifier)**.

`GitProvider` is one 26-member protocol covering two jobs. Jira can implement
only the 12 work-item members, and no caller can say which half it needs.

## Proposed outcome

- RFC-0022 is `Accepted`, with a Decision section recording option C, the
  Phase 2-before-Phase 1 order, and the answer to the first open question.
- The hub defines `WorkItemProvider` and `CodeProvider` next to `GitProvider`,
  additively. Every existing provider satisfies both unchanged; a test proves
  it (GitHubProvider, GitLabProvider, AzureDevOpsProvider), and proves
  `HttpGitHubProvider` is a work-item provider only.
- Nothing changes at runtime, so no flag is needed: no service imports the new
  names until a re-vendor.
- The remaining slices are filed as sub-issues of #392.

## Affected users and systems

Hub `shared/factory-github/providers/protocol.py`, `providers/__init__.py`,
`docs/rfc/0022-work-item-and-code-seams.md` and one new hub test. The four
vendored copies are untouched until their own sub-issues.

## Constraints

- Vendoring exception (RFC section 8, "all four or none"): this slice adds
  names only and the services stay pinned to their current hub SHA, so no
  drift gate fires and no service sees a half-changed protocol. The re-vendor
  of all four is its own sub-issue and lands together.
- Additive only: `api_get`/`api_post` stay on `GitProvider` and the concrete
  classes until the caller audit (sub-issue) is done and all four copies move
  together (drift gates).
- Decisions recorded as "Decision (owner delegation 2026-11-16)".
- Jira credentials and a Jira Cloud test site stay with the owner (Phase 3).

## Open questions

Resolved by the delegation rule: may one object be both providers? Yes. It is
less configuration and the three existing providers already are both. A tenant
may still configure two connections.
