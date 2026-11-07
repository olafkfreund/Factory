---
status: approved
issue: 3679
spec: spec/2026-11-07-3679-ws-event-org-filtering.md
coders:
  1: codex   # AIF routing core: small, security-critical predicate + revocation logic
  2: coder   # AIF plumbing: thread user id / project id through a few call sites + tests; neither large nor tricky
  3: codex   # PF routing core: same tricky logic against the Postgres relay and the REST-mode flag
  4: coder   # PF plumbing: mirror of step 2
  5: agy     # TF: ports steps 3+4 (incl. new org delivery, the missing key narrowing, revocation, login routing) onto local-only delivery; not merely mechanical, so codex and the fresh Opus reviewer check it closely
reviewers:
  - codex    # authored steps 1 and 3; reviews the cross-repo consistency of the predicate
  - agy      # authored step 5; independent read on tests and fail-closed coverage
# Each reviewer authored some steps, so the independent check is the fresh Opus reviewer (managed rule), given only this plan and the diffs.
---

# Plan: confine `/ws/events` to the caller's orgs

## Approved decisions (carried from the spec, self-contained)

**Who may receive an event.** An event reaches a socket only if that client may read the event's project over REST, in the mode REST is running in.

**`_event_org(payload) -> str | None`**, module-private in each factory's `websockets/events.py`:
- Project id: `payload.get("projectId")`. Otherwise, if `payload.get("taskId")` is a str containing `:`, the part before the first `:`. Otherwise `None`.
- Org: `load_projects().get(pid, {}).get("org_id") or None`.
- Cache: per project id for `_ORG_CACHE_SECONDS = 30.0`, in a module dict `pid -> (time.monotonic(), org)`. `None` results are cached too.
- Any exception → `None`.
- It runs on the emitting pod only, never on the delivering pod.

**`_may_receive(client, org: str | None) -> bool`**, the single predicate behind every local delivery path:
- `client.user_id is None` (service client: legacy token or `DISABLE_AUTH`) → `True`.
- `client.key_org_id` is set (an `acw_` socket) → `org is not None and org == client.key_org_id`.
- Otherwise (a JWT socket):
  - Compute `strict_ok = org is not None and org in client.org_ids`.
  - If `_jwt_strict()` is true → return `strict_ok`.
  - Otherwise, if not `strict_ok`, `logger.debug("ws would drop %s for user %s", ...)`, and return `True`.
  - Never log payload text.
- `_jwt_strict()`:
  - AIF: always `True`.
  - PF/TF: `bool(get_settings().RBAC_ENFORCE_TASK_ROUTES)`, read on each call. This is the flag `routes/project_authz._enforcing()` reads (PF :61, TF :53).

**Routing.**
- `SERVICE_ONLY_ORG = ""`.
- `broadcast_event(event_type, payload)` body becomes `await send_to_org(_event_org(payload) or SERVICE_ONLY_ORG, event_type, payload)`. None of the ~170 call sites change.
- Org delivery uses `_may_receive(client, org or None)`, so `""` behaves as "no org".
- The legacy broadcast delivery path stays (an old pod may still send it during a rolling deploy) but now filters with `_may_receive(client, None)`:
  - AIF: `event_bus.deliver_local` `BroadcastScope` branch.
  - PF: `_deliver_local_broadcast`, which also serves relayed `ws:broadcast`.

**Clients.**
- `ConnectedClient` gains `key_org_id: str | None = None`. At register it is set to `(user_info or {}).get("org_id")`; only the `acw_` principal carries `org_id`.
- TF additionally gets the #312 narrowing line after loading memberships: `if user_info.get("org_id"): client.org_ids &= {user_info["org_id"]}`.

**User-scoped delivery** keeps the `client.user_id == user_id` match.
- For a client with `key_org_id`, it also requires `_payload_org(payload) == client.key_org_id`.
- `_payload_org` is `payload.get("org_id")`, otherwise `payload.get("data", {}).get("org_id")` when `data` is a dict, otherwise `None`.
- So an org-less user event never reaches a key socket.

**`notify_org` override.** Flip `merged_data = {"org_id": org_id, **(data or {})}` to `{**(data or {}), "org_id": org_id}` (`services/notification_service.py`, AIF :209, PF/TF :211).

