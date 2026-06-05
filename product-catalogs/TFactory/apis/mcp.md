# TFactory — MCP control plane

**Transport:** stdio (spawned per-process by an MCP-aware client).
**Backend:** `:3103`.

TFactory exposes autonomous test generation, sandboxed execution and the
5-signal verdict as MCP tools.

## Tools

| Tool | Purpose | Key inputs | Returns |
|---|---|---|---|
| `spec.create` | Create a test spec for a branch/PR | `repo`, `branch`, `pr_number?`, `acceptance_criteria`, `lanes?` | `spec_id`, `correlation_key` |
| `spec.get` | Fetch a spec (with verdict if ready) | `spec_id` | `Spec` |
| `spec.run` | Execute the generated suite in the Docker sandbox | `spec_id`, `lanes?` | run handle |
| `spec.report` | Get the triage report + 5-signal verdict | `spec_id` | `TriageReport` |
| `handback` | Route a correction back to AIFactory's QA fixer | `correlation_key`, `spec_id`, `failing_tests`, `report_url?` | dispatch result |

## Lanes

`unit` · `browser` · `api` · `integration` · `mutation`

## The 5-signal verdict

`coverage_delta` · `stability` (re-runs) · `mutation_score` · `lint` ·
`semantic_relevance` — a pass means *meaningful* tests, not a green bar.

## Resources

| Resource | Description |
|---|---|
| `tfactory://specs/{spec_id}` | Spec state and verdict |
| `tfactory://specs/{spec_id}/report` | The PR triage report |

## Notes

- Completion of the verdict pipeline emits an RFC-0001 completion event
  (`factory-completion-events`).
