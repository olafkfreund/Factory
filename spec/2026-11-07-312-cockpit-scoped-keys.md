---
status: draft
issue: 312
intent: intent/2026-11-07-312-cockpit-scoped-keys.md
---

# Spec: let the CFactory cockpit present a scoped key per factory

There are four code PRs, one per repo, each on the branch `feat/312-cockpit-scoped-keys` cut from `dev`. These artifacts live in this repo because the change crosses repos (precedent: `intent/2026-10-27-312-fleet-rbac-role-model.md`).

## Design

### A. CFactory: a token per factory (`apps/backend/cfactory/`)

- `config.py`: next to the existing `aifactory_token`, add `pfactory_token` and `tfactory_token`, both `str | None = Field(default=None, repr=False)`. With the existing `CFACTORY_` env prefix they read `CFACTORY_PFACTORY_TOKEN` and `CFACTORY_TFACTORY_TOKEN`; the existing one reads `CFACTORY_AIFACTORY_TOKEN`. Add one method:

  ```python
  def token_for(self, service: str) -> str | None:
      """The bearer for one factory: its own token, else the shared upstream_token."""
      own = {"pfactory": self.pfactory_token, "aifactory": self.aifactory_token,
             "tfactory": self.tfactory_token}.get(service)
      return own or self.upstream_token
  ```

- Call sites. Each one swaps `settings.upstream_token` for `settings.token_for(<service>)`:
  - `adapters/__init__.py:30-34`: each adapter gets the token for its own service.
  - `actions.py:458-460`: uses `token_for(action.target_service)`. `target_service` is already validated as one of the three names a few lines above.
  - `upstream_ws.py:145-150, 202-206`: `_auth_headers(settings, service)`. `start_subscribers` builds the headers inside its loop, once per service.
  - `live_agent_proxy.py:71`: `settings.token_for("aifactory")`. Same behaviour as today, without a second copy of the fallback rule.
- `.env.example` and `docs/dev/environment-reference.md` gain the two new variables. The `aifactory_token` comment widens from "live agent console" to "all AIFactory calls".

**Behaviour change, and why it is acceptable.** `CFACTORY_AIFACTORY_TOKEN`, when set, now also authenticates the AIFactory REST adapter, the action chain and the `/ws/events` feed, not only the rmux console. It is not set in gitops (`factory-gitops/apps/cfactory/manifests/manifests.yaml` sets only `CFACTORY_UPSTREAM_TOKEN` and `CFACTORY_MCP_SECRET`), so on the live cluster nothing changes. Reusing the setting also means one AIFactory key covers every cockpit-to-AIFactory path, which is what the intent asks for.

### B. Factories: accept an `acw_` key on WebSocket (AIFactory, PFactory, TFactory)

In `apps/web-server/server/auth.py` `authenticate_websocket`, a new branch goes after the JWT and legacy checks and before the final reject:

```python
if token.startswith("acw_"):
    principal = await _ws_acw_principal(token)
    if principal is not None:
        return principal
    await websocket.close(code=4001, reason="Unauthorized")
    raise WebSocketAuthError("Invalid API key")
```

`_ws_acw_principal` is a small per-factory helper. It calls the same validator the REST middleware uses, so each factory keeps its own rules:

| Factory | REST validator reused | Returns |
|---|---|---|
| AIFactory | `mcp_remote.auth.authenticate_rest` (owner active, org active, `api` scope for owned keys) | `{"id": key.user_id, "email": None, "role": "user", "org_id": key.org_id, "api_key_id": key.key_id}`; **`None` when `key.user_id is None`** (see below) |
| PFactory | `_try_authenticate_api_key` (unexpired, `api` scope capped by owner role, owner active) | its dict, unchanged (`id`, `email`, `role`, `api_key_id`, `org_id`) |
| TFactory | `mcp_remote.auth.authenticate` plus `key.has_scope(REST_API_SCOPE)` (`api:full`) | `{"id": key.user_id, "email": None, "role": "user", "org_id": key.org_id, "api_key_id": key.key_id}`; `None` when the scope is missing or `user_id` is `None` |

Any exception from the validator is caught and treated as `None`, so the request is rejected, as on REST. The token is never logged.

