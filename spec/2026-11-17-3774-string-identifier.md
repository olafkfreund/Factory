---
status: draft
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
   `scripts/gen_contracts.py` emits these and `--check` stays green.
2. **Hub protocol.** `IssueData.number` and `IssueComment.issue_number` become `str`;
   issue-only members take `str`. Members shared with PRs (`add_comment`-style, labels) take
   `str`, and PR callers pass `str(n)`; PR-only members (`fetch_pr`, `pr_number`) stay `int`.
3. **Providers.** Each converts at its own boundary through one helper
   `as_issue_int(ref) -> int` (raises `ValueError("issue identifier ... not numeric for <provider>")`):
   REST paths, GraphQL `Int!`, ADO work item id, GitLab IID. `group_bulk_comments` and
   `fanout_comments` key by `str`; the `int()` casts go away.
   Every provider parser (e.g. \`github_provider.py:724\`) and \`issue_number_from_url\`
   (\`_github_json.py:61\`) emits \`str(...)\` explicitly; a dataclass annotation alone normalises nothing.
4. **Services.** Annotations move to `str`; the 27 `int()` casts are removed or replaced by
   `as_issue_int` only where a numeric API needs it. Database columns holding the number are
   not retyped in this change: values are written as the decimal string into existing text or
   integer columns via a read-side `str()`; the Phase 2b audit lists any column that needs a
   migration and that goes in the service PR's plan.
5. **Order (no half-migrated type).** The vendor gates only check bytes, so order is by
   procedure. Hub PR widens the schema/contract to accept both and changes the protocol types
   while providers still emit the same values; the re-vendor of each service is bundled in that
   service's single PR with its caller migration (re-vendor and migration land together, never
   one without the other), and the four service PRs merge together. The hub contract's
   emit-as-string behaviour is switched on only by those PRs. Coordinator merges the four
   service PRs back to back after all are green.

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
