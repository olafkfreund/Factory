# Deployment-Metrics — MCP contract (RFC-0013)

**Transport:** stdio (spawned per-process by an MCP-aware client).
**Status:** contract defined; **stubbed now, real provider later**.

The deployment-metrics MCP gives PFactory a single, provider-agnostic way to ask
"how does this repo actually deploy, and how healthy is its delivery?" so it can
populate the additive `deployment` block of the Task Contract
([RFC-0002](../docs/rfc/0002-task-contract.md), `$defs.deployment`).

The contract is deliberately small and **honest by construction**: every tool
returns a well-formed envelope with an `available` flag. When a backend cannot
answer (no credentials, no deployment history, provider unreachable), it returns
`available: false` with a `reason` and **null metrics** — it never fabricates a
healthy-looking delivery record. The dependency-free reference provider is
`scripts/deployment_metrics_stub.py`, which returns `available: false` by default
and well-formed sample data only when an explicit fixture is supplied.

## Tools

| Tool | Purpose | Key inputs | Returns |
|---|---|---|---|
| `deploy_history` | Recent deploy events for a repo/environment | `repo`, `env?`, `limit?` | `DeployHistory` |
| `dora_metrics` | DORA delivery metrics for a repo/environment | `repo`, `env?`, `window_days?` | `DoraContext` |

### `deploy_history(repo, env?, limit?)`

Returns recent deploy events, newest first.

```jsonc
{
  "source": "stub",            // 'stub' | 'github-deployments' | 'argocd' | ...
  "repo": "olafkfreund/my-app",
  "env": "production",
  "available": false,          // true only when real events were retrieved
  "reason": "no provider configured (stub default)",
  "deploys": []                // [{ "env", "status", "at", "ref", "url" }, ...]
}
```

### `dora_metrics(repo, env?, window_days?)`

Returns the DORA delivery context that maps 1:1 onto
`$defs.deployment.dora_context`.

```jsonc
{
  "source": "stub",
  "repo": "olafkfreund/my-app",
  "env": "production",
  "available": false,          // false => downstream treats health as UNKNOWN
  "reason": "no provider configured (stub default)",
  "deploy_success_rate": null, // { "value", "window_days", "sample" } when available
  "lead_time_p50_hours": null,
  "change_fail_rate": null,
  "last_deploy": null          // { "env", "status", "at" } when available
}
```

## Honesty rules (normative)

1. `available: false` means metrics were **unreachable**, never that delivery is
   healthy. Numeric fields MUST be `null` when `available: false`.
2. A provider MUST NOT invent deploy events or rates. Absence is reported as
   absence.
3. Downstream policy (the `risk_class` / `system_gates` derivation in RFC-0013)
   treats unavailable DORA context as **unknown** and does not relax any gate on
   the strength of missing data.

## Reference provider

`scripts/deployment_metrics_stub.py` — pure, dependency-free Python. Default
behavior is `available: false` (degrade, never fabricate); pass a fixture to get
well-formed sample data for tests and demos. Run its self-test with
`python3 scripts/deployment_metrics_stub.py`.

## Notes

- The shape of `dora_metrics` is the source of truth for
  `$defs.deployment.dora_context`; keep them in sync.
- A real provider (GitHub Deployments / Argo CD / Datadog) implements the same
  two tools behind the same envelope, so PFactory needs no change to adopt it.