**Ownerless (service) keys are rejected on WS.** The `/ws/events` routing gives a client with `user_id is None` every org's events (AIFactory `websockets/event_bus.py:289`, PFactory `websockets/events.py:324`). TFactory has no org routing: `broadcast_event` sends every event to every client, JWT users included, so an `acw_` key there gets exactly what a logged-in user gets. TFactory rejects ownerless keys anyway, for one rule across the fleet. That is the wildcard's see-everything routing. On REST, an AIFactory service key is `is_service` and bypasses project authorization, so WS see-all would technically match REST. The approved intent still forbids it. Rejecting the key keeps the change from adding a new see-everything credential. The cockpit's keys are therefore user-owned: minted by a service-account user who belongs to the orgs the cockpit should watch. That works the same way in all three factories, since PFactory and TFactory keys are user-owned anyway. The rejection is commented as `shortcut: ownerless keys rejected on WS; revisit with Phase 4 scope enforcement`.

**Org-bound keys stay in their org.** In the AIFactory and PFactory `/ws/events` endpoints (`websockets/events.py`; TFactory never reads `org_ids`, so it gets no change), the org-membership lookup fills `client.org_ids` from the owner's memberships. Right after that assignment comes one added line:

```python
if user_info.get("org_id"):  # an org-bound acw_ key must not widen to the owner's other orgs
    client.org_ids &= {user_info["org_id"]}
```

If the lookup fails, `org_ids` stays empty, so the client fails closed. JWT principals have no `org_id`, so they are unaffected. `update_client_orgs` has no callers in any of the three repos today; the risks below cover it.

## Alternatives rejected

- **Keep `upstream_token` for WS only and give REST separate tokens.** The cockpit would still hold the wildcard, so nothing would be retired.
- **One `acw_` key for all three factories.** Each factory checks keys against its own database, so no such key exists.
- **A fleet-wide key service or a JWT-based M2M token.** That is a new mechanism. The intent asks for the replacement that already exists.
- **Accept ownerless service keys on WS with see-all routing.** That matches REST parity, but the intent's constraint rules it out, and it needs Phase 4 scope enforcement to be safe.
- **A new `CFACTORY_AIFACTORY_UPSTREAM_TOKEN` that leaves `aifactory_token` console-only.** That would be two settings for the same factory, and an operator could cut over half of AIFactory's paths and miss the other half.

## Risks

- **Mission Control goes quiet after a bad cut-over.** If an operator sets a per-factory token that the factory rejects on WS (wrong scope, or an ownerless key), that factory's live feed closes with 4001 and the cockpit falls back to polling. Mitigation: the PR's operator checklist says to check that `/ws/events` connects before removing the wildcard. Rollback is unsetting the variable.
- **Narrower visibility.** A user-owned key only sees events and tasks for its owner's orgs. A cockpit key whose owner is missing from some org shows less than the wildcard does. That is the intended least privilege, and the checklist warns about it.
- **`update_client_orgs`** could later re-widen a key-bound client if a caller is added. There are no callers today. The spec accepts this and the PR notes it.
- **Repos drift.** The three `authenticate_websocket` changes have the same shape but call different validators, by design (the intent's constraint). Tests in each repo pin the behaviour.
- No cluster impact. Nothing is deployed, and the defaults are unchanged.

## Verification

- CFactory: unit tests for `token_for` (own token wins, fallback to `upstream_token`, unknown service falls back), for the adapters getting per-service tokens, for the action chain header per target, and for the per-service WS headers. Run `just test` (or the repo's pytest) plus ruff, and keep the existing `test_pydantic_credential_repr` green, since the new fields must be `repr=False`.
- Each factory: WS auth tests. A valid owned `acw_` key returns a principal. An unknown, expired or under-scoped key is closed with 4001. An ownerless key is closed with 4001 (AIFactory/TFactory). JWT and legacy paths are unchanged. An org-bound key's `client.org_ids` is narrowed to the key's org (AIFactory, PFactory). Run each repo's pytest for the touched test files plus ruff.
- Grep: no remaining `settings.upstream_token` read in CFactory outside `config.py`'s `token_for`.
