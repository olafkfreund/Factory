---
layout: default
title: "RFC-0001: Correlation Key & Completion-Event Schema"
permalink: /rfc/correlation-key/
---

# RFC-0001 — Shared Correlation Key & Completion-Event Schema

> **Status:** Accepted · **Version:** 1.1 · **Updated:** 2026-06-05
> Part of the **PARR spine** (issue [#1](https://github.com/olafkfreund/Factory/issues/1),
> [#4](https://github.com/olafkfreund/Factory/issues/4)). The product repos implement
> against this document.

## 1. Motivation

The four products — **PFactory** (plan) → **AIFactory** (act) → **TFactory** (verify),
all observed by **CFactory** (cockpit) — each own one stage of one unit of work. To
thread a single unit *across* the family (for CFactory's observability and for an
EU-AI-Act-grade audit trail), every product must agree on two things:

1. a **shared correlation key** that identifies the unit of work end to end, and
2. a **normalized completion-event envelope** every service emits when its stage
   reaches a terminal state.

This RFC specifies both. It is deliberately small and additive-friendly so a new
product (or a new field) does not force a breaking change.

## 2. The correlation key

The correlation key is the **GitHub issue number** of the governed work item — the
durable, human-visible artifact every stage already references.

```
pfactory.session_id  →  issue#  →  aifactory.task_id  →  branch / PR#  →  tfactory.spec_id
```

- **Canonical form:** the integer issue number rendered as a string, e.g. `"142"`.
- **Synthetic fallback:** when no issue exists yet (a plan that is rejected before
  emit, a unit that never reached GitHub), a service MUST emit a synthetic key of the
  form `<prefix>-<local-id>`, where `<prefix>` is the emitting service's short code:

  | Service | Prefix | Example |
  |---|---|---|
  | PFactory | `pf` | `pf-001-refund-flow` |
  | AIFactory | `af` | `af-<task_id>` |
  | TFactory | `tf` | `tf-<spec_id>` |

  A synthetic key MUST be stable for the life of that unit so events correlate even
  before an issue number exists. Once the unit acquires a real issue number, services
  SHOULD switch the `correlation_key` to that number and record the synthetic id in
  the `correlation` block (§4) so the two can be reconciled.

## 3. The completion-event envelope

A service emits **one** completion event when its stage reaches a **terminal status**.
The envelope has exactly these six required fields:

| Field | Type | Description |
|---|---|---|
| `correlation_key` | string | The shared key (§2) — issue number, or synthetic fallback. |
| `service` | string | The emitting service: `pfactory` \| `aifactory` \| `tfactory` \| `cfactory`. |
| `task_id` | string | The emitter's *local* identifier for this unit (PFactory: `session_id`; AIFactory: `task_id`; TFactory: `spec_id`). |
| `status` | string | The terminal status this service landed on (§5). |
| `phase` | string | The pipeline phase the status belongs to (e.g. `emit`, `review`, `qa`, `test`). |
| `updated_at` | string | ISO-8601 UTC timestamp of the terminal transition. |

### Example

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

## 3.1 The optional `usage` block (v1.1)

A service MAY include a `usage` object carrying the LLM token/cost it spent on this
stage, so a consumer (CFactory) can aggregate spend by service, work item and total
without polling. **Additive and optional** — consumers MUST ignore it when absent.

| Field | Type | Description |
|---|---|---|
| `input_tokens` | int | Prompt tokens (fresh, non-cached). |
| `output_tokens` | int | Completion tokens. |
| `total_tokens` | int | Convenience total. |
| `cost_usd` | number | Provider/estimated cost for the stage. |
| `model` | string? | Model id, optional. |

```json
{
  "correlation_key": "142", "service": "aifactory", "task_id": "proj:001",
  "status": "done", "phase": "act", "updated_at": "2026-06-05T12:00:00+00:00",
  "usage": { "input_tokens": 2400, "output_tokens": 100,
             "total_tokens": 2500, "cost_usd": 1.25, "model": "claude-sonnet-4-6" }
}
```

AIFactory derives it from its per-task `token_usage.json` (already tracked). PFactory
and TFactory accumulate per session/spec and emit it when instrumented (pending).

## 4. The optional `correlation` block

An emitter MAY include a `correlation` object carrying the upstream/downstream chain
links it knows about, so a consumer (CFactory) can stitch the thread without a join
table. All members are optional and additive:

```json
{
  "correlation_key": "142",
  "service": "pfactory",
  "task_id": "001-refund-flow",
  "status": "emitted",
  "phase": "emit",
  "updated_at": "2026-06-04T15:14:45+00:00",
  "correlation": {
    "session_id": "001-refund-flow",
    "issue_number": 142,
    "aifactory_task_id": null
  }
}
```

Known link fields (extend as the chain grows): `session_id`, `issue_number`,
`aifactory_task_id`, `branch`, `pr_number`, `tfactory_spec_id`.

## 5. Per-service contract

Each service decides its own terminal statuses and phases; the envelope normalizes
the *shape*, not the vocabulary. The reference (PFactory) contract:

| Service | `service` | `task_id` | Terminal `status` → `phase` | Emits when |
|---|---|---|---|---|
| **PFactory** | `pfactory` | `session_id` | `emitted` → `emit`, `rejected` → `review` | a plan is governed-emitted, or rejected |
| **AIFactory** | `aifactory` | `task_id` | e.g. `merged`/`qa_failed` → `act`/`qa` | a build run reaches a terminal state |
| **TFactory** | `tfactory` | `spec_id` | e.g. `triaged`/`triaged_empty`/`triager_failed` → `test` | the verdict pipeline completes |

`phase` for an unknown status SHOULD fall back to the status string itself. Consumers
MUST treat unknown `status`/`phase` values as opaque (forward-compatibility).

## 6. Transport

Completion events are delivered **best-effort** — a failing delivery MUST NEVER break
the emitting pipeline.

- **Webhook (the standardized transport).** When configured, the emitter POSTs the
  envelope as JSON (`Content-Type: application/json`) to the operator-set webhook URL.
  Delivery is fire-and-forget with a short timeout; failures are swallowed and logged.
- **Sentinel (same-host convenience).** Optionally, the emitter writes the envelope to
  a `COMPLETED.json` file under a configured directory, so a same-host watcher
  (e.g. CFactory's collector) can `stat` it instead of receiving the webhook.

Operators opt in per service via env. PFactory's surface (other services SHOULD mirror
the names with their own prefix):

| Env var | Effect |
|---|---|
| `PFACTORY_COMPLETION_WEBHOOK=<url>` | POST the envelope to `<url>` on terminal status. |
| `PFACTORY_COMPLETION_WEBHOOK_TIMEOUT=<seconds>` | Webhook timeout (default `5`). |
| `PFACTORY_COMPLETION_SENTINEL=1` | Also write a `COMPLETED.json` sentinel. |
| `PFACTORY_COMPLETION_SENTINEL_DIR=<dir>` | Where the sentinel is written. |

Consumers SHOULD treat events as **idempotent** by `(service, correlation_key,
status)` — a retried or duplicated delivery for the same terminal transition is the
same event.

## 7. Versioning & compatibility

- The six §3 fields are **stable**. New fields are **additive** and optional; a consumer
  MUST ignore unknown fields.
- Removing or renaming a field, or changing a field's type, is a **breaking** change and
  requires a new RFC version (and a `schema_version` field on the envelope at that time).
- Until then, the absence of `schema_version` implies **v1** (this document).

## 8. Reference implementation

PFactory implements this RFC today:

- Envelope + transport: [`apps/backend/plan/completion.py`](https://github.com/olafkfreund/PFactory/blob/main/apps/backend/plan/completion.py)
- Terminal wiring (emit / reject): `apps/backend/plan/service.py`
- Tracking: PFactory [#47](https://github.com/olafkfreund/PFactory/issues/47) (spec),
  PR #50 (impl), #52 / PR #53 (live emit so the `emitted` transition fires end-to-end).

AIFactory and TFactory implement the **emitter** side against §3–§6; CFactory implements
the **consumer** side (idempotent ingest keyed by §7).
