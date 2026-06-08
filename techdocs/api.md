# API & Contracts

**Factory exposes no API.** This is a program / meta repository — documentation, RFCs
and cross-cutting plans, with **no services, no REST surface, no MCP server**. There is
therefore no `openapi.yaml` here.

What this repo *does* own are the **inter-product contracts** that let the four
products cooperate: a shared correlation key and a normalized completion-event
envelope, specified in **RFC-0001**. The products implement those contracts; this page
summarizes them and links to each product's own API entity.

## RFC-0001 — Correlation key & completion-event envelope

> Status: **Accepted** · Version 1.1 · part of the PARR spine.
> Canonical text: [factory.freundcloud.com/rfc/correlation-key](https://factory.freundcloud.com/rfc/correlation-key/)
> (source: `docs/rfc/0001-correlation-key-and-completion-event.md`).

### The correlation key

The unit of work is identified end to end by the **GitHub issue number** of the
governed work item:

```
pfactory.session_id → issue# → aifactory.task_id → branch / PR# → tfactory.spec_id
```

- **Canonical form:** the integer issue number as a string, e.g. `"142"`.
- **Synthetic fallback:** when no issue exists yet, a service emits a stable
  `<prefix>-<local-id>` key (`pf-…` / `af-…` / `tf-…`) and reconciles to the real
  number once assigned.

### The completion-event envelope

A service emits **one** event when its stage reaches a terminal status. Six fields are
required and stable:

| Field | Type | Description |
|---|---|---|
| `correlation_key` | string | The shared key — issue number or synthetic fallback |
| `service` | string | `pfactory` \| `aifactory` \| `tfactory` \| `cfactory` |
| `task_id` | string | The emitter's local id (PFactory `session_id`, AIFactory `task_id`, TFactory `spec_id`) |
| `status` | string | The terminal status this service landed on |
| `phase` | string | The pipeline phase (e.g. `emit`, `review`, `act`, `qa`, `test`) |
| `updated_at` | string | ISO-8601 UTC timestamp of the terminal transition |

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

**Optional additive blocks** (consumers ignore when absent):

- `usage` — per-stage LLM spend (`input_tokens`, `output_tokens`, `total_tokens`,
  `cost_usd`, `model?`), so CFactory can aggregate cost without polling.
- `correlation` — known upstream/downstream chain links (`session_id`,
  `issue_number`, `aifactory_task_id`, `branch`, `pr_number`, `tfactory_spec_id`),
  so a consumer can stitch the thread without a join table.

### Per-service terminal contract

| Service | `service` | `task_id` | Terminal `status` → `phase` |
|---|---|---|---|
| **PFactory** | `pfactory` | `session_id` | `emitted` → `emit`, `rejected` → `review` |
| **AIFactory** | `aifactory` | `task_id` | e.g. `merged` / `qa_failed` → `act` / `qa` |
| **TFactory** | `tfactory` | `spec_id` | e.g. `triaged` / `triaged_empty` / `triager_failed` → `test` |

`phase` for an unknown status falls back to the status string; consumers must treat
unknown `status`/`phase` values as opaque.

### Transport

Best-effort — a failing delivery must never break the emitting pipeline.

- **Webhook (standard):** the emitter POSTs the JSON envelope to an operator-set URL,
  fire-and-forget with a short timeout.
- **Sentinel (same-host):** optionally writes `COMPLETED.json` for a same-host watcher
  (e.g. CFactory's collector) to `stat`.

Operators opt in per service via env, e.g. PFactory:

| Env var | Effect |
|---|---|
| `PFACTORY_COMPLETION_WEBHOOK=<url>` | POST the envelope on terminal status |
| `PFACTORY_COMPLETION_WEBHOOK_TIMEOUT=<s>` | Webhook timeout (default `5`) |
| `PFACTORY_COMPLETION_SENTINEL=1` | Also write a `COMPLETED.json` sentinel |
| `PFACTORY_COMPLETION_SENTINEL_DIR=<dir>` | Where the sentinel is written |

Events are **idempotent** by `(service, correlation_key, status)`.

### Versioning

The six required fields are stable; new fields are additive and optional. Removing or
renaming a field, or changing a type, is breaking and requires a new RFC version (and a
`schema_version` field then). Absence of `schema_version` implies v1.

### Reference implementation

PFactory implements this RFC today (envelope + transport in
`apps/backend/plan/completion.py`; terminal wiring in `apps/backend/plan/service.py`).
AIFactory and TFactory implement the **emitter** side; CFactory implements the
**consumer** side (idempotent ingest).

## Task Contract v2 — RFC-0002

Where RFC-0001 lets the family *track* one unit of work, **RFC-0002** lets it
*hand the work off in full*. The **Task Contract v2** is one canonical, signed
document carrying **WHAT** (the plan), **HOW** (the execution profile) and
**VERIFY** (the test profile), so PFactory computes the profile once, AIFactory
executes it without re-planning (`skip_planning`), and TFactory tests it without
guessing.

- Specification: [RFC-0002](https://github.com/olafkfreund/Factory/blob/main/docs/rfc/0002-task-contract.md)
- Machine-readable JSON Schema: [`apis/task-contract.schema.json`](https://github.com/olafkfreund/Factory/blob/main/apis/task-contract.schema.json)
- Trust: signed with AIFactory's `trusted_plan` HMAC envelope; the signature
  covers the execution and test profiles, not just the plan.
- Sync: status flows back via the RFC-0001 completion-event envelope keyed by the
  same `correlation_key`.

Adoption is tracked by cross-linked epics in each repo (PFactory emits + signs;
AIFactory ingests + skips planning; TFactory consumes the `tfactory` block).

## GitHub Agentic Integration — RFC-0003

Where RFC-0001 and RFC-0002 are about the family talking to *itself*, **RFC-0003**
is about the family talking to **GitHub's native agentic surface** — the Copilot
cloud agent, the free GitHub Models inference API, MCP call-home for the cloud
agent, and Copilot automations in Actions. Each product adopted these independently
and converged on the same conventions; RFC-0003 names them once.

- Specification: [RFC-0003](https://github.com/olafkfreund/Factory/blob/main/docs/rfc/0003-github-agentic-integration.md)
- Shared label taxonomy (the trigger contract): `copilot:delegate`, `aifactory:run`,
  `aifactory:review`, `pfactory:run`, `tfactory:run`.
- Provider: a `github-models` alias routes through each product's existing
  OpenAI-compatible backend (`models.github.ai/inference`, `GITHUB_TOKEN` auth) —
  no new provider class.
- Call-home: the cloud agent reaches each product's existing `*-mcp` surface during
  a coding session for spec/plan/test context.
- Threading: a Copilot-authored PR is threaded by the same RFC-0001 correlation key
  as any other work item.

Adoption shipped across all three product repos (epics AIFactory#456, PFactory#87,
TFactory#277 — all closed).

## Each product's own API

Factory has no API of its own, but each product does. These are registered as
**Backstage API entities** in this repo's catalog (machine-readable definitions in
[`apis/`](https://github.com/olafkfreund/Factory/tree/main/apis), embedded via
`$text`) until the product repos are onboarded — see [Catalog & entities](catalog.md).

| Product | API entities | Surface |
|---|---|---|
| **PFactory** | `pfactory-api` (openapi), `pfactory-mcp` (mcp) | REST + WebSocket portal (`:3114`) + MCP control plane — see [PFactory](https://github.com/olafkfreund/PFactory) |
| **AIFactory** | `aifactory-api` (openapi), `aifactory-mcp` (mcp) | Build/QA web server (`:3101`) + stdio & remote HTTP+SSE MCP — see [AIFactory](https://github.com/olafkfreund/AIFactory) |
| **TFactory** | `tfactory-api` (openapi), `tfactory-mcp` (mcp) | Verify web server (`:3103`) + MCP control plane — see [TFactory](https://github.com/olafkfreund/TFactory) |
| **CFactory** | `cfactory-api` (openapi), `cfactory-mcp` (mcp), `factory-completion-events` (asyncapi) | Cockpit API (`:3110`) + stream (`:3111`); owns the completion-event ingress — see [CFactory](https://github.com/olafkfreund/CFactory) |

The `factory-completion-events` AsyncAPI is the machine-readable form of the
RFC-0001 envelope documented above: **provided by** CFactory (the
`/api/events/completion` channel) and **consumed by** PFactory, AIFactory and
TFactory.
