---
status: draft
issue: 3773
spec: spec/2026-11-17-3773-http-github-workitem.md
coders:
  1: lead   # moves tricky GraphQL logic without behaviour change
  2: lead   # REST members, small
reviewers:
  - codex
---

# Plan: complete HttpGitHubProvider as a WorkItemProvider (Factory#3773)

Approved decisions (spec `spec/2026-11-17-3773-http-github-workitem.md`): add `add_comment`, `close_issue`, `apply_labels`, `remove_labels`, `create_label`, `list_labels`, `assign_to_user` to `HttpGitHubProvider` over its token client; share the Copilot/GraphQL assignment algorithm with `GitHubProvider` through one helper; the VCS half stays absent. Services re-vendor the file with the Factory#3772 pin bump; no service change here.

## Steps

1. `shared/factory-github/providers/_github_json.py`: add `async def assign_actors(graphql, repo, issue_number, assignees)` holding the algorithm from `github_provider.py:431-534` verbatim (alias constants move with it). `github_provider.py`: `assign_to_user` calls it with `self._graphql`. → verify by the existing `GitHubProvider` assign tests passing unchanged.
   Traps: vendored byte-exact; no behaviour change; keep the silent no-op when Copilot is disabled.
2. `shared/factory-github/providers/http_github_provider.py`: add the seven members and a `_graphql` method (`POST` to `{base}/graphql`, or `{base minus /v3}/graphql` for a GHE `/api/v3` base), all through `_client()`; add the REST label/close/comment calls per the spec table. Update the module docstring (work-item seam now complete). Add tests to `tests/test_http_github_provider.py`. → verify by `pytest -q tests/test_http_github_provider.py tests/test_provider_credential_repr.py tests/test_provider_redirect_posture.py`, then the full hub suite, ruff and mypy.
   Traps: token never in repr or logs; `follow_redirects=False` stays; URL-quote label names; `isinstance(HttpGitHubProvider(...), WorkItemProvider)` must be true.
3. Open the PR to main with the artifacts; wait for green; the coordinator merges. Closing #3773 happens after merge.

## Tests

Full hub suite as in `.github/workflows/contracts.yml`; new tests assert method, path, body and `Authorization` header per member, 422-then-PATCH label create, 404-tolerant label removal, Copilot disabled no-op.

## Rollback

Revert the PR. Nothing outside the hub consumes the new members yet.
