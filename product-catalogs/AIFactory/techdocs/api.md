# API & Contracts

AIFactory exposes a REST + WebSocket API and an MCP control plane (stdio and a
remote HTTP+SSE transport), registered as Backstage API entities in this repo's
`catalog-info.yaml`.

## REST / WebSocket — `aifactory-api`

Backend on `:3101`. Machine-readable spec:
[`apis/openapi.yaml`](https://github.com/olafkfreund/AIFactory/blob/main/apis/openapi.yaml).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/tasks` | Create a build task (from an issue/spec) |
| `GET` | `/api/tasks/{taskId}` | Get a task (status, worktree, usage) |
| `POST` | `/api/tasks/{taskId}/qa-fix` | Apply a TFactory handback correction |
| `GET` | `/api/tasks/{taskId}/worktree` | Inspect the isolated worktree |
| `GET` | `/api/providers` | List configured model providers |
| `WS` | `/ws/tasks/{taskId}` | Live build/QA stream |

## MCP control plane — `aifactory-mcp`

Stdio **and** remote HTTP+SSE. Tools: `task.create`, `task.get`, `task.qa_fix`,
`task.worktree`, `providers.list`, `task.delegate`. See
[`apis/mcp.md`](https://github.com/olafkfreund/AIFactory/blob/main/apis/mcp.md).

## Completion-event contract (RFC-0001)

AIFactory **consumes** `factory-completion-events` — it emits one event on terminal
status, **including the v1.1 `usage` block**:

```json
{
  "correlation_key": "142", "service": "aifactory", "task_id": "proj:001",
  "status": "merged", "phase": "act", "updated_at": "2026-06-05T12:00:00+00:00",
  "usage": { "input_tokens": 2400, "output_tokens": 100,
             "total_tokens": 2500, "cost_usd": 1.25, "model": "claude-sonnet-4-6" }
}
```

The contract is specified in
[RFC-0001](https://factory.freundcloud.com/rfc/correlation-key/) and owned by the
Factory program repo.
