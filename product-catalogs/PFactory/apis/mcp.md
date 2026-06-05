# PFactory — MCP control plane

**Transport:** stdio (spawned per-process by an MCP-aware client/editor).
**Backend:** PFactory also serves a Graphiti MCP on its backend port (`:3114`).

PFactory exposes its governed-planning capability as Model Context Protocol
tools so MCP-aware editors and agents can drive planning directly.

## Tools

| Tool | Purpose | Key inputs | Returns |
|---|---|---|---|
| `plan.create` | Start a planning session from an idea/spec | `title`, `description`, `repo`, `context?` | `session_id`, initial `status` |
| `plan.get` | Fetch a session with its review-gate scores | `session_id` | `Plan` (status, gates, tasks) |
| `plan.enrich` | Pull live cloud/Backstage context into the plan | `session_id` | enriched `Plan` |
| `plan.review` | Run the review gates (architecture / security / best-practices / feasibility) | `session_id` | array of `ReviewGate` (score 0–1 + citations) |
| `plan.approve` | Record the human governance decision | `session_id`, `approver`, `decision`, `note?` | updated `Plan` |
| `plan.emit` | Emit governed GitHub issues (sets the correlation key) | `session_id` | `correlation_key`, created issues |

## Resources

| Resource | Description |
|---|---|
| `pfactory://plans/{session_id}` | The plan document and its current state |
| `pfactory://plans/{session_id}/citations` | Evidence behind each review-gate verdict |

## Notes

- The MCP surface mirrors the REST API (`pfactory-api`); use REST for
  long-running/persistent clients and MCP for editor-driven flows.
- On `plan.emit` / rejection, PFactory emits an RFC-0001 completion event
  (`factory-completion-events`).
