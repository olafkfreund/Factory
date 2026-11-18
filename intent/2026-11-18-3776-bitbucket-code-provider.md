---
status: approved
issue: 3776
author: olafkfreund
---

# Intent: Bitbucket as a code provider (RFC-0022 Phase 5)

## Problem

The fleet reaches GitHub, GitLab and Azure DevOps for code. Bitbucket Cloud is
a common home for a tenant's repositories and the fleet cannot talk to it:
`get_provider("bitbucket", ...)` raises `NotImplementedError` pointing at a
stub file that does not exist. RFC-0022 Phases 1 and 2 are merged (the
`CodeProvider` / `WorkItemProvider` split, no raw HTTP members, string work-item
identifiers), so a code-only provider is now expressible without stubbing the
work-item half.

## Proposed outcome

- A `BitbucketProvider` in the hub `factory-github` package implements
  `CodeProvider` only (Bitbucket Cloud REST 2.0): repository info and default
  branch, pull requests (get, list, diff, close/decline, merge with strategies),
  PR comments (`fetch_pr_comments`), posting a review, a permission check, and
  `enable_auto_merge` (a required `CodeProvider` member) raising a clear
  `NotImplementedError` because Bitbucket Cloud has no such API.
- The factory hands it out through a new `get_code_provider()` typed
  `CodeProvider`. `get_provider()` stays typed `GitProvider` and never returns
  Bitbucket, so no existing caller is promised work-item methods it lacks.
- It authenticates with the existing opaque credential kind (a Bitbucket Cloud
  app password or repository access token). No credential-store change.
- The provider kind is registered but disabled by default behind a feature flag,
  so nothing changes for any tenant until the owner has a Bitbucket workspace to
  test against.
- Tests use a mock transport with recorded-shape fixtures and never contact
  bitbucket.org.
- A provider docs page exists and RFC-0022 records Phase 5 as implemented
  (flag-off).
- The new file and the factory change are re-vendored byte-for-byte into
  AIFactory, PFactory, TFactory and CFactory.

## Affected users and systems

Hub `shared/factory-github/providers/` and its four vendored copies; the hub
drift checker's canonical file list; docs. No tenant is affected while the flag
is off. Coordinates with rfc22-jira (same hub package, a different new file) and
rfc22-mixed-tenant (CFactory).

## Constraints

- Additive: no change to `protocol.py`, so the four copies cannot drift on the
  protocol and the re-vendor PRs need no pin ordering beyond "hub merge first".
- Never log or repr the credential or the Authorization header.
- The credential must not leave the configured host: no cross-origin redirect or
  `next` link is followed with it (Factory#825 posture).
- No Bitbucket issues (work items), no commit-status/checks API beyond what a
  `CodeProvider` member needs.
- No contact with bitbucket.org from tests or CI.

## Open questions

None. Decisions taken under the owner delegation of 2026-11-18 are in the spec.
