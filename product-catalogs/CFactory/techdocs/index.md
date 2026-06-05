# CFactory

**Review / Observe — the control tower** of the Factory
[PARR pipeline](https://factory.freundcloud.com/).

CFactory threads each unit of work across PFactory → AIFactory → TFactory in one
cockpit, using a **WorkItem correlation store** keyed by the GitHub issue number.
Its **advise-and-confirm copilot** prepares actions that a human must confirm —
no autonomous writes.

| | |
|---|---|
| **Stage** | Review / Observe (PARR) |
| **Ports** | `:3110` (API) · `:3111` (realtime stream) |
| **Surfaces** | REST + WebSocket API, MCP control plane |
| **Ingests** | RFC-0001 completion events at `/api/events/completion` |
| **Model** | Pure consumer; writes only through human-confirmed actions |

## In the suite

CFactory observes the other three products through their existing REST/WS APIs and
the completion-event webhook — no shared database.

```
PFactory ─▶ AIFactory ─▶ TFactory
   └──────────┬───────────┘
              ▼  completion events + REST/WS
          CFactory  (cockpit + advise-and-confirm copilot)
```

See [Architecture](architecture.md) and [API & Contracts](api.md).
