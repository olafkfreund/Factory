---
status: draft
issue: 3679
intent: intent/2026-11-07-3679-ws-event-org-filtering.md
---

# Spec: confine `/ws/events` to the caller's orgs

Scope: owner decisions 1 and 3 to 6 in the intent. The multi-org cockpit key is a non-goal (decision 2).

## Facts the design rests on (measured on `feat/312-cockpit-scoped-keys`)

- Every tenant event identifies its project in one of two ways:
  - `taskId`, which is the composite `"{project_id}:{spec_id}"`, not `Task.id`. It is built in `delegation_runner.py`, `agent_service.py` and the execution routes, and split in `project_authz.py` (AIF :274, PF :324).
  - `projectId`, for the insights, changelog, PR review and auto-fix families.
  The exception is `task-logs:stream`, which carries only a bare `specId`. Spec ids are not unique across projects.
- A project's org lives in the `projects.json` registry, as `load_projects()[project_id]["org_id"]`. `load_projects` is in AIF `project_registry.py:47`, PF `services/project_paths.py:32` and TF `routes/projects.py:236`. The DB `Task`/`Project` tables are not used for routing.
- REST already decides who sees a project (`project_authz.check_project_access`, all three factories):
  - `is_service` principals (the legacy `API_TOKEN` and `DISABLE_AUTH`) see everything.
  - A project without `org_id` is visible to service principals only.
  - An `acw_` key sees only its bound org.
  - A member sees their orgs.
