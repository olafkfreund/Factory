# AIFactory — MCP control plane

**Transport:** stdio **and** a remote **HTTP+SSE** transport for persistent
clients (the only product in the suite that exposes a remote MCP).
**Backend:** `:3101`.

AIFactory exposes its spec-first build/QA pipeline as MCP tools, routed through
the multi-provider model factory.

## Tools

| Tool | Purpose | Key inputs | Returns |
|---|---|---|---|
| `task.create` | Start a build from a governed issue/spec | `repo`, `issue_number?`, `spec`, `provider?`, `base_branch?` | `task_id`, `correlation_key` |
| `task.get` | Fetch a task (status, worktree, usage) | `task_id` | `Task` |
| `task.qa_fix` | Apply a TFactory handback correction | `task_id`, `failing_tests`, `report_url?` | updated `Task` |
| `task.worktree` | Inspect the isolated git worktree | `task_id` | branch, path, clean flag |
| `providers.list` | List configured model providers | — | provider/model/transport list |
| `task.delegate` | Delegate the build to another coding agent/executor | `task_id`, `executor` | delegation handle |

## Resources

| Resource | Description |
|---|---|
| `aifactory://tasks/{task_id}` | Task state, branch/PR, and usage |
| `aifactory://tasks/{task_id}/worktree` | The isolated worktree for the build |

## Notes

- Enterprise auth (SAML/SCIM), tenant isolation, HMAC-anchored audit logs and a
  LiteLLM gateway apply to the remote transport.
- Terminal runs emit an RFC-0001 completion event **with the v1.1 `usage` block**
  (`factory-completion-events`).
