---
status: draft
issue: 312
author: olafkfreund
---

# Intent: scoped cockpit keys, WS review follow-ups

## Problem
The 2026-11-14 final review of the scoped cockpit keys (Factory#312) listed non-blocking follow-ups that no PR fixed. Verified still present on each repo's `dev` on 2026-11-18:
- AIFactory, PFactory and TFactory `websockets/events.py` `_load_org_ids` (TFactory added after Codex review): a failed org-membership query is logged at DEBUG and the socket stays open with no org events. Silent.
- AIFactory, PFactory, TFactory `_ws_acw_principal`: validator exceptions are swallowed with no log, so a DB outage looks like a bad key (close 4001).
- CFactory `adapters/base.py:251`: the 401/403 probe hint says "check CFACTORY_UPSTREAM_TOKEN", wrong after the scoped-key cutover.
- CFactory `live_agent_proxy._auth_headers`: no test asserts the proxy auth header.
- CFactory `techdocs/dependencies.md`, `techdocs/live-agents.md`: describe `CFACTORY_AIFACTORY_TOKEN` as console-only; it now is the primary key for every AIFactory call (shared-token fallback and the extra org tokens aside).
- TFactory `mcp_remote/auth.py` `_lookup_by_digest`: no owner `User.is_active` check (AIFactory and PFactory have it); the key now also works on WS. Security-relevant: a deactivated owner with a live key and org membership still authenticates on REST, MCP and WS.
- `_ws_extract_token` (all three): `acw_` keys via the deprecated `?token=` land in access logs. A one-time deprecation warning already exists in all three (to be confirmed in the spec); browser clients still use the query form.
- AIFactory `tests/test_ws_acw_auth.py`: the "expired" case stubs the lookup and duplicates "unknown"; parity is only asserted with `SCOPED_SERVICE_TOKENS_ENABLED` off.

## Proposed outcome
Each item is fixed or, where already fixed, recorded as such with evidence, each with a test. One small PR per repo. #312 stays open (owner-only items remain).

## Affected users and systems
AIFactory, PFactory, TFactory, CFactory (base `dev`); operators reading logs and the cockpit probe hint.

## Constraints
No token value is ever logged by our code; the query-token support is kept (browser clients depend on it), so URL exposure in upstream proxy logs is documented, not removed. No client may break: the cockpit and browser clients must keep working. Org filtering (Factory#3679) is done and is not redone. No live-cluster changes. PRs only; the coordinator merges.

## Open questions
None. Decisions taken under the owner delegation of 2026-11-18 are recorded in the spec.
