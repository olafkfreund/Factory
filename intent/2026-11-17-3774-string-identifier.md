---
status: draft
issue: 3774
author: olafkfreund
---

# Intent: RFC-0022 Phase 1, string issue identifier across contract and providers

## Problem

Every work-item identifier in the fleet is typed `int`. A Jira key (`PROJ-123`) cannot be
represented, so a Jira provider (#3775) cannot be built without synthesising an integer,
which RFC-0022 rejects because it cannot round-trip (the board could show an issue it
cannot update). Correlation keys are already strings (`origin_key`, `synthetic_key`), so
the dangerous layer is safe; the work is the type surface around it.

## Proposed outcome

The work-item identifier is a string everywhere it crosses a service boundary, and an
all-digit string behaves exactly like today's integer: same correlation keys and same
stored meaning for existing GitHub/GitLab/ADO tenants. The wire form changes from a JSON
integer to a decimal string; the schema accepts both during the transition, so every consumer
is re-vendored before any producer emits the string. No service ships a
half-migrated type: hub first, four re-vendors, then four service PRs.

## Contract inventory (hub, Factory main)

- `apis/task-contract.schema.json:26` `provenance.issue_number` integer
- `shared/factory-contracts/python/factory_contracts/__init__.py:58` `CorrelationBlock.issue_number: int | None`
- `shared/factory-contracts/ts/factory-contracts.ts:20` `issue_number?: number | null`
- `scripts/gen_contracts.py` (generator; output is committed, `--check` gates drift)
- `apis/aifactory.openapi.yaml:222,262`, `apis/cfactory.openapi.yaml:253`,
  `apis/completion-events.asyncapi.yaml:179`, `apis/aifactory.mcp.md:14`, and the
  `product-catalogs/*` copies of the same
- `shared/factory-github/providers/protocol.py`: `IssueData.number`, `IssueComment.issue_number`,
  and the issue-number parameters of the work-item members (PR numbers stay `int`)
- Provider implementations and `_github_json.py` (`issue_number_from_url`, `parse_comment`),
  `gh_client.py`; the `int(...)` casts in `fetch_comments_bulk` and `fanout_comments`
  (`protocol.py:173-186`), and the integer-keyed `group_bulk_comments`
  (`_github_json.py:147-175`), which must key by the string form or it silently drops comments
- Services (measured 2026-11-14): about 186 `issue_number: int` annotations and 27 `int()`
  casts (AIFactory 94/11, PFactory 34/6, TFactory 33/6, CFactory 25/4). The Phase 2b audit
  (#3771) refines which of these are issue identifiers and which are PR numbers.

## Affected users and systems

Hub contract and provider package, the four vendored copies, AIFactory, PFactory, TFactory,
CFactory. Existing GitHub/GitLab/ADO tenants must see no change.

## Constraints

- Decimal-compatible: `"123"` and `123` both accepted on input; output of an existing integer
  issue is its decimal string; correlation keys byte-identical. Providers that need an integer
  (GitHub GraphQL `Int!` at `github_provider.py:511-517`, REST paths) convert at their own
  boundary and reject a non-numeric key with a clear error, never a bare `ValueError`.
- PR numbers and MR IIDs remain integers; only the work-item identifier widens. Members shared
  between issues and PRs (`protocol.py:371,477,490`) take the wider type and the PR callers
  pass `str(n)`, decided in the spec.
- Four vendored `protocol.py` copies behind pinned-SHA drift gates: land in all four or none.
- Starts only after the Phase 2b/2c PRs (#3771, #3772) merge, because the audit decides the
  real call sites and 2c rewrites the protocol this change edits.

## Open questions

None. RFC-0022 option C is accepted; the identifier is a string, and no integer is synthesised.
