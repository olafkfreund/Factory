---
status: approved
issue: 312
intent: intent/2026-11-18-312-ws-review-followups.md
---

# Spec: scoped cockpit keys, WS review follow-ups

## Design
Decisions (owner delegation 2026-11-18, recommended option taken):

1. **Org-membership failure (AIFactory, PFactory, TFactory `websockets/events.py`).** `_load_org_ids` returns `bool`: True for success (including an empty membership) and for the no-user-identity early return (legacy token, `DISABLE_AUTH`, which must keep working); False only when the lookup raised. On failure it logs a WARNING with the exception type only (`type(exc).__name__`, no `exc_info`), sets no orgs and returns False. `events_websocket` runs both lookups (initial and periodic recheck) inside the existing `try/finally` so the client is always unregistered. On False, a **key principal** (`api_key_id` set: CFactory and other machine clients, which retry every 3 s, `upstream_ws.py:173-209`) is closed with 1011 and reconnects. A human/JWT or legacy socket stays open with the warning (today's behaviour, now visible). Reason (Codex review, confirmed): the browser `websocket.ts` reconnect creates a connection with an empty handler set (`websocket.ts:39,69-70`), so a 1011 close would leave a browser silently without events, worse than today. That frontend defect is pre-existing (it also hits the 4001 recheck close) and is recorded as a follow-up, not fixed here.
2. **`_ws_acw_principal` (all three).** Log `logger.warning("WS key validation failed: %s", type(exc).__name__)`; still return None. The close stays 4001: the frontend treats 4001 specially (AgentConsole) and a distinct code for infrastructure failure would need client work. Only the log is added.
3. **CFactory 401/403 hint.** Name the variable actually used: `CFACTORY_<SERVICE>_TOKEN` for the probed service, with `CFACTORY_UPSTREAM_TOKEN` as the shared fallback (`Settings.token_for`).
4. **CFactory proxy header test.** Assert `_auth_headers` returns `Bearer <aifactory token>`, falls back to the upstream token, and is empty with none. Also assert the headers passed to the upstream connect if the existing test seam allows.
5. **CFactory docs.** `CFACTORY_AIFACTORY_TOKEN` is the primary scoped key for every AIFactory call (adapter, actions, `/ws/events`, live-agent console); falls back to `CFACTORY_UPSTREAM_TOKEN`. Extra org-bound keys are `CFACTORY_AIFACTORY_ORG_TOKENS`.
6. **TFactory `_lookup_by_digest`.** Load the owner `User` when `row.user_id` is set and raise `MCPAuthError("API key owner is deactivated")` when missing or inactive, as AIFactory does. Security-relevant (REST, MCP and WS).
7. **`?token=` query parameter.** Already handled: all three `_ws_extract_token` prefer the header and emit a one-time deprecation warning that never contains the token (`_warn_ws_query_token_once`). No code change; support is kept because browser clients (`frontend-web/src/lib/auth.ts`) cannot set headers. Existing tests (`test_ws_token_prefers_header.py`, `test_auth_hardening.py`) cover the one-time warning; add an assertion that the logged text never contains the token where one is missing. Document in each repo's WS docs that the header is the supported form and that the query form can reach proxy logs.
8. **AIFactory tests.** The "expired" case runs the real `_lookup_by_digest` against a fake session holding an expired key; add a case with `SCOPED_SERVICE_TOKENS_ENABLED` on asserting the principal matches `_acw_principal(..., enabled=True)`.

## Alternatives rejected
- Distinct close code for validator infrastructure failure: client treats 4001 specially; no cockpit change in scope.
- Removing `?token=`: breaks browser clients.
- Leave every socket open on membership failure: silent loss of events for machine clients.
- Close browser sockets too: the browser reconnect drops its handlers (see Design 1).
- Fix the browser reconnect in three frontends here: out of scope for small PRs; follow-up.

## Risks
A DB outage makes key clients reconnect (CFactory every 3 s, unbounded) and log one warning per attempt; acceptable noise, and the socket is useless without the lookup anyway. The warning carries only the exception class. Human sockets are unchanged.

## Verification
Each repo: its tests, ruff, mypy as CI does; new tests per item. Codex `review --base origin/dev` per repo.
