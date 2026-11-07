---
status: draft
issue: 312
author: olafkfreund
---

# Intent: let the CFactory cockpit present a scoped key per factory

Epic: olafkfreund/Factory#312, checkbox "Retire the shared wildcard token → per-service scoped credentials". This slice covers the edge that AIFactory `docs/compliance/scoped-service-tokens.md` says to do first: **CFactory cockpit → PFactory, AIFactory, TFactory**. Out of scope here: agent commit identity (#1960), MFA, `DISABLE_AUTH`.

## Problem

The cockpit sends one credential, `CFACTORY_UPSTREAM_TOKEN`, to all three factories. In gitops that credential is the shared wildcard `APP_API_TOKEN` (`factory-gitops/apps/cfactory/manifests/manifests.yaml:115`). The wildcard has no scope, so if the cockpit is compromised the attacker gets admin across the fleet.

The replacement for that edge is a scoped `acw_` key minted in each factory. Two code gaps stop an operator from making the switch, even after minting the keys:

1. **There is only one setting.** `upstream_token` is one value sent to all three factories (`CFactory/apps/backend/cfactory/adapters/__init__.py:30`, `actions.py:459`, `upstream_ws.py:148`). An `acw_` key exists only in the database of the factory that minted it, so no single key works against all three. (`aifactory_token` already exists, but only the live-agents proxy reads it.)
2. **The factories reject `acw_` keys on their live feed.** In AIFactory, PFactory and TFactory, `authenticate_websocket` (`apps/web-server/server/auth.py`) accepts only a JWT or the legacy wildcard. It does not accept an `acw_` key, although the REST middleware in the same file does. The cockpit subscribes to `/ws/events` on all three. With a scoped key, that subscription would be refused and Mission Control would stop getting pushed events.

Until both gaps are closed, the cockpit cannot stop sending the wildcard.

## Proposed outcome

- CFactory can be given a separate token for each factory. Each one falls back to `upstream_token` when it is unset, so if no new setting is set, nothing changes. Every adapter call, action chain and upstream WS subscription to a factory uses that factory's token.
- AIFactory, PFactory and TFactory accept a valid `acw_` key on `/ws/events` and the other WS endpoints that use `authenticate_websocket`, under the same validation as their REST path (active, not expired, owner active). The connection is then scoped to that key's principal, not treated as the wildcard.
- With both changes deployed, an operator can mint one key per factory and set the three CFactory settings, and the cockpit no longer sends `APP_API_TOKEN` anywhere. Rollback is unsetting a setting.

## Affected users and systems

- CFactory backend: `config.py`, `adapters/__init__.py`, `actions.py`, `upstream_ws.py`, `live_agent_proxy.py` (fallback order), tests, env docs.
- AIFactory, PFactory and TFactory web-server: `server/auth.py` `authenticate_websocket`, plus tests.
- Operators of the `cfactory` Deployment. They need no change until they choose to cut over.
- No gitops, secret or cluster change in this slice.

## Constraints

- Additive and default-preserving. A deploy with no new settings behaves exactly as today.
- An `acw_` key on a WS must never get more than the same key gets on REST. Most importantly, it must never get the wildcard's unfiltered, see-everything routing. A revoked, expired or unknown key is rejected.
- Never log a token.
- The WS change is the same in the three factories, which already share this auth code, and must not make them drift apart.
- No minting, rotation or deploy. The user does not touch a secret.

## Open questions

None. Minting the keys and setting them in gitops are operator follow-ups, listed in the PR.
