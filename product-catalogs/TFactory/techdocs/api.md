# API & Contracts

TFactory exposes a REST + WebSocket API and an MCP control plane, registered as
Backstage API entities in this repo's `catalog-info.yaml`.

## REST / WebSocket — `tfactory-api`

Backend on `:3103`. Machine-readable spec:
[`apis/openapi.yaml`](https://github.com/olafkfreund/TFactory/blob/main/apis/openapi.yaml).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/specs` | Create a test spec for a branch/PR |
| `GET` | `/api/specs/{specId}` | Get a spec (with verdict if ready) |
| `POST` | `/api/specs/{specId}/run` | Execute the suite in the sandbox |
| `GET` | `/api/specs/{specId}/report` | Triage report + 5-signal verdict |
| `POST` | `/api/handback` | Route a correction back to AIFactory |
| `WS` | `/ws` | Live generation/execution stream |

## MCP control plane — `tfactory-mcp`

Stdio MCP server. Tools: `spec.create`, `spec.get`, `spec.run`, `spec.report`,
`handback`. See
[`apis/mcp.md`](https://github.com/olafkfreund/TFactory/blob/main/apis/mcp.md).

## Contracts (RFC-0001)

TFactory **consumes** two contracts:

- `factory-completion-events` — it emits one event on terminal status
  (`triaged` / `triaged_empty` / `triager_failed` → `test`).
- `aifactory-api` — the handback POSTs the failing-test set to AIFactory's
  `/api/tasks/{id}/qa-fix`.

```json
{
  "correlation_key": "142", "service": "tfactory", "task_id": "spec-001",
  "status": "triaged", "phase": "test", "updated_at": "2026-06-05T12:00:00+00:00"
}
```

The completion-event contract is specified in
[RFC-0001](https://factory.freundcloud.com/rfc/correlation-key/) and owned by the
Factory program repo.
