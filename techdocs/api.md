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

## Each product's own API

Factory has no API, but each product does — see its catalog entity / repo:

| Product | API surface |
|---|---|
| **PFactory** | REST + WebSocket portal (`:3114`) + `pfactory` MCP control plane — see [PFactory](https://github.com/olafkfreund/PFactory) |
| **AIFactory** | Build/QA web server (`:3101`) + MCP control plane — see [AIFactory](https://github.com/olafkfreund/AIFactory) |
| **TFactory** | Verify web server (`:3103`) + MCP control plane — see [TFactory](https://github.com/olafkfreund/TFactory) |
| **CFactory** | Cockpit API (`:3110`) + stream (`:3111`); ingests completion events — see [CFactory](https://github.com/olafkfreund/CFactory) |
