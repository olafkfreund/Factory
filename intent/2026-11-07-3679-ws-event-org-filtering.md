---
status: approved
issue: 3679
author: olafkfreund
predecessor: plan/2026-11-07-312-cockpit-scoped-keys.md
---

# Intent: confine `/ws/events` to the caller's orgs, and give the cockpit a multi-org key

## Problem

Measured on the #312 branches (`feat/312-cockpit-scoped-keys`: AIFactory `9babbf6d`, PFactory `cfc00510`, TFactory `487e241d`):

| Factory | `broadcast_event(` calls | `send_to_user(` | `send_to_org(` |
| ------- | ------------------------ | --------------- | -------------- |
| AIFactory | 58 | 1 | **0** |
| PFactory | 58 | 1 | **0** |
| TFactory | 55 | 1 | **0** (no function) |

(Counts are non-test call sites under `apps/`, from `git grep`.)

1. **Every broadcast `/ws/events` event reaches every org.** The issue says only broadcast and user scopes ignore `client.org_ids`. The real gap is wider: nothing publishes with an org scope at all. Task progress, status, logs, `task-logs:stream`, subtask updates, insights chunks, changelog, PR review and auto-fix events (`websockets/events.py` `emit_*` helpers and services) all go through `broadcast_event`, which sends to every connected socket (`event_bus.py` `deliver_local`, PFactory `_deliver_local_broadcast`, TFactory `broadcast_event`). So any authenticated session in org A, a JWT user or an `acw_` key bound to A, receives org B's task logs and insights text. In AIFactory and PFactory, #312's narrowing line (`client.org_ids &= {org_id}`) is correct but has no effect, because only org-scoped delivery reads `org_ids` and nothing emits it. The #312 test "OrgScope(B) does not arrive" passes against a path production never uses. TFactory has neither: no org-scoped delivery and no narrowing, since it loads all the owner's memberships (`events.py:119-133`). Org routing alone would therefore still let an A-bound TFactory key receive B's events.
2. **`UserScope` ignores the key's org.** `send_to_user` (one caller, AIFactory `notification_service.py:145`, and its PF/TF twins) matches on `user_id` alone. A key bound to org A gets its owner's notifications about org B.
3. **Some broadcasts have no obvious org.** `profile:changed` (`agent_credential.py:419`), `cli-account-auth` (`cli_accounts.py:610`) and `github:auth-complete` (`github.py:585`, payload `_gh_auth_status`, including an error string from one user's `gh` login) look installation- or session-wide. Their owner has not been established, and nothing decides who may see them.
4. **The cockpit sees one org per factory.** An owned `acw_` key is bound to one org at mint (`CreateApiKeyRequest.org_id` is required, `mcp_remote/auth.py:53,149-185`). REST (`project_authz.py:102,333`) and, once item 1 is fixed, `/ws/events` confine it to that org. CFactory holds one token per factory (#312 `token_for`), so on a multi-org install the scoped cockpit covers one org, and the #312 operator checklist tells operators to keep the wildcard `CFACTORY_UPSTREAM_TOKEN` there.

## Proposed outcome

- A `/ws/events` client receives an org's tenant events only if that org is in its `org_ids`. A key bound to org A receives nothing about org B, whatever its owner belongs to. This holds in all three factories and across replicas, whatever the relay (AIFactory: Redis `REDIS_CHANNEL`; PFactory: Postgres LISTEN/NOTIFY `ws:*` envelopes, `relay.py`; TFactory: local delivery only).
- Legacy-token and `DISABLE_AUTH` clients keep today's behaviour (they are installation admins by definition).
- An event whose org cannot be resolved is not delivered to an org-confined client (fail closed).
- Installation-wide or session events go only to the sockets of the user who started the action.
- An open socket authenticated by an `acw_` key is re-validated every few minutes and closed with 4001 once the key is revoked or expired.
- Non-goal: a multi-org cockpit key (deferred; #3679 stays open for it). Single-org cut-over per #312 stands.
- Tests prove each of the above through the real endpoint, in each factory.

## Affected users and systems

- AIFactory, PFactory, TFactory web servers: `websockets/events.py`, AIFactory `websockets/event_bus.py` (Redis relay), PFactory `websockets/relay.py` and `_dispatch.py` (Postgres relay), and the services that call `broadcast_event`.
- The factory frontends that subscribe to `/ws/events` (single-org users must see no change).
- CFactory's upstream WS subscriber and adapters (question 1).
- Operators following the #312 checklist.

## Constraints

- Builds on the open, unmerged #312 PRs (CFactory#510, AIFactory#2017, PFactory#991, TFactory#1496, Factory#3680) and must merge after them.
- `task:log` and `task-logs:stream` fire per log line. Resolving an event's org must not add a DB round trip per emit (cache task/project → org).
- No event the recipient is authorised to receive is lost. Single-org installs see no change apart from the deliberate exclusions this issue decides (question 2 and unresolved-org events).
- Any later reload of a client's orgs (e.g. `update_client_orgs`, which has no callers today) must keep the key's bound-org intersection.
- No new dependency. No change to the REST authorization model.
- Never log tokens or event payload text.

## Open questions (answered below)

1. **Shape of the multi-org cockpit credential.** Pick one:
   - (a) **A key per org in CFactory.** Config becomes a map org → token per factory, and CFactory opens one WS per org. No factory change; config and connection count grow with orgs.
   - (b) **Phase 4 scoped service key** (`docs/compliance/scoped-service-tokens.md`) with a read-only fleet scope that is not bound to one org. One key per factory, but it introduces a new principal class that sees all orgs read-only, which the factories must honour in REST and WS.
   - (c) **An `acw_` key bound to a list of orgs** chosen at mint, each one checked against the owner's membership. Changes the key schema in three factories.
   - (d) **Defer.** Ship org filtering only; multi-org installs keep the wildcard token for the cockpit until a later issue.
2. **Who receives installation-wide events** (`profile:changed`, `cli-account-auth`, `github:auth-complete`): every authenticated client as today, only the user or session that started the action, only org admins of any org, or only unconfined clients (legacy token or `DISABLE_AUTH`)? Note that a JWT user is not unconfined: their sockets load their org memberships.
3. **Scope of this issue.** Item 1 (fix every tenant broadcast in three factories, about 170 call sites) is security work that does not depend on question 1. Should it ship on its own first, with question 1 split into a separate issue?
4. **Revocation on an open socket.** Memberships are loaded once at connect. Must a membership removal, key expiry or revocation stop delivery on an already-open socket (and within what time), or is "until reconnect" acceptable for this issue?

## Decisions (answered by the user, 2026-11-07, relayed by the team lead)

1. Ship broadcast filtering first, on its own. Route each event to its task's org in AIFactory, PFactory and TFactory. Add the missing key-org narrowing in TFactory.
2. Multi-org cockpit key: **deferred**. Keep the single-org cut-over; it is a non-goal here, and #3679 stays open for it.
3. Orgless events (auth, profile): deliver only to that user's own sockets, routed by user id.
4. Revocation: re-validate an open socket's key periodically (every few minutes) and close with 4001 once revoked. No immediate fan-out.
5. Fail closed: an event whose org cannot be determined must not go to everyone.
6. Cover the frontend consumers and CFactory's upstream subscriber, so filtering does not break the cockpit's single-org feed.
