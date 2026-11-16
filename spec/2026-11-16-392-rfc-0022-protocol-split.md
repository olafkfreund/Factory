---
status: draft
issue: 392
intent: intent/2026-11-16-392-rfc-0022-protocol-split.md
---

# Spec: hub WorkItemProvider and CodeProvider protocols

## Design

In `shared/factory-github/providers/protocol.py` add two
`@runtime_checkable` Protocols:

- `WorkItemProvider`: `provider_type` plus the 12 work-item members
  (`fetch_issue`, `fetch_issues`, `create_issue`, `close_issue`,
  `add_comment`, `fetch_comments`, `fetch_comments_bulk`,
  `assign_to_user`, `apply_labels`, `remove_labels`, `create_label`,
  `list_labels`).
- `CodeProvider`: `provider_type`, `repo` and the 9 code members
  (`fetch_pr`, `fetch_prs`, `fetch_pr_diff`, `post_review`, `merge_pr`,
  `close_pr`, `enable_auto_merge`, `get_default_branch`,
  `check_permissions`, plus `get_repository_info`).
- Neither has `api_get`/`api_post` (RFC section 2.2). `GitProvider` is left
  as is, so no caller breaks. Both are exported from `providers/__init__.py`.
- Identifiers stay `int` in this slice (Phase 1 follows Phase 2).
- RFC-0022: Status Proposed to Accepted, plus a Decision section.

Method bodies are not repeated: the protocols list signatures only, copied
from `GitProvider`. To avoid drift between three copies, the test asserts
`GitProvider` members equal the union of the two plus `api_get`/`api_post`.

## Alternatives rejected

- Option A (identifier first): about 186 annotations and 27 casts migrate
  before any consumer exists.
- Option B (leave RFC Proposed): a four-repo protocol change would rest on an
  unaccepted design.
- Make `GitProvider` inherit from the two: Protocol inheritance would remove
  the duplicate bodies, but it changes the vendored shape and is a re-vendor
  decision for the audit sub-issue.
- Removing `api_get` now: 18 call sites would break (audit not done).

## Risks

Low: new names only. Signature copies could drift; the union test guards that.

## Verification

`pytest tests/test_provider_protocol_split.py tests/test_provider_comments.py`;
ruff and mypy as in the repo CI.
