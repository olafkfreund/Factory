# API & Contracts

PFactory exposes a REST + WebSocket API and an MCP control plane, both registered
as Backstage API entities in this repo's `catalog-info.yaml`.

## REST / WebSocket — `pfactory-api`

Backend on `:3114`. Machine-readable spec:
[`apis/openapi.yaml`](https://github.com/olafkfreund/PFactory/blob/main/apis/openapi.yaml).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/plans` | Create a planning session |
| `GET` | `/api/plans/{sessionId}` | Get a session + review-gate scores |
| `POST` | `/api/plans/{sessionId}/review` | Run/re-run the review gates |
| `POST` | `/api/plans/{sessionId}/approve` | Record the human governance decision |
| `POST` | `/api/plans/{sessionId}/emit` | Emit governed GitHub issues |
| `WS` | `/ws` | Live planning progress |

## MCP control plane — `pfactory-mcp`

Stdio MCP server exposing the planning tools (`plan.create`, `plan.enrich`,
`plan.review`, `plan.approve`, `plan.emit`). See
[`apis/mcp.md`](https://github.com/olafkfreund/PFactory/blob/main/apis/mcp.md).

## Completion-event contract (RFC-0001)

PFactory **consumes** `factory-completion-events` — it emits one event on terminal
status, threaded by the GitHub-issue correlation key:

```json
{
  "correlation_key": "142",
  "service": "pfactory",
  "task_id": "001-refund-flow",
  "status": "emitted",
  "phase": "emit",
  "updated_at": "2026-06-04T15:14:45+00:00"
}
```

Terminal statuses: `emitted` → `emit`, `rejected` → `review`. The contract is
specified in [RFC-0001](https://factory.freundcloud.com/rfc/correlation-key/) and
owned by the Factory program repo.
