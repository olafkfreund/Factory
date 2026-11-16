---
status: draft
issue: 3702
spec: spec/2026-11-16-3702-per-org-cockpit-tokens.md
coders:
  1: you (lead)
  2: you (lead)
reviewers:
  - codex
---

# Plan: per-org upstream tokens in CFactory

Approved decisions: one extra `/ws/events` socket per org-bound key, in
CFactory only; env `CFACTORY_{PFACTORY,AIFACTORY,TFACTORY}_ORG_TOKENS`
(comma-separated), default empty = today's behaviour; `repr=False`; no
cross-socket dedupe (org-bound keys never overlap); extras must be org-bound;
no change to the three upstream factories. Repo: olafkfreund/CFactory, base
`dev`. Two small edits, so the lead implements (no handoff).

## Steps

1. `apps/backend/cfactory/config.py` near line 93 and `token_for` (~415):
   add three `str | None` fields (`repr=False`) and
   `extra_tokens_for(service) -> list[str]` (split on `,`, strip, drop blanks,
   de-duplicate preserving order, remove `token_for(service)`).
   Verify: unit test in `tests/test_upstream_ws.py`.
2. `apps/backend/cfactory/upstream_ws.py` `start_subscribers` (~198): after the
   primary task, one extra `subscribe(...)` task per extra token with
   `{"Authorization": f"Bearer {tok}"}`. Add the env rows to
   `docs/dev/environment-reference.md`.
   Verify: tests below.
   Traps: never log a token; `just lint` (ruff, banned constructs).

## Tests

`just test tests/test_upstream_ws.py` and `just lint`: defaults give one task
per service; extras give N+1 tasks, distinct Bearer headers, same URL; parser
dedupes and drops the primary and blanks.

## Rollback

Unset the env vars (inert) or revert the PR.