**Events with no org** (`cli-account-auth`, `github:auth-complete`):
- Thread the starting principal from the start route into the background thread or task.
- If the principal is a dict with an `id` and not `is_service` → `send_to_user(id, …)`.
- Otherwise → `send_to_org(SERVICE_ONLY_ORG, …)`. A thread uses the same `run_coroutine_threadsafe`/loop mechanism the call site already uses.
- `profile:changed` stays on `broadcast_event`.

**`task-logs:stream`.**
- `emit_task_logs_stream(spec_id, chunk, project_id: str | None = None)` adds `"projectId": project_id` when it is set.
- `TaskLogWriter.__init__` takes `project_id: str | None = None` and passes it at its emit.
- Every `TaskLogWriter(` constructor call passes the project id its caller holds.

**Revocation.**
- Applies when the socket's token (`_ws_extract_token(websocket)`, read once after auth) starts with `acw_`.
- In the existing receive loop, every `_KEY_RECHECK_SECONDS = 300` (monotonic), re-run `await _ws_acw_principal(token)`.
- On `None`: `await websocket.close(code=4001)` and break. The existing `finally` unregisters. `_ws_acw_principal` (#312) already turns any validator exception into `None`, so a raising validator closes the socket too; test it.
- JWT and legacy sockets are untouched.

**CFactory.** No code change.

**Non-goals.** The multi-org cockpit key (#3679 stays open), the per-task sockets `/ws/tasks/*`, and the frontend `specId` collision. Follow-ups are filed in step 6.

**Accepted residual (user, 2026-11-07).** In PF/TF shadow mode a JWT socket still receives other orgs' and unresolved events, as REST serves them. Turning on `RBAC_ENFORCE_TASK_ROUTES` closes it.

## Branches and worktrees

- Per repo `R` in {AIFactory, PFactory, TFactory}:
  - Worktree: `/tmp/claude-1000/-mnt-code-Source-home-GitHub-Factory/157388fb-55f6-470f-a189-e3907c327b71/scratchpad/wt/R-3679`.
  - Branch: `feat/3679-ws-event-org-filtering`, cut from `origin/feat/312-cockpit-scoped-keys` (#312 adds `_ws_acw_principal` and the AIF/PF narrowing).
- PRs target `dev`, because PF/TF CI only runs for PRs into `dev`/`main`. They state "merge after #312's PR".
- No `git stash`, no `git worktree prune`.

## Test rules (all factories)

- Cases that involve connecting, registration, membership narrowing, `key_org_id` binding or revocation go through the real `/ws/events` endpoint (FastAPI `TestClient.websocket_connect`), with auth and the `OrgMember` query stubbed. Pure-delivery cases may call the delivery functions directly.
- The PF/TF flag test uses one open JWT socket. With the flag off it receives B's event; patch settings to on, emit again, and the same socket does not receive it. REST `check_project_access` for B follows the flag the same way.
- Every factory also covers:
  - an org-less user event (for example `cli-account-auth` for the key's owner) not reaching that owner's `acw_` socket;
  - `notify_org(A, data={"org_id": B})` producing `data.org_id == A`;
  - `_event_org` caching `None`, re-reading after expiry (patch `time.monotonic`), and honouring a re-assigned project after expiry;
  - a raising validator closing a key socket with 4001.

## Steps

1. **AIFactory routing core** (codex).
   - `apps/web-server/server/websockets/event_bus.py`:
     - `ConnectedClient` (~:60-120) gains `key_org_id`; `register_client` sets it.
     - Add `_may_receive`.
     - `deliver_local` (:258-298): BroadcastScope → `_may_receive(c, None)`; UserScope → user match plus the key rule; OrgScope → `_may_receive(c, scope.org_id or None)`.
   - `apps/web-server/server/websockets/events.py`:
     - Add `SERVICE_ONLY_ORG`, `_event_org` (import `load_projects` from `..project_registry`) and `_payload_org` if it is needed here.
     - Re-route `broadcast_event` (:76).
     - Add the revocation re-check in the `events_websocket` loop (:101-155).
   - `services/notification_service.py:209`: apply the flip.
   - Tests: new `tests/test_ws_org_routing.py`. Cover every case in the spec's Verification that applies to AIF:
     - member A / B;
     - service client;
     - key bound to A with owner in {A, B};
     - unresolved, no-org, raising-registry, bare spec id;
     - notification with `data.org_id` B against key and JWT sockets;
     - `update_client_orgs` widening does not widen a key socket;
     - legacy `BroadcastScope` envelope through `_parse_envelope` + `deliver_local`;
     - `OrgScope("")` round trip through `_serialize_envelope` / `_parse_envelope`;
     - real `emit_task_status("<pid>:001-x", ...)` delivery, with an assertion that the payload has `taskId` and `status`;
     - revocation with `_KEY_RECHECK_SECONDS` patched to 0 and the validator stubbed to return a principal then `None` → close 4001;
     - plus everything under "Test rules".
     Stub `load_projects` via monkeypatch on the events module and the `OrgMember` query in the style of `tests/test_ws_acw_auth.py` (#312) and `tests/test_event_bus.py`. Clear the org cache between tests.
   - Verify (worktrees have no `.venv`; always use the main checkout's venv by absolute path): `cd AIFactory-3679 && /mnt/code/Source-home/GitHub/AIFactory/apps/backend/.venv/bin/pytest tests/test_ws_org_routing.py tests/test_ws_acw_auth.py tests/test_event_bus.py tests/test_auth_hardening.py -q`.
   - Traps:
     - Tests put `apps/web-server` and `apps/backend` on `sys.path` (`test_auth_hardening.py:24`).
     - Do not reorder the legacy branch in `auth.py` (`_warn_legacy_api_token_once` global).
     - `asyncio.create_task` for fire-and-forget needs the existing `# noqa: RUF006` pattern.
     - Keep the `_parse_envelope` `kind == "org"` str check, which accepts `""`.

2. **AIFactory plumbing** (coder).
   - `services/task_log_writer.py:61` (`__init__`) and `:221` (emit): add `project_id`.
   - `websockets/events.py` `emit_task_logs_stream` (:240): add the `project_id` param.
   - Callers `services/agent_service.py:1334,1339` and `services/agent_kubejob.py:719`: pass the project id in scope. If a caller truly has none, pass nothing and note it in the hand-back.
   - `routes/cli_accounts.py`: `start-login` route → background thread → `:610` emit.
   - `routes/github.py`: auth start route → `_monitor_gh_auth` (:545) → `:585` emit.
   - Apply the user / service / org-less rule above to both.
   - Tests in `tests/test_ws_org_routing.py` (append):
     - a `TaskLogWriter(project_id=...)` emit carries `projectId` and reaches only org members;
     - `cli-account-auth` from a JWT user reaches only that user's socket; from a service principal it reaches only the service client;
     - the same two cases for `github:auth-complete`.
   - Verify: as step 1, plus `tests/test_task_log_writer*.py` and any `tests/*cli_accounts*`/`*github*auth*` tests that exist.
   - Traps: thread-to-loop scheduling must reuse the call site's existing loop handle, not `asyncio.run`.

3. **PFactory routing core** (codex).
   - In `apps/web-server/server/websockets/events.py`, make the same changes as step 1:
     - `ConnectedClient` :41, `_register_client` :69;
     - `_deliver_local_broadcast` :241, `broadcast_event` :271, `_deliver_local_to_user` :282, `_deliver_local_to_org` :311;
     - the `events_websocket` loop :362+.
   - `_jwt_strict()` reads `get_settings().RBAC_ENFORCE_TASK_ROUTES`. `load_projects` comes from `..services.project_paths`.
   - `services/notification_service.py:211`: apply the flip.
   - Tests: new `tests/test_ws_org_routing.py`, with step 1's cases adapted:
     - relay: `_dispatch` `ws:org` with `org_id=""` and `ws:broadcast`;
     - the flag test: with the flag off, a JWT member of A gets B's event and REST `check_project_access` for B in shadow mode does not raise through the dependency; with the flag on (patched settings), the WS drops it and REST raises 403.
   - Verify: `cd PFactory-3679 && /mnt/code/Source-home/GitHub/PFactory/apps/backend/.venv/bin/pytest tests/test_ws_org_routing.py tests/test_ws_acw_auth.py tests/test_ws_relay.py tests/test_rbac_console_and_mcp.py -q`.
   - Traps: PF ruff is stricter (PLW0603: no `global`; mutate the cache dict instead), and mypy `--strict` is ratcheted on changed files, so annotate fully.

4. **PFactory plumbing** (coder).
   - The same work as step 2:
     - `services/task_log_writer.py:68` and `:262`, with callers at `services/agent_service.py:1123,1130`;
     - `routes/cli_accounts.py`: `start-login` :652 → threads :448-521 → emit :545;
     - `routes/github.py`: `/auth/start` :848 → emit :843.
   - Tests and traps: as step 2, plus step 3's PF traps.

5. **TFactory** (agy).
   - Steps 3 and 4 applied to TF:
     - `websockets/events.py`: `ConnectedClient` :37, `_register_client` :48, `broadcast_event` :70, `send_to_user` :85, the `events_websocket` loop :107+;
     - add `send_to_org` and `_deliver_local_to_org` (local only), and the narrowing line after :131;
     - `_jwt_strict()` from `RBAC_ENFORCE_TASK_ROUTES`; `load_projects` from `..routes.projects` (use a lazy import if it cycles);
     - `notification_service.py:211`;
     - `emit_task_logs_stream` :237 and its caller `services/agent_service.py:~344` (the enclosing function's project id);
     - `routes/cli_accounts.py:561` and `routes/github_auth.py:273`, with their start routes.
   - Tests: new `tests/test_ws_org_routing.py` with step 3's cases. The key-bound case exercises the new narrowing; drop the relay cases (TF has no relay).
   - Verify: `cd TFactory-3679 && /mnt/code/Source-home/GitHub/TFactory/apps/backend/.venv/bin/pytest tests/test_ws_org_routing.py tests/test_ws_acw_auth.py tests/rmux/test_bridge.py -q`. If imports fail, run it under `nix develop -c`.
   - Traps: TF's lazy-import style for `mcp_remote.auth`; no unused imports (F401).

6. **Lead.**
   - Per repo, run the step's tests plus the whole `tests/` directory that CI runs, and reproduce CI's lint gates locally against `origin/dev`. Worktrees have no `.venv`: put `/mnt/code/Source-home/GitHub/<Repo>/apps/backend/.venv/bin` first on `PATH` and read every `apps/backend/.venv/bin/...` below as that absolute path. Bare `ruff`/`python` means those venv binaries.
     - AIF: `apps/backend/.venv/bin/ruff check apps/backend apps/web-server apps/model-gateway scripts tests`; `python scripts/cq_ratchet.py --base origin/dev --ruff apps/backend/.venv/bin/ruff --config standards/ruff.toml --paths 'apps/backend/*.py' 'apps/web-server/*.py' 'scripts/*.py'`; `ruff format --check apps/backend apps/web-server apps/model-gateway scripts tests`.
     - PF: `PATH=apps/backend/.venv/bin:$PATH apps/backend/.venv/bin/python scripts/ratchet_lint.py --base origin/dev --package apps/backend --package apps/web-server --package scripts`; `ruff format --check`.
     - TF: `ruff check apps/backend tests scripts`; `python scripts/ratchet_lint.py --base origin/dev --package apps/backend --package apps/web-server --package scripts`; `ruff format --check apps/backend apps/web-server scripts tests`.
   - Commit per step, citing the step.
   - Final review: a fresh Opus agent given only this plan's path and the three diffs, plus codex and agy read-only reviews. Fix what is confirmed.
   - Push, and open three factory PRs into `dev` plus the Factory docs PR. Each links intent, spec and plan, names who did each step, gives the merge order (after the #312 PRs), and states the operator notes:
     - PF/TF JWT sockets stay unfiltered until `RBAC_ENFORCE_TASK_ROUTES` is on;
     - PF/TF projects need `org_id` in `projects.json` before a scoped cockpit key receives their events.
   - File follow-ups: per-task sockets `/ws/tasks/*` lack org checks; frontend `task-logs:stream` ignores `projectId`.

## Tests

The commands are per step above. Expected: every listed test passes, nothing that passes on `origin/feat/312-cockpit-scoped-keys` regresses, and every ratchet reports no new violations.

## Rollback

Revert the factory PRs (`git revert` the merge commits). The delivery code returns to broadcast-to-all, with no data or schema change.

Reverting also restores the cross-org leak, including to scoped `acw_` keys. Behaviour that the revert undoes:
- key sockets confined to their org;
- login completions sent to the initiating user only;
- bare-spec-id and no-org events withheld from key sockets and strict JWT sockets;
- AIF JWT filtering.

In PF/TF shadow mode, JWT behaviour does not change either way.
