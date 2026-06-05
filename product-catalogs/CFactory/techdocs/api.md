# API & Contracts

CFactory exposes a cockpit/observer REST + WebSocket API and an MCP control plane,
and **owns the completion-event ingress channel**. All are registered as Backstage
API entities in this repo's `catalog-info.yaml`.

## REST / WebSocket — `cfactory-api`

API on `:3110`, realtime stream on `:3111`. Machine-readable spec:
[`apis/openapi.yaml`](https://github.com/olafkfreund/CFactory/blob/main/apis/openapi.yaml).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/events/completion` | Ingest a completion event (RFC-0001) |
| `GET` | `/api/workitems` | List work items |
| `GET` | `/api/workitems/{correlationKey}` | Aggregated work item |
| `GET` | `/api/workitems/{correlationKey}/timeline` | Event timeline |
| `GET` | `/api/usage` | Aggregated spend (by service/project/workitem) |
| `POST` | `/api/copilot/actions` | Prepare an action (advise) |
| `POST` | `/api/copilot/actions/{actionId}/confirm` | Confirm + execute (human-in-the-loop) |
| `WS` | `/ws/cockpit` | Live cockpit stream (`:3111`) |

## MCP control plane — `cfactory-mcp`

Stdio MCP server. Tools: `workitems.list`, `workitem.get`, `workitem.timeline`,
`usage.aggregate`, `copilot.advise`, `copilot.confirm`. See
[`apis/mcp.md`](https://github.com/olafkfreund/CFactory/blob/main/apis/mcp.md).

## Completion-event contract — `factory-completion-events`

CFactory **provides** this AsyncAPI: it owns the `/api/events/completion` ingress
channel that PFactory, AIFactory and TFactory publish to. The envelope (six stable
fields + optional `usage` / `correlation` blocks) is specified in
[RFC-0001](https://factory.freundcloud.com/rfc/correlation-key/) and **defined in
the Factory program repo** — CFactory references it here rather than redefining it.

Events are ingested **idempotently** by `(service, correlation_key, status)`.
