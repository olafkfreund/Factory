---
status: draft
issue: 3773
intent: intent/2026-11-17-3773-http-github-workitem.md
---

# Spec: HttpGitHubProvider as a complete WorkItemProvider (RFC-0022 Phase 2d)

## Design

Add the seven missing members to `shared/factory-github/providers/http_github_provider.py`, using the existing `_client()` (token header, `follow_redirects=False`, timeout) for every request:

| Member | Request |
| ------ | ------- |
| `add_comment(n, body)` | `POST /repos/{repo}/issues/{n}/comments`, returns the comment `id` (int) |
| `close_issue(n, comment)` | optional `add_comment`, then `PATCH /repos/{repo}/issues/{n}` `{"state":"closed"}`; returns `True`, and `False` on an HTTP or transport error, matching `GitHubProvider.close_issue` |
| `apply_labels(n, labels)` | `POST /repos/{repo}/issues/{n}/labels` |
| `remove_labels(n, labels)` | `DELETE /repos/{repo}/issues/{n}/labels/{name}` per label (name URL-quoted); a 404 means already absent and is ignored |
| `create_label(label)` | `POST /repos/{repo}/labels`; on 422 `already_exists` `PATCH /repos/{repo}/labels/{name}` (the gh `--force` semantics) |
| `list_labels()` | paged `GET /repos/{repo}/labels` to completion |
| `assign_to_user(n, assignees)` | the same GraphQL algorithm as `GitHubProvider` (suggested actors, Copilot alias, `replaceActorsForAssignable`) over `POST {graphql}` |

The assignment algorithm moves from `GitHubProvider.assign_to_user` into one helper in `providers/_github_json.py` that takes an async `graphql(query, variables)` callable; both providers call it. That keeps one copy of 80 lines (the hub has a duplication ratchet) and guarantees the Copilot semantics do not drift between transports. The GraphQL URL is `{base}/graphql` for `https://api.github.com` and `{base minus /v3}/graphql` for a GitHub Enterprise `/api/v3` base.

Unit tests in `tests/test_http_github_provider.py` use `httpx.MockTransport` and assert the method, path, body and the token header for each member, the 422-then-PATCH label path, the idempotent 404 removal, the Copilot no-op when the agent is disabled, and that `isinstance(provider, WorkItemProvider)` now holds.

## Alternatives rejected

- **Copy the GraphQL block into the HTTP provider.** Two drifting copies and a clone-ratchet hit.
- **Raise `NotImplementedError` for `assign_to_user`.** Hosted callers are the ones that assign Copilot; Phase 2b callers may need it.
- **Implement the VCS half too.** Out of scope (Factory#370 explains why it is deliberately absent).

## Risks

- Moving the assignment code touches `GitHubProvider`; its existing tests must still pass unchanged.
- The file is vendored byte-exact in four repos; the service re-vendor follows with the next pin bump (Factory#3772 carries it).
- Swallowing errors in `close_issue` mirrors the gh provider but hides failures; documented, not changed.

## Verification

Hub suite (`pytest tests/ shared/factory-common/tests/ scripts/benchmarks/`), ruff and mypy as the code-quality workflow runs them, and the new tests above.
