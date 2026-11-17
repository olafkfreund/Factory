---
status: approved
issue: 392
spec: spec/2026-11-16-392-rfc-0022-protocol-split.md
coders:
  1: you   # small additive edit, below the coder handoff threshold
  2: you
  3: you
reviewers:
  - codex  # read-only final review
---

# Plan: hub WorkItemProvider and CodeProvider protocols

Approved decisions carried over from the spec: option C (Phase 2 before Phase 1);
additive hub-only change, `GitProvider` and `api_get`/`api_post` untouched;
vendored copies not touched (re-vendor is a sub-issue); one object may be both
providers; identifiers stay `int`; `HttpGitHubProvider` satisfies neither
protocol today and the RFC's claim is corrected.

## Steps

1. `shared/factory-github/providers/protocol.py` (after `GitProvider`, EOF) and
   `providers/__init__.py`: add `WorkItemProvider` (provider_type + 12 work-item
   members) and `CodeProvider` (provider_type, repo, get_repository_info + 9
   code members) as `@runtime_checkable` Protocols with signatures copied from
   `GitProvider`; export both → verify by import.
   Traps: ruff rules in standards/ruff.toml; protocol.py is vendored, so keep it
   self-contained.
2. `tests/test_provider_protocol_split.py`: three full providers are instances
   of both; HttpGitHubProvider is not a CodeProvider; signature equality vs
   `GitProvider`; member union equals GitProvider members minus api_get/api_post
   → verify by pytest.
   Traps: use the `conftest.py` sys.path bootstrap, no pytest-asyncio.
3. `docs/rfc/0022-work-item-and-code-seams.md`: Status Accepted; add a Decision
   section (option C, order, same-object answer, Phase 2 sub-slices); correct
   the HttpGitHubProvider claim in 2.1 → verify by reading; then open sub-issues.

## Deviations

- Step 1: `GitProvider` now inherits `WorkItemProvider` and `CodeProvider` and keeps
  only `api_get`/`api_post`, instead of three copies of the signatures. Reason:
  copies add jscpd clones (the budget ratchet) and can drift. Member set and
  `isinstance` behaviour of `GitProvider` are unchanged.
- Step 2: signature comparison replaced by single-definition (no copies to compare).

## Tests

`pytest tests/test_provider_protocol_split.py tests/test_provider_comments.py
tests/test_http_github_provider.py`; `ruff format --check scripts/ tests/`; `python scripts/ratchet_lint.py --base origin/main --package scripts,tests`
(ruff, then `--tool mypy`). The provider files are outside those ratchets, so also run
`ruff check` and `ruff format --check` directly on `shared/factory-github/providers/protocol.py`
and `__init__.py`.

## Rollback

Revert the PR; nothing imports the new names.
