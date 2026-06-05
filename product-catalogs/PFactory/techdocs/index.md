# PFactory

**Prepare / Plan + Review** — the first stage of the Factory
[PARR pipeline](https://factory.freundcloud.com/).

PFactory turns an idea or spec into **governed GitHub issues**: it ingests a
plan, enriches it with live cloud/Backstage context, decomposes it, scores it
through **review gates** (architecture, security, best-practices, feasibility —
each 0–1 with citations), requires **human approval**, and emits the issues that
AIFactory picks up to build.

| | |
|---|---|
| **Stage** | Prepare / Plan + Review (PARR) |
| **Backend port** | `:3114` (dev frontend `:3115`) |
| **Surfaces** | REST + WebSocket API, MCP control plane |
| **Emits** | RFC-0001 completion events (`emitted` / `rejected`) |
| **Hands off to** | AIFactory (governed issues carry the correlation key) |

## In the suite

PFactory is a Component of the `factory-suite` System and a subcomponent of the
`factory` program repo. The unit of work it emits is threaded across the family
by the **GitHub issue number** — the shared correlation key.

```
PFactory ──governed issues──▶ AIFactory ──branch/PR──▶ TFactory
 (Plan)                         (Act)                   (Verify)
   └──────────── observed by CFactory (Review) ───────────┘
```

See [Architecture](architecture.md) and [API & Contracts](api.md). Suite-level
docs live at [factory.freundcloud.com](https://factory.freundcloud.com/).
