---
status: draft
issue: 3774
spec: spec/2026-11-17-3774-string-identifier.md
coders:
  1: you
  2: you
  3: you
  4: you
  5: you
  6: you
reviewers:
  - codex
---

# Plan: string issue identifier (RFC-0022 Phase 1)

Decisions carried from the approved spec: `IssueRef = str` (decimal string for
GitHub/GitLab/ADO, a key like `PROJ-123` for Jira); no integer is synthesised.
The schema accepts integer or string. `factory_contracts` stores `str | None`
and a `before` validator turns an int into its decimal string. TS accepts
`string | number`. Hub protocol: `IssueData.number` and `IssueComment.issue_number`
are `str`; issue-only and shared issue/PR members take `str`; PR-only members
(`fetch_pr`, `pr_number`) stay `int`. Each provider converts at its own boundary
through one helper `as_issue_int(ref)` that raises `ValueError` with a clear
message for a non-numeric key. `group_bulk_comments` and `fanout_comments` key by
`str` and the `int()` casts go away. Every parser emits `str(...)` explicitly.
Correlation keys stay byte-identical (`"o/r#5"` for `5` and `"5"`).
Column migrations and service emission are per-service decisions in the service
PRs. Order: hub PR first (types widen, nothing is emitted as a string on the wire
by the hub), then ONE PR per service containing both re-vendor and caller
migration; the four merge back to back.

Phase A (hub, steps 1-5) starts now. Phase B (steps 6) waits for the Phase 2b/2c
service PRs (#3771, #3772) to merge: if they have not merged, the hub PR and the
service PRs are opened as drafts and the work is reported blocked rather than
leaving a partial migration mergeable.

Implementers: the lead does every step (they are small and tightly coupled);
Codex reviews the artifacts and the diff.

## Steps

1. Contract. `apis/task-contract.schema.json:26` `issue_number` becomes
   `{"type": ["integer", "string"]}`; `scripts/gen_contracts.py` template
   (`CorrelationBlock.issue_number: str | None` with a `field_validator(..., mode="before")`
   turning int into `str`, and TS `string | number | null`), then regenerate
   `shared/factory-contracts/{python,ts}` → `python scripts/gen_contracts.py --check`.
   Traps: output is committed; never hand-edit generated files.
2. API docs. `apis/aifactory.openapi.yaml:222,262`, `apis/cfactory.openapi.yaml:253`,
   `apis/completion-events.asyncapi.yaml:179`, `apis/aifactory.mcp.md:14`, and the
   `product-catalogs/{AIFactory,CFactory}/apis/*` copies: `oneOf` integer/string.
   → verify by grep that no `issue_number` is left `type: integer`; the catalog
   copies match their `apis/` source (check any existing sync test).
3. Protocol. `shared/factory-github/providers/protocol.py`: `IssueRef = str`,
   `as_issue_int`, `IssueData.number`, `IssueComment.issue_number`, issue and
   shared members, `fanout_comments` and `fetch_comments_bulk` keyed by `str`.
   `_github_json.py`: `issue_number_from_url` returns `str | None`, `parse_comment`
   and `group_bulk_comments` use `str`. → `ruff` and `mypy` on `shared/factory-github`.
4. Providers. `github_provider.py`, `gitlab_provider.py`, `azure_devops_provider.py`,
   `http_github_provider.py`, `gh_client.py`: convert with `as_issue_int` at the
   REST/GraphQL/WIQL boundary; parsers emit `str(...)`. PR-only paths keep `int`.
   → `pytest tests/test_provider_comments.py tests/test_http_github_provider.py
   tests/test_github_assign_to_user.py`.
   Traps: the GraphQL `Int!` call at `github_provider.py:511-517`; a PR caller
   of a shared member passes `str(n)`.
5. Tests. Update the provider tests for `str` ids, add: schema validates `5`
   and `"PROJ-1"`; `CorrelationBlock(issue_number=5).issue_number == "5"`; correlation
   key parity (`5` and `"5"`); non-numeric id on GitHub raises a clear `ValueError`;
   `group_bulk_comments` keeps comments for string keys. Then
   `python scripts/check_factory_github_drift.py` expectations and the pinned SHA
   in the hub's own drift test are updated if the gate pins bytes.
   → `pytest tests/ shared/factory-common/tests/`.
6. Services (Phase B, after #3771/#3772 merge). In each of AIFactory, PFactory,
   TFactory, CFactory (base dev): re-vendor `factory_github` and
   `factory_contracts`, move issue annotations to `str`, drop or replace the
   `int()` casts, update the integer-keyed comment maps, and add the text-column
   write-side migration where the 2b audit lists an integer issue column; one PR
   per repo → each repo's own CI (ruff, mypy, pytest, drift gate).
   Traps: AIFactory autonomy matrix is regenerated, never hand-merged; use plain
   names in parenthesised imports; vendored files are byte-checked against the hub.

## Tests

`python scripts/gen_contracts.py --check`; `pytest tests/ shared/factory-common/tests/`;
`ruff check` and `mypy` as the hub CI does. Each service: its own CI.

## Rollback

Hub: revert the PR (types widen only, no wire emission changes). Services: revert
the service PR; a text column keeps decimal values so a revert needs no data fix.
