---
status: draft
issue: 312
spec: spec/2026-11-18-312-ws-review-followups.md
coders:
  A2: codex   # TFactory: small tricky logic (owner is_active check, events/auth logs, tests)
  C1: codex   # CFactory: contained edits (hint, test, two docs)
  A1: you     # AIFactory: lead edits (reference implementation of the events change)
  P1: you     # PFactory: mirrors AIFactory
reviewers:
  - codex     # final `codex review --base origin/dev` per repo
---

# Plan: scoped cockpit keys, WS review follow-ups

Approved decisions (spec): see `spec/2026-11-18-312-ws-review-followups.md`, all 8 items. Summary:
- `_load_org_ids` -> bool (True on success, empty membership, and no-user early return; False only on exception). WARNING with exception class only. Key principals (`api_key_id`) closed with 1011 on False; human/legacy sockets stay open. Both lookups inside the cleanup `try/finally`.
- `_ws_acw_principal`: WARNING `type(exc).__name__`, return None, keep 4001.
- CFactory: hint names `CFACTORY_<SERVICE>_TOKEN` + `CFACTORY_UPSTREAM_TOKEN` fallback; `_auth_headers` test; two techdocs corrected.
- TFactory `_lookup_by_digest`: owner `User` active check (AIFactory shape).
- `?token=`: warning already present; no code change; test no-token-in-log; doc line.
- AIFactory tests: real expiry; SCOPED_SERVICE_TOKENS_ENABLED on parity.

One PR per repo, branch `fix/312-ws-review-followups`, base `dev`. Artifacts PR in Factory (main).

## Steps
Per-repo membership tests (A1, P1, A2) must cover: initial failure and periodic-recheck failure each close a key principal with 1011 and unregister the client; a JWT principal stays open with orgs cleared; a successful empty membership and the no-user (legacy/DISABLE_AUTH) path return True and stay open; the warning text contains the exception class and no token.

A1 AIFactory (lead):
1. `apps/web-server/server/websockets/events.py` `_load_org_ids` + `events_websocket` per spec 1 -> `pytest tests/test_ws_acw_auth.py tests/test_ws_org_routing.py`.
2. `apps/web-server/server/auth.py:229` `_ws_acw_principal`: warning log (class only) -> same tests.
3. `tests/test_ws_acw_auth.py`: real expired key through real `_lookup_by_digest` with a fake session (patch `mcp_auth.get_db`); flag-on parity (`SCOPED_SERVICE_TOKENS_ENABLED=True` principal equals `_acw_principal(..., scoped_service_tokens_enabled=True)`); membership cases above; validator-exception log. `tests/test_auth_hardening.py`: run the real `?token=` warning with a sentinel token and assert the log lacks it.
4. `guides/REMOTE_MCP_SERVER.md`: one sentence: WS auth uses `Authorization: Bearer`, the `?token=` form is deprecated and can reach proxy logs.
P1 PFactory (lead): same as A1 1-4 at `apps/web-server/server/websockets/events.py:442`, `server/auth.py:196`; tests in `tests/test_ws_acw_auth.py`, `apps/web-server/tests/test_ws_token_prefers_header.py`; doc `guides/REMOTE_MCP_SERVER.md`.
A2 TFactory (codex): `server/mcp_remote/auth.py:_lookup_by_digest` add owner check after the expiry check (import `User` from `server.database.models`): missing/inactive owner raises `MCPAuthError("API key owner is deactivated")`; ownerless keys unchanged. Update the session stub in `apps/web-server/tests/test_api_key_auth.py:128-144` to provide `get()`; add tests: active owner OK, missing owner rejected, inactive owner rejected, ownerless key OK. `server/auth.py:369` warning; `server/websockets/events.py:227-249` per spec 1 with the membership tests; `test_ws_token_prefers_header.py` sentinel test; `guides/REMOTE_MCP_SERVER.md` sentence -> `cd apps/web-server && pytest tests/test_api_key_auth.py tests/test_ws_token_prefers_header.py <new ws test>` all pass.
C1 CFactory (codex): `apps/backend/cfactory/adapters/base.py:251` hint `CFACTORY_<SERVICE>_TOKEN` (or the shared `CFACTORY_UPSTREAM_TOKEN`) with a test asserting it for a 401; `tests/test_live_agent_proxy.py`: `_auth_headers` returns the aifactory token, falls back to upstream, is empty with none, and the injected connect seam (`:67-69`, `:103-106`) receives `additional_headers == {"Authorization": "Bearer <token>"}`; `techdocs/dependencies.md:90,148,161` and `techdocs/live-agents.md:49,54` -> `pytest tests/test_live_agent_proxy.py` and the adapter test file pass; `ruff check`.

Traps: AIFactory ruff vs standards/ruff.toml on `as` aliases (plain names), regenerate the autonomy matrix, never hand-merge; vendored files byte-checked; never log a token.

## Tests
Run each repo's CI commands locally (read `.github/workflows` and Makefile): ruff check and format check, mypy where CI runs it, then pytest on the touched files plus the auth and ws suites; all must pass.

## Rollback
Revert the PRs; no data or config changes.
