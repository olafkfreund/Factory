---
status: approved
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
   Traps: never log a token. `just lint` is only statix/deadnix; run `ruff check` and `ruff format --check` separately. Tests record calls in a list (patch `upstream_ws.subscribe` with an async recorder, `await asyncio.gather(*tasks)`), not a dict, which would overwrite same-service calls.

3. (Deviation, found in Codex final review.) `progress.py` `poll_progress_once`
   and `routes_events.py` `/api/refresh`: the REST poll sees only the primary
   org, so `reconcile_snapshot` would blank running stages that extra-org
   sockets delivered. Skip `reconcile_snapshot` for a service that has extra
   tokens. Cost: ghost running stages for that service clear only on a
   terminal event, not by poll. Polling per extra token is the follow-up.

## Tests

`just test tests/test_upstream_ws.py` and `just lint`: defaults give one task
per service; extras give N+1 tasks, distinct Bearer headers, same URL; parser
dedupes and drops the primary and blanks.

## Rollback

Unset the env vars (inert) or revert the PR.
