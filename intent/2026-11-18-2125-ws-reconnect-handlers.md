---
status: draft
issue: 2125
author: olafkfreund
---

# Intent: frontend-web WebSocket reconnect keeps its handlers

## Problem

In `apps/frontend-web/src/lib/websocket.ts` of AIFactory (#2125), TFactory (#1564) and PFactory (#1070), the subscribed message handlers live on the per-socket `WebSocketConnection`. The reconnect timer deletes that connection and calls `connect()`, which builds a new one with `handlers: new Set()`. After any non-1000 close (including the server's 4001 for a failed `_ws_acw_principal`) the socket comes back but nobody listens, so the browser silently stops receiving events. The unsubscribe closure also still points at the dead connection.

## Proposed outcome

A subscriber keeps receiving events after any number of reconnects, including after 4001. Unsubscribe still removes only that handler and closes the socket when none are left. No handler is delivered twice and none leaks after unsubscribe or explicit disconnect.

## Affected users and systems

Browser users of the three web UIs (task logs, progress, terminal, events). No server change.

## Constraints

- Server close codes unchanged (Factory#312 decision: key sockets 1011, human/JWT sockets stay open with a warning, 4001 unchanged).
- Public API of `wsManager`, `terminalWs`, `taskLogsWs`, `taskProgressWs` unchanged.
- One PR per repo, base `dev`. PFactory's heartbeat behaviour is kept.

## Open questions

None. Owner delegation 2026-11-18: handlers move to a manager-owned registry (the recommended option in Factory#312).
