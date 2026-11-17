---
status: approved
issue: 3774
intent: intent/2026-11-17-3774-string-identifier.md
---

# Spec: string issue identifier

## Design

Canonical type: `IssueRef = str` (a decimal string for GitHub/GitLab/ADO, a key such as
`PROJ-123` for Jira). No integer is synthesised.

1. **Contract.** `task-contract.schema.json` `provenance.issue_number` becomes
   `{"type": ["integer", "string"]}` (accept both). `factory_contracts`:
   `issue_number: str | None` with a `before` validator that turns an int into its decimal
   string. TS: `issue_number?: string | number | null` (readers normalise with `String()`).
   OpenAPI/AsyncAPI/MCP docs and the `product-catalogs` copies get the same `oneOf`.
   `scripts/gen_contracts.py` emits the Python and TS outputs only (it does not touch API docs);
   the OpenAPI/AsyncAPI/MCP/catalog files are edited by hand in the same PR.
2. **Hub protocol.** `IssueData.number` and `IssueComment.issue_number` become `str`;
   issue-only members take `str`. Members shared with PRs (`add_comment`-style, labels) take
   `str`, and PR callers pass `str(n)`; PR-only members (`fetch_pr`, `pr_number`) stay `int`.
3. **Providers.** Each converts at its own boundary through one helper
   `as_issue_int(ref) -> int` (raises `ValueError("issue identifier ... not numeric for <provider>")`):
   REST paths, GraphQL `Int!`, ADO work item id, GitLab IID. `group_bulk_comments` and
   `fanout_comments` key by `str`; the `int()` casts go away.
   Every provider parser (e.g. \`github_provider.py:724\`) and \`issue_number_from_url\`
   (\`_github_json.py:61\`) emits \`str(...)\` explicitly; a dataclass annotation alone normalises nothing.
   Every provider parser (e.g. `github_provider.py:724`) and `issue_number_from_url`
   (`_github_json.py:61`) emits `str(...)` explicitly; a dataclass annotation alone normalises nothing.
4. **Services.** Annotations move to `str`; the 27 `int()` casts are removed or replaced by
   `as_issue_int` only where a numeric API needs it. Persistent columns: a column holding an issue identifier as an integer cannot store
   `PROJ-123`; the Phase 2b audit lists them and each service PR carries a write-side migration
   to text (decimal values preserved) before it accepts a non-numeric key. Until then that
   service rejects a non-numeric key at its edge.
5. **Order (no half-migrated type).** The vendor gates check bytes only, so order is by
   procedure. The hub PR widens schema/contract/protocol types and keeps emitting today's
   values. Each service's re-vendor and its caller migration are ONE service PR (never one
   without the other); the four service PRs merge back to back once all are green, and only
   they switch emission to the string form.

## Alternatives rejected

- Integer plus a separate `external_key` string: two sources of truth, the board could show an
  issue it cannot update.
- Synthesised integer for Jira: cannot round-trip (RFC-0022).
- Widen only schema and protocol: a half-migrated type.

## Risks

- A service that compares `issue.number == 5` silently becomes false for `"5"`; the 2b audit
  and a grep-gate test in each service catch int comparisons.
- Correlation key drift: `origin_key` already returns `str`; a test pins `"o/r#5"` for both `5` and `"5"`.
- Old readers reject a string on the wire: producers flip last.

## Verification

Hub: `python scripts/gen_contracts.py --check`, schema validates `5` and `"PROJ-1"`, provider
tests with string ids and a non-numeric id on GitHub (clear error), correlation-key parity test.
Each service: its CI (ruff, mypy, pytest) and drift gate green.
