# Architecture

CFactory is a long-running observer + cockpit. It ingests events and state from the
other products and presents one steerable view of each unit of work.

## Pipeline

```
adapters ─▶ WorkItem store ─▶ copilot ─▶ advise-and-confirm actions
(REST/WS/    (correlation     (Claude     (human confirms
 webhook      store keyed by   Agent SDK)  before any write)
 ingress)     correlation key)
                                 │
                              cockpit UI (:3110 / stream :3111)
```

| Stage | What it does |
|---|---|
| **Adapters** | Read each service's REST/WS API and ingest completion events (webhook or `COMPLETED.json` sentinel). |
| **WorkItem store** | Aggregate each unit's state across PFactory/AIFactory/TFactory, keyed by the correlation key; idempotent by `(service, correlation_key, status)`. |
| **Copilot** | An agentic assistant (Claude Agent SDK) that wraps the services' APIs as its own tools. |
| **Advise-and-confirm** | The copilot *prepares* an action; a human *confirms* to execute. No autonomous writes. |

## Why REST/WS/webhooks, not MCP-first

CFactory observes over the services' existing REST/WS APIs plus the RFC-0001
webhook ingress. The stdio MCP servers are spawned per-process by an LLM client —
unsuited to a persistent cockpit — so the data plane is REST/WS/webhooks
(see [ADR-008](https://factory.freundcloud.com/)). The `cfactory-mcp` server exists
only for MCP-aware clients that want to query the correlation store.

## Data model

CFactory **owns the completion-event channel** (`factory-completion-events`) at
`/api/events/completion` and aggregates the v1.1 `usage` block into spend by
service / project / work item. See [API & Contracts](api.md).
