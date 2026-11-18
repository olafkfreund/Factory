---
status: draft
issue: 2125
intent: intent/2026-11-18-2125-ws-reconnect-handlers.md
---

# Spec: manager-owned handler registry

## Design

In `WebSocketManager` add `private handlers: Map<string, Set<MessageHandler>>` keyed by endpoint. It outlives any socket.

- `connect()`: drop `handlers` from `WebSocketConnection`. `onmessage` reads `this.handlers.get(endpoint)` at delivery time, so a re-created socket delivers to the same handlers with no copying and no duplicate path. The reconnect timer keeps its backoff but first checks that `this.connections.get(endpoint) === connection`; if a newer socket replaced it (direct `connect()` call) or the entry is gone, it does nothing, so no untracked socket is created. The timer never touches the registry, so 4001 and every other non-1000 close recover the same way; `getAuthenticatedWsUrl` is called again on each connect, which is the token recheck.
- `subscribe()`: add the handler to the registry first, then `connect()` if there is no connection. Unsubscribe is bound to the Set it was added to: it is a no-op if the registry's Set for the endpoint is no longer that Set (after an explicit `disconnect()` and re-subscribe), otherwise it deletes the handler; when the set is empty it deletes the registry entry and calls `disconnect()`.
- `disconnect()` (explicit, also used by `taskLogsWs.disconnect` etc.): also deletes the registry entry, so nothing leaks. Idle-timeout reconnect never calls it.
- Stale-socket guard: `onclose` of a socket that is no longer `this.connections.get(endpoint)?.ws` does not schedule a reconnect, so a closed-then-replaced socket cannot spawn a second one. `onmessage` of a stale socket is ignored for the same reason (no double delivery).
- Dispatch: JSON parsing is in its own try/catch; handlers run outside it, each in its own try/catch that logs, so a throwing handler is neither redelivered as raw text nor blocks the others.
- PFactory keeps its heartbeat code as is.

Same change in all three files; no API change.

## Alternatives rejected

- Copy the old `handlers` set into the new connection inside the timer: works, but leaves unsubscribe closures bound to dead connections and keeps two owners of the truth.
- Re-subscribe from the React hooks on `onConnect`: pushes the bug into every caller.
- Change server close codes: ruled out by the Factory#312 decision.

## Risks

- Retry policy is unchanged and out of scope: each new socket starts `reconnectAttempts` at 0, so retries are not capped across sockets, and a closed connection stays in `connections` until its timer replaces it. Capping retries is a separate change.
- `disconnect()` now drops all handlers for the endpoint. Teardown in the apps goes through the unsubscribe closure (AIFactory `api-adapter.ts:122-126`; global events discard theirs at `:978`); the exported `*.disconnect` helpers have no callers there, so nothing relies on handlers surviving them. The plan re-greps each repo.
- Callers that never unsubscribe still keep their handlers, as before.

## Verification

New `src/lib/websocket.test.ts` per repo with a fake `WebSocket` and fake timers: subscribe, force close (1006), reconnect, handler still receives; close 4001 then reconnect; unsubscribe after reconnect stops delivery and closes the socket; several reconnects deliver exactly once; explicit disconnect clears handlers; a stale unsubscribe after disconnect+resubscribe leaves the new handler; a pending timer does not replace a newer socket; a throwing handler is not redelivered and does not block others. Then `npm run lint`, `typecheck`, `test` in each `apps/frontend-web`.
