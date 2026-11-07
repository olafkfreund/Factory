---
status: draft
issue: 312
spec: spec/2026-11-07-312-cockpit-scoped-keys.md
coders:
  1: coder   # CFactory: config field + four mechanical call-site swaps + tests in one repo; neither large nor tricky
  2: codex   # AIFactory WS acw_ branch: small security-critical logic (ownerless reject, principal parity, org narrowing)
  3: codex   # PFactory: same small tricky logic against a different validator; same agent keeps the pattern consistent
  4: agy     # TFactory: mechanical mirror of step 3's shape with no org-routing change
reviewers:
  - codex    # the final diff spans four repos of auth code; a second model checks the principal-parity claim
  - agy      # independent read on the CFactory fallback order and on test coverage
---

# Plan: let the CFactory cockpit present a scoped key per factory

## Approved decisions (from the spec)

- **CFactory.** New settings `pfactory_token` and `tfactory_token`, both `str | None = Field(default=None, repr=False)`, sit beside the existing `aifactory_token`. Env vars: `CFACTORY_PFACTORY_TOKEN`, `CFACTORY_TFACTORY_TOKEN`, `CFACTORY_AIFACTORY_TOKEN`. One method, `Settings.token_for(service) -> str | None`, returns `own or self.upstream_token`. Every outbound call to a factory uses it: the adapters, the action chain, the upstream WS subscriber (headers are built per service, inside the loop) and the live-agents proxy. `aifactory_token` now covers every AIFactory path, not only the console.
- **Factories (all three).** `authenticate_websocket` gains an `acw_` branch after the JWT and legacy checks and before the final reject. That branch calls `_ws_acw_principal(token)`, a per-factory helper:
  - It reuses the REST validator and builds the same principal REST builds.
  - It returns `None` for an ownerless key (`user_id is None`), for any validator exception (`except Exception`) and for a missing scope. On `None` the branch closes the socket with code 4001 and raises `WebSocketAuthError`.
  - It never logs the token.
  - It adds the comment `shortcut: ownerless keys rejected on WS; revisit with Phase 4 scope enforcement`.
  - Callers: `websockets/events.py` and `rmux/bridge.py`. Leave `verify_websocket_token` alone.
- **Org narrowing (AIFactory and PFactory only).** In `websockets/events.py`, right after `client.org_ids = {...}`, add:
  `if user_info.get("org_id"): client.org_ids &= {user_info["org_id"]}`
  TFactory never reads `org_ids`, so it gets no routing change.
- **Out of scope.** No change to the `DISABLE_AUTH` behaviour, to broadcast or user-scope routing, or to `update_client_orgs` (it has no callers). No gitops, secret or deploy change.

Code lives on `feat/312-cockpit-scoped-keys` in each repo, cut from `origin/dev`. The worktrees are under `/tmp/claude-1000/-mnt-code-Source-home-GitHub-Factory/157388fb-55f6-470f-a189-e3907c327b71/scratchpad/wt/<Repo>-312`.

## Steps

1. **CFactory** (`CFactory-312`):
   - `apps/backend/cfactory/config.py:84-91`: add the two fields with comments next to `aifactory_token`, widen the `aifactory_token` comment, and add `token_for` as a method on `Settings`.
   - `adapters/__init__.py:30-34`: pass `settings.token_for("pfactory" | "aifactory" | "tfactory")` to each adapter.
   - `actions.py:458-460`: use `token_for(action.target_service)`.
   - `upstream_ws.py:145-150, 200-206`: change to `_auth_headers(settings, service)` and call it inside the loop with `name`.
   - `live_agent_proxy.py:71`: use `settings.token_for("aifactory")`.
   - Add both env vars to `.env.example` and `docs/dev/environment-reference.md`.
   - Tests: `tests/test_actions.py`, `tests/test_adapters.py`, `tests/test_upstream_ws.py`, plus a `token_for` test. Cover: own token wins, fallback to `upstream_token`, unknown service falls back, and each service gets its own header. Add the two new fields to `tests/test_pydantic_credential_repr.py:194` if that test lists the fields.

   Verify: `cd CFactory-312 && PYTHONPATH=apps/backend /mnt/code/Source-home/GitHub/CFactory/apps/backend/.venv/bin/pytest tests/test_actions.py tests/test_adapters.py tests/test_upstream_ws.py tests/test_live_agent_proxy.py tests/test_pydantic_credential_repr.py tests/test_well_known.py -q`, plus `ruff check apps/backend tests` and `ruff format --check`. Then `grep -n "settings.upstream_token" apps/backend/cfactory` must match only inside `config.py`.

   Traps: the `config.py` credential-repr test requires `repr=False`. Do not use `SecretStr`: the codebase interpolates the raw string (comment at `config.py:39`).

