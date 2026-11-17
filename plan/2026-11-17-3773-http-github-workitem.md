---
status: approved
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

1. `shared/factory-github/providers/_github_json.py`: add `async def assign_actors(graphql, repo, issue_number, assignees)` holding the algorithm from `github_provider.py:431-534` verbatim (alias constants move with it). `github_provider.py`: `assign_to_user` calls it with `self._graphql`. BEFORE the extraction, port the regression cases from AIFactory `tests/test_git_providers_assign.py` (mixed aliases, Copilot disabled, empty assignees, unknown login) into a new hub test `tests/test_github_assign_to_user.py` against a fake `gh` client, and see them pass on the unextracted code; after the extraction they must pass unchanged. → verify by that new hub test file.
   Traps: vendored byte-exact; no behaviour change; keep the silent no-op when Copilot is disabled.
2. `shared/factory-github/providers/http_github_provider.py`: add the seven members and a `_graphql` method (`POST` to `{base}/graphql`, or `{base minus /v3}/graphql` for a GHE `/api/v3` base), all through `_client()`. Decisions carried from the spec: `close_issue` posts the optional comment first, then PATCHes `state=closed`, returns `True`, and returns `False` on `httpx.HTTPError`; `list_labels` pages with `per_page=100` until a short page; `remove_labels` issues one DELETE per label, URL-quoted, ignoring a 404; `create_label` POSTs and falls back to PATCH only when the response is 422 AND the error body's `errors[].code` is `already_exists` (any other 422 raises); `add_comment` returns the integer comment id. Update the module docstring (work-item seam now complete). Add tests to `tests/test_http_github_provider.py`. → verify by `pytest -q tests/test_http_github_provider.py tests/test_provider_credential_repr.py tests/test_provider_redirect_posture.py`, then the full hub suite, ruff and mypy.
   Traps: token never in repr or logs; `follow_redirects=False` stays; URL-quote label names; `isinstance(HttpGitHubProvider(...), WorkItemProvider)` must be true.
3. Open the PR to main with the artifacts; wait for green; the coordinator merges. Closing #3773 happens after merge.

## Deviations (recorded with the code that made them)

- Step 1: the moved algorithm is not strictly verbatim. A null issue node (`repository.issue: null`) used to raise `AttributeError`; it is now the no-op the surrounding code already intended (`if not assignable_id: return`). Covered by `test_missing_issue_node_skips_the_mutation` on both transports.
- Step 2: `HttpGitHubProvider._graphql` raises when the response carries an `errors` array, because GraphQL failures arrive as HTTP 200 (Codex review finding, confirmed); `gh api graphql` already fails on those. Covered by `test_a_graphql_error_in_a_200_response_is_raised_not_swallowed`.

## Tests

Full hub suite as in `.github/workflows/contracts.yml`; new tests assert method, path, body and `Authorization` header per member, 422-then-PATCH label create, 404-tolerant label removal, Copilot disabled no-op, a non-`already_exists` 422 raising, `list_labels` spanning two pages, `close_issue` returning `False` on a 5xx.

## Rollback

Revert the PR. Nothing outside the hub consumes the new members yet.
