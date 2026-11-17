---
status: draft
issue: 3772
intent: intent/2026-11-17-3772-remove-raw-http.md
---

# Spec: remove api_get/api_post from the provider protocols (RFC-0022 Phase 2c)

## Design

- `protocol.py`: delete `api_get` and `api_post` from `GitProvider`. `GitProvider` becomes `WorkItemProvider` plus `CodeProvider` with no body of its own; update its docstring.
- The concrete providers (`GitHubProvider`, `GitLabProvider`, `AzureDevOpsProvider`) and `GHClient` keep their `api_get`/`api_post` (RFC-0022 section 2.2: GitHub-specific callers hold a GitHub-specific type). `HttpGitHubProvider` never had them.
- Hub tests that assert the protocol member set are updated to the smaller set; one new test asserts `api_get`/`api_post` are in neither protocol.
- Services (separate PRs, after the Factory#3771 PRs are merged): re-vendor the canonical files from the hub commit carrying this change plus Factory#3773 and #3771, bump `HUB_SHA`. AIFactory, PFactory, TFactory, CFactory in one set.
- Each service's own test double (`runners/github/testing.py`) drops `api_get`/`api_post` only if nothing non-protocol still calls them (the AIFactory `permissions.py` calls them on `GHClient`, which stays).

## Alternatives rejected

- **Delete the methods from the concrete classes as well.** Breaks GitHub-specific callers the RFC says must keep working (AIFactory `permissions.py` uses `GHClient.api_get`).
- **Merge with Factory#3771 in one PR.** The owner ordered 2c after every 2b site is merged.

## Risks

- A service that still calls `provider.api_get` through a protocol-typed variable fails mypy after re-vendor, not at runtime (the concrete classes keep the method). Factory#3771 removes the known sites; the re-vendor PRs run mypy and grep for stragglers.
- Re-vendors must land as one set so the four copies agree.

## Verification

Hub suite plus ruff/mypy; per service, drift gate green on the exact head SHA, service tests, and `grep -rn "\.api_get\|\.api_post"` showing only concrete-provider and `GHClient` uses.