2. **AIFactory** (`AIFactory-312`):
   - In `apps/web-server/server/auth.py`, add `_ws_acw_principal` near `_acw_principal`. It runs `from .mcp_remote.auth import authenticate_rest` lazily, as REST does at `auth.py:365`, then `key = await authenticate_rest(f"Bearer {token}")`, with `except Exception: return None`. It returns `None` if `key.user_id is None`. Otherwise it returns `_acw_principal(key, scoped_service_tokens_enabled=getattr(get_settings(), "SCOPED_SERVICE_TOKENS_ENABLED", False))`.
   - In `authenticate_websocket` (around `auth.py:424-465`), add the branch after the legacy check.
   - `websockets/events.py:125`: add the org-narrowing line inside the `try`, after the assignment.
   - Tests: a new `tests/test_ws_acw_auth.py` covering:
     - an owned key gives a principal equal to `_acw_principal(...)`;
     - an unknown key or a validator that raises closes with 4001;
     - an ownerless key closes with 4001;
     - the JWT and legacy paths are unchanged;
     - `event_bus` delivery: owner in orgs A and B with a key bound to A, so OrgScope(A) arrives and OrgScope(B) does not;
     - a failed membership lookup means no org events.

     Copy the stubbing style of `tests/test_auth_hardening.py` and `tests/test_event_bus.py`.

   Verify: `cd AIFactory-312 && /mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin/pytest tests/test_ws_acw_auth.py tests/test_auth_hardening.py tests/test_event_bus.py tests/test_auth_acw_main_api.py -q`, then `ruff check` on the touched files.

   Traps: tests insert `apps/web-server` and `apps/backend` on `sys.path` (see `test_auth_hardening.py:24`). `_warn_legacy_api_token_once` uses a module global, so do not reorder the legacy branch.

3. **PFactory** (`PFactory-312`):
   - In `apps/web-server/server/auth.py`, `_ws_acw_principal` calls `await _try_authenticate_api_key(token)` inside `try/except Exception: return None` and returns its dict.
   - Add the branch in `authenticate_websocket`, after `_is_legacy_api_token`.
   - `websockets/events.py:386`: add the org-narrowing line.
   - Tests: a new `tests/test_ws_acw_auth.py` with the same cases as step 2, except the ownerless case (PFactory keys are always owned). Delivery uses PFactory's `send_to_org` (`events.py:324` predicate).

   Verify: `cd PFactory-312 && /mnt/code/Source-home/GitHub/PFactory/apps/backend/.venv/bin/pytest tests/test_ws_acw_auth.py tests/test_ws_relay.py tests/test_rbac_console_and_mcp.py -q`, then `ruff check` on the touched files.

   Traps: PFactory's ruff config is stricter (PLW0603, no `global`). `_try_authenticate_api_key` bumps `last_used_at`, which is expected.

4. **TFactory** (`TFactory-312`):
   - In `apps/web-server/server/auth.py`, `_ws_acw_principal` lazily imports `REST_API_SCOPE, MCPAuthError, authenticate` from `.mcp_remote.auth`, as at `auth.py:265`. It calls `key = await authenticate(f"Bearer {token}")` with `except Exception: return None`. It returns `None` unless `key.has_scope(REST_API_SCOPE)` and `key.user_id` is set. Otherwise it returns the same dict as `auth.py:277-283`.
   - Add the branch in `authenticate_websocket`. No change to `events.py`.
   - Tests: a new `tests/test_ws_acw_auth.py` covering:
     - an owned `api:full` key gives the principal;
     - an `mcp:read`-only key closes with 4001;
     - an ownerless key, an unknown key or a raising validator closes with 4001;
     - JWT and legacy are unchanged.

   Verify: `cd TFactory-312 && /mnt/code/Source-home/GitHub/TFactory/apps/backend/.venv/bin/pytest tests/test_ws_acw_auth.py tests/rmux/test_bridge.py -q`, then `ruff check` on the touched files.

   Traps: the TFactory Justfile runs pytest under `nix develop -c` for runtime libraries. If the venv pytest fails on imports, run it through `nix develop -c`.

5. **Lead (me).** Run each repo's touched test files and ruff, then commit per step, citing the step. Run the final Opus review, plus codex and agy, over the plan and the four diffs. Push the four branches and the Factory artifacts branch, and open five PRs. Each PR links intent, spec and plan, names who did each step, and carries the operator checklist:
   1. mint a user-owned key per factory;
   2. set the three `CFACTORY_*_TOKEN` variables;
   3. check that `/ws/events` connects and that the rmux console works;
   4. only then drop `CFACTORY_UPSTREAM_TOKEN`.

   File the follow-up issue for the broadcast and TFactory org-routing gap.

## Tests

The commands are listed per step above. Each must pass with no new failures, and ruff must be clean on the touched files.

## Rollback

Revert the PR. At runtime nothing needs rolling back: every new path is inactive until an operator sets a per-factory token or presents an `acw_` key on a WS. Unsetting the token restores today's behaviour.