- On the WS, those service principals arrive as `user_info is None`, so `client.user_id is None`.
- `send_to_org` exists and is relayed in AIF (Redis `OrgScope`) and PF (Postgres `ws:org`), but has no callers. TF has no `send_to_org` and no relay.
- PF's analysis notes that `projects.json` may not be shared between pods. The org must therefore be resolved on the pod that emits, not the one that delivers.
- CFactory (`upstream_ws.py`) parses only events with a task key and a `status`. It connects with either the user-less legacy wildcard (`CFACTORY_UPSTREAM_TOKEN`) or a single-org `acw_` key (#312). Frontends filter by the selected project, and no view needs another org's events (`api-adapter.ts` in each factory).

## Design

The rule matches REST: **an event reaches a client only if the client may read the event's project over REST.** It is applied in each factory's `websockets/events.py` (AIF also touches `event_bus.py`).

1. **`_event_org(payload) -> str | None`** (new, module-private in `events.py`):
   - project id = `payload["projectId"]`; failing that, the part of `payload["taskId"]` before `:` (only if it contains `:`); failing that, `None`;
   - org = `load_projects().get(pid, {}).get("org_id") or None`;
   - results (including `None`) are cached per project id for 30 s in a module dict of `(monotonic time, org)`;
   - any exception means `None`.
   The cache bounds the file reads on the `task:log` hot path. A project re-assigned to another org is honoured within 30 s.
2. **One delivery predicate, `_may_receive(client, org) -> bool`**, used by every local delivery path (org, user, and the legacy broadcast path):
   - `client.user_id is None` (a service client: legacy token or `DISABLE_AUTH`): `True`.
   - `client.key_org_id` set (an `acw_` socket): `org is not None and org == client.key_org_id`. This holds even if `org_ids` were later widened by `update_client_orgs`, which has no callers today.
   - Otherwise (a JWT socket): `org is not None and org in client.org_ids`, subject to the REST-mode rule in "Owner decision pending" below.
3. **`broadcast_event(event_type, payload)` becomes org-routed.** Its body is `await send_to_org(_event_org(payload) or SERVICE_ONLY_ORG, event_type, payload)`, where `SERVICE_ONLY_ORG = ""`. The org delivery predicate is already `client.user_id is None or org in client.org_ids`, and no client's `org_ids` contains `""`. So an unresolvable event reaches only user-less service clients (fail closed), across replicas, with no envelope change. None of the ~170 call sites change. The old broadcast scope and its relay kind stay, because a pod running the old version may still send them during a rolling deploy. Their local delivery (AIF `deliver_local` `BroadcastScope`, PF `_deliver_local_broadcast`) now applies `_may_receive(client, None)`, so an old emitter cannot leak through a new receiver.
4. **Org membership per client.** AIF and PF already load `OrgMember` rows into `client.org_ids` and intersect them with an `acw_` key's org (#312). TF loads the rows but does not intersect, so add the same line: `if user_info.get("org_id"): client.org_ids &= {user_info["org_id"]}`. TF gains `send_to_org` and `_deliver_local_to_org`, using `_may_receive` (local only, since TF has no relay). If the membership query fails, `org_ids` stays empty, so the client receives nothing.
5. **User-scoped events and bound keys.** `ConnectedClient` gains `key_org_id: str | None`, set to `user_info.get("org_id")` at register.
   - User-scoped delivery (AIF `deliver_local` `UserScope`, PF `_deliver_local_to_user`, TF `send_to_user`) still matches `user_id`.
   - For an `acw_` socket it also requires that the payload's org equals `key_org_id`. The payload's org is `payload.get("org_id")`, or `payload["data"]["org_id"]` for `notification:new`, so no registry read is needed on the delivering pod.
   - An org-less user event, such as a login completion, therefore never reaches a key socket (fail closed). Key sockets are the cockpit, not an interactive login.
   - `notify_org` builds `{"org_id": org_id, **(data or {})}` (AIF `notification_service.py:209`, PF/TF `:211`), which lets the caller's `data` override the org. Flip it to `{**(data or {}), "org_id": org_id}`.
6. **Events with no org** (decision 3):
   - `cli-account-auth` (AIF `cli_accounts.py:610`, PF `:545`, TF `:561`) and `github:auth-complete` (AIF `github.py:585`, PF `:843`, TF `github_auth.py:273`) go to the user who started the login: thread `request.state.user["id"]` from the start route into the background thread or task and call `send_to_user`.
   - When the starting principal `is_service` (the legacy token or `DISABLE_AUTH`; REST gives it `id="default"` in TF `auth.py:190-196`, while its socket has `user_id=None`), or there is no user, use `send_to_org(SERVICE_ONLY_ORG, …)` instead. Sending to `"default"` would reach no socket.
   - `profile:changed` is triggered automatically and has no user. It stays on `broadcast_event` and therefore reaches service clients only.
7. **`task-logs:stream` gains `projectId`.** `emit_task_logs_stream(spec_id, chunk, project_id=None)` adds `"projectId": project_id` when it is given. `TaskLogWriter` takes an optional `project_id` and passes it on. The call sites that build the writer pass the project id they already hold (AIF `agent_service.py:1334,1339`, `agent_kubejob.py:719`; PF `agent_service.py:1123,1130`; TF `agent_service.py:~344`). Where a caller has no project id, the event goes to service clients only (fail closed). The payload otherwise stays the same, and frontends ignore the extra key.
8. **Re-validating an open `acw_` socket** (decision 4). In `events_websocket`, if the token from `_ws_extract_token(websocket)` starts with `acw_`, re-run `_ws_acw_principal(token)` (#312) at most every `_KEY_RECHECK_SECONDS = 300`, inside the existing 30 s receive loop. On `None`, `close(code=4001)` and leave the loop; `finally` unregisters the client. A transient validator error also closes the socket, and the client reconnects. JWT and legacy sockets are unchanged.

**CFactory: no code change.**
- The legacy wildcard is user-less, so it keeps receiving every org's events plus the service-only ones.
- A single-org `acw_` key receives its org's events, which is #312's documented single-org cut-over.
- Tests in each factory pin both behaviours.

## Owner decision pending: JWT sockets in PF/TF shadow mode

PF and TF REST run project authz in shadow mode by default (`RBAC_ENFORCE_TASK_ROUTES` off; `project_authz.py` header, PF :7-9, TF :15-16). The live `factory` namespace runs them with OIDC and without the flag. No code in PF or TF writes `org_id` into `projects.json`. Strict JWT filtering would therefore stop every live PF/TF update for browser users, while REST still serves them the same data. The question was put to the owner on 2026-11-07, with option A recommended:

- **Option A.** Key and service rules as above. JWT sockets apply the org rule in AIF always, and in PF/TF only when `RBAC_ENFORCE_TASK_ROUTES` is on. In shadow mode a JWT socket receives what it receives today, with a debug "would drop" log.
- **Option B.** Strict for JWT everywhere now.

This section is replaced by the owner's answer before the spec is approved.

## Alternatives rejected

- **Edit the ~170 call sites to call `send_to_org` (the lead's suggestion for agy).** It gives the same result with 170 times the diff, and every future emitter must remember to do it. Central routing fails closed by default.
- **Resolve the org on the delivering pod.** `projects.json` may not be shared between pods (PF analysis), and every pod would repeat the lookup.
- **A new `service` scope kind in the envelope.** An old pod during a rolling deploy would drop it with a warning. `OrgScope("")` uses the existing kind, with the same fail-closed result.
- **Look up via the DB `Task.project_id → Project.org_id`.** Nothing populates or reads those rows for these ids.
- **Immediate revocation fan-out.** Ruled out by decision 4.

## Risks

- **Projects with no `org_id` in `projects.json`.** Their events reach service clients, and JWT sockets as the owner decision allows. An `acw_` key never receives them. AIF enforces REST and backfills a default org (`project_registry.py:109`). In PF and TF, no code writes `org_id`, so a scoped cockpit key receives no PF/TF events until projects carry an org; CFactory's polling adapters still update those items. Say so in the PR.
- **The frontend log stream drops `projectId`.** Each `api-adapter.ts` passes `(specId, chunk)` only (AIF :889, PF :887, TF :888), so a user authorised for two projects with the same spec number can still see mixed log lines in the UI. This is a pre-existing UI bug, not a cross-org leak, and it is out of scope; file a follow-up issue.
- **`task:update` and `task:subtask-update` with a bare spec id.** Some callers fall back to a bare spec id (PF `agent_worktree_sync.py:62`, AIF `:381,405`). Those events go to service clients only. Accepted: fail closed.
- **The 30 s cache.** Re-assigning a project to another org leaks its events to the old org for up to 30 s.
- **The re-check costs one validator call (a DB lookup) per `acw_` socket every 5 minutes.** This is negligible.
- **The per-task sockets leak too.** `/ws/tasks/{id}/logs|progress` check only the token, not the org. That is outside `/ws/events`; file a follow-up issue.
- **Merge order.** This builds on the #312 PRs (`_ws_acw_principal`, AIF/PF narrowing). Branch from `feat/312-cockpit-scoped-keys` and merge after it.

## Verification

Per factory: a new `tests/test_ws_org_routing.py`, driven through the real `/ws/events` endpoint with stubbed `OrgMember` rows and a stubbed `load_projects`. Cases:

- A JWT member of A receives A's `task:status` (from a `taskId`) and A's `insights:chunk` (from a `projectId`), and does not receive B's.
- A legacy or user-less client receives A's, B's and unresolvable events.
- An `acw_` key bound to A, whose owner is in {A, B}, receives A's events only. This exercises TF's new narrowing.
- An event for a project with no `org_id`, an unknown project or a bare spec id reaches only the user-less client.
- `notification:new` with `data.org_id = B` does not reach the A-bound key socket of the same user, and does reach that user's JWT socket. An org-less user event does not reach a key socket.
- An `acw_` socket bound to A whose `org_ids` is then widened to {A, B} by `update_client_orgs` still receives no B events.
- A legacy `BroadcastScope` (AIF Redis envelope) or `ws:broadcast` (PF relay) arriving from an old pod reaches service clients only, and JWT sockets only as the owner decision allows.
- Real emitters, not hand-made payloads:
  - `emit_task_status("<pid>:001-x", "in_progress")` reaches the member of `pid`'s org, and its payload still passes CFactory's `parse_upstream_message` (a status and a task key, checked by asserting the keys).
  - A `TaskLogWriter` built with `project_id` emits `task-logs:stream` with `projectId`.
- A service-initiated login completion reaches the service client.
- `cli-account-auth` reaches the initiating user only.
- `task-logs:stream` carrying `projectId` A reaches the A member only.
- A raising `load_projects` means the event reaches user-less clients only.
- Cross-replica: AIF serialises `OrgScope("")` and delivers it to user-less clients only; PF dispatches `ws:org` with `org_id=""` the same way.
- Revocation: a key that validates at connect and then returns `None` is closed with 4001 after the re-check interval, which the test patches to 0.

Run each repo's existing WS and event tests, plus ruff, using the repo's own CI ratchet (`factory-seclint`/strict baseline), locally before pushing.
