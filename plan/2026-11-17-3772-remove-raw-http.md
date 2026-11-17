---
status: approved
issue: 3772
spec: spec/2026-11-17-3772-remove-raw-http.md
coders:
  1: lead   # two-member deletion plus tests
  2: lead   # byte-copy re-vendor in four repos, checked by the drift gate
reviewers:
  - codex
---

# Plan: remove api_get/api_post from the provider protocols (Factory#3772)

Approved decisions (spec `spec/2026-11-17-3772-remove-raw-http.md`): `GitProvider` loses `api_get`/`api_post` and becomes `WorkItemProvider` + `CodeProvider`; concrete providers and `GHClient` keep them; the four services re-vendor together after every Factory#3771 PR is merged.

## Steps

1. Hub, branch `refactor/3772-remove-raw-http` (worktree Factory-3772): `shared/factory-github/providers/protocol.py`: delete the two members and fix the `GitProvider` docstring; update `tests/test_provider_protocol_split.py` and any other test that lists the member set; add a test that neither protocol has `api_get`/`api_post` while `GitHubProvider` still does. → verify by the full hub suite, ruff, mypy.
   Traps: rebase on main after Factory#3771 and #3773 merge (they touch `protocol.py` and the providers); do not touch concrete providers.
2. Open the hub PR now (artifacts + step 1); it is mergeable once the four Factory#3771 PRs (AIFactory, PFactory, TFactory, CFactory) are merged. The services are unaffected at runtime because they pin an earlier SHA.
3. After step 2 merges (and the four Factory#3771 PRs are merged), per service (AIFactory, PFactory, TFactory, CFactory; base dev; branch `refactor/3772-re-vendor-protocol`): copy the canonical files at the new hub SHA (this also carries Factory#3773), bump `HUB_SHA`, run mypy and `grep -rn "provider.api_get\|provider.api_post"` for stragglers. → verify by the drift gate and each repo's CI commands. Traps as in the Factory#3771 plan (AIFactory ruff alias sorting, autonomy matrix, vendored files byte-checked).
4. Open the four PRs linking the artifacts; wait for green on the exact head SHA; the coordinator merges all four together.

## Tests

Hub suite; per service the drift gate, mypy and the service test suite.

## Rollback

Revert the service re-vendors, then the hub PR. Concrete providers kept their methods throughout, so runtime behaviour is unchanged by either direction.
