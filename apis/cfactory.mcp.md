# CFactory — MCP control plane

**Transport:** stdio (for MCP-aware clients that want to query the correlation
store). The persistent cockpit itself runs on REST/WS (`cfactory-api`,
`:3110`/`:3111`) — see [ADR-008](../techdocs/decisions.md): stdio MCP is
spawned per-process by an LLM client and is unsuited to a long-running observer,
so the cockpit data plane is REST/WS/webhooks, not MCP-first.

CFactory exposes read-mostly observer tools plus the advise-and-confirm action
surface (writes always require human confirmation).

## Tools

| Tool | Purpose | Key inputs | Returns |
|---|---|---|---|
| `workitems.list` | List work items | `project?`, `status?` | `WorkItem[]` |
| `workitem.get` | Aggregated state across services | `correlation_key` | `WorkItem` |
| `workitem.timeline` | Ordered completion events for a unit | `correlation_key` | `CompletionEvent[]` |
| `usage.aggregate` | Spend by service / project / work item | `group_by?` | `UsageRow[]` |
| `copilot.advise` | Prepare (not execute) an action | `correlation_key`, `intent`, `prompt?` | `CopilotAction` (status `prepared`) |
| `copilot.confirm` | Execute a prepared action (human-in-the-loop) | `action_id` | `CopilotAction` (status `executed`) |

## Resources

| Resource | Description |
|---|---|
| `cfactory://workitems/{correlation_key}` | The aggregated work item |
| `cfactory://workitems/{correlation_key}/timeline` | The event timeline |

## Notes

- CFactory is a **pure consumer**: it observes via the other services' REST/WS
  APIs and the RFC-0001 webhook ingress (`/api/events/completion`), and only
  writes through human-confirmed copilot actions.
