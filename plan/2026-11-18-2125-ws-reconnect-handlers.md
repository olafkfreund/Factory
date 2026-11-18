---
status: draft
issue: 2125
spec: spec/2026-11-18-2125-ws-reconnect-handlers.md
coders:
  1: codex   # small tricky logic (registry, identity guards) plus its test file
  2: claude  # port of step 1 to TFactory, mechanical
  3: claude  # port to PFactory, keeps heartbeat
reviewers:
  - codex    # final `codex review --base origin/dev` per repo
---

# Plan: manager-owned WebSocket handler registry

Issues: AIFactory#2125, TFactory#1564, PFactory#1070. Worktrees base `dev`, branch `fix/ws-reconnect-handlers`, one PR per repo. Server close codes unchanged. Decisions carried from the approved spec:

- `WebSocketManager.handlers: Map<endpoint, Set<MessageHandler>>` owns subscriptions; `WebSocketConnection` loses `handlers`.
- `onmessage` reads the registry at delivery time; JSON parse has its own try/catch; each handler runs in its own try/catch that logs.
- Reconnect timer first checks `this.connections.get(endpoint) === connection`, else does nothing; otherwise unchanged (delete + `connect`). `onclose`/`onmessage` of a socket that is no longer the current one is ignored (no reconnect, no delivery).
- `subscribe` adds to the registry (creating the Set) before `connect` when there is no connection. Unsubscribe is bound to its Set: no-op if the registry's Set for the endpoint differs; deletes the handler; on empty deletes the entry and calls `disconnect`.
- `disconnect()` also deletes the registry entry.
- Retry policy unchanged (out of scope). PFactory heartbeat unchanged.

## Steps

0. Before editing, in each repo grep callers of `wsManager.disconnect`, `terminalWs.disconnect`, `taskLogsWs.disconnect`, `taskProgressWs.disconnect`, `disconnectAll` under `apps/frontend-web/src`; if any caller relies on handlers surviving, stop and record a deviation.
1. AIFactory `apps/frontend-web/src/lib/websocket.ts` (connect lines ~29-85, subscribe ~90-105, disconnect ~123-133) implement the above; add `apps/frontend-web/src/lib/websocket.test.ts` (fake `WebSocket` class, `vi.useFakeTimers`, mock `./auth` `getAuthenticatedWsUrl`): subscribe, close 1006, advance timers, new socket opens, message reaches handler; same with close 4001; unsubscribe after reconnect stops delivery and closes the socket; three reconnects deliver once per message; explicit disconnect clears handlers; stale unsubscribe after disconnect+resubscribe keeps the new handler; pending timer does not replace a newer socket; throwing handler is not redelivered and does not block others. Verify: in `apps/frontend-web`, `npm run lint`, `npm run typecheck`, `npx vitest run src/lib/websocket.test.ts`.
   Traps: AIFactory eslint style wraps single-statement arrows in braces (`{ h(); }`); `--max-warnings 2039` must not rise; plain imports, no `as` alias in parenthesised imports.
2. TFactory same files: apply step 1's diff (`git diff` from the AIFactory worktree, `git apply -3`; resolve the brace-style differences by hand) plus the test file. Verify: same three commands. Traps: `--max-warnings 2817`.
3. PFactory same files: apply the same change, keeping `heartbeat` handling in `onopen`/`onclose`/`disconnect` (heartbeat set up per socket, cleared on close). In `onclose` the heartbeat `clearInterval` runs BEFORE the stale-socket guard, so a stale close never leaks the interval; add a mandatory test that a stale socket's close clears its interval and that a reconnected socket starts a new one. Verify: same commands. Traps: `--max-warnings 3004`.
4. Final: `codex review --base origin/dev` in each repo, fix confirmed findings (max 2 rounds), rebase on `origin/dev`, push, open PRs linking these three artifacts, wait for checks.

## Tests

`npm run lint && npm run typecheck && npm test` in `apps/frontend-web` of each repo; expected: green, new test file passes, lint warnings not above the cap. Before the change, the reconnect tests fail (proves the bug).

## Rollback

Revert the PR commit in the affected repo; no data or server change.
