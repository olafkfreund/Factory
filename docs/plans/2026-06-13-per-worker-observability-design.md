---
layout: default
title: Per-worker / per-provider cost & observability — design
permalink: /plans/per-worker-observability/
---

# Per-worker / per-provider cost & observability for AIFactory parallel builds

> Status: Approved design (super-brainstorm, 2026-06-13). Implementation phased (P1/P2).

## Context
AIFactory already runs parallel coding workers across providers (Claude / Gemini→Antigravity /
Ollama / etc.) — `agents/parallel_runner.py` (`asyncio.gather`, child git worktree per subtask),
`providers/factory.py` (8 providers wired), and `parallel`/`workers`/`phase_models` are live
end-to-end from the RFC-0002 contract. **What's missing is the ability to SEE it.** Today cost +
tokens collapse to a single scalar `model` (last-writer-wins) in `token_usage.json` and the
RFC-0001 completion event; CFactory models cost per-service, never per-worker/per-model; and
OpenTelemetry is scaffolded-but-dormant (agents emit no spans, no OTel metrics, exporter off by
default). A Claude+Gemini+Ollama parallel run is therefore unobservable — undercutting the
program's governance+observability bet. This work makes heterogeneous parallel runs observable,
per worker and per provider, on both OpenTelemetry and the CFactory cockpit.

## Decisions
1. Target: per-worker / per-provider cost & observability.
2. Granularity: capture at the **worker (subtask)** level; headline **per-provider / per-model**
   rollups; per-worker is the drill-down.
3. Delivery: **live per-worker sub-events** as each worker finishes + a terminal rollup event.
4. Surface: **both** — OTel per-worker spans + metrics AND CFactory rollups (phased).
5. Governance: **observe + soft budget alert** (warn over a contract budget; never abort).
6. Backend: **instrument + ship dashboards-as-code**; operator runs the OTLP backend.

## Architecture
A per-worker usage record is produced where the work happens (each subtask's agent session) and
fans out to three additive, best-effort sinks:

```
worker (subtask) finishes
   ├─ token_attribution: per-worker record {worker_id, phase, subtask_id, provider, model,
   │                      input/output tokens, cost_usd, duration_ms}  (no longer collapsed)
   ├─ OTel: a worker span (attrs provider/model/phase) + metrics (token/cost/duration
   │        counters+histograms, tagged provider|model|phase) — exported when otel.enabled
   └─ live completion sub-event (RFC-0001 v1.3, new phase "worker") → CFactory cockpit
on task end:
   └─ terminal completion event gains usage.workers[] + usage.by_provider{} + usage.by_model{}
      (scalar aggregate fields KEPT for back-compat) + soft budget flag if over contract budget
```

Local providers (Ollama) report `cost_usd: 0` but still emit tokens + duration (the universal
metrics). Per-model cost is derived from a provider-agnostic pricing map — **reuse LiteLLM's
cost data** (`completion_cost` / `cost_per_token`, spanning Claude/OpenAI/Gemini/local) rather
than a hand-maintained table.

## Components (file-grounded)
1. **Per-worker capture** — `agents/token_attribution.py` (`record_turn`, ~345-410): stop
   overwriting the scalar `model`; key attribution by `worker_id` (= subtask id; serial build =
   single implicit worker). Write a `workers` map in `token_usage.json` alongside the existing
   aggregate (aggregate preserved). Wire `worker_id`+`provider`+`model`+timestamps from
   `agents/parallel_integration.py` (~314) and the serial path.
2. **OTel instrumentation** — a `worker` span in `core/tracing_bootstrap.py` per subtask; a new
   `observability/metrics_otel.py` MeterProvider with `gen_ai.tokens` / `gen_ai.cost_usd` /
   `worker.duration_ms` instruments tagged `{provider, model, phase}` (bounded cardinality —
   never by task_id). Honor existing `OTEL_EXPORTER_OTLP_ENDPOINT` / Helm `otel.enabled`. Fix
   `completion.py` `_new_traceparent` to use the real span context so events link to traces.
3. **Event schema v1.3 (additive)** — `services/completion.py` +
   `services/completion_event.schema.json` + RFC-0001 doc bump: `usage.workers[]`,
   `usage.by_provider{}`, `usage.by_model{}`, optional `budget` block; new live sub-event with
   `phase:"worker"`, dedup key `(service, correlation_key, worker_id)`. Old consumers ignore the
   additive fields and the new phase.
4. **Live sub-event emission** — `agents/parallel_runner.py` wave completion + serial path emit a
   per-worker event as each worker finishes, via the existing best-effort webhook/sentinel path
   (a failed emit never fails the build — unchanged transport contract).
5. **CFactory ingest + cockpit** — `apps/backend/cfactory/models.py`/`store.py`: `ServiceState`
   gains `workers[]` + `by_provider`/`by_model`; ingest the `worker` phase into a live per-worker
   view; cockpit drill-down + provider rollup + soft-budget badge.
6. **Soft budget alert** — optional `budget_usd` in the contract; when a task's rolled-up cost
   exceeds it, set a warning flag on the terminal event + an OTel `budget.exceeded` metric + a
   CFactory badge. No abort.
7. **Dashboards-as-code** — Grafana dashboard JSON (cost-by-provider, tokens-by-model,
   worker-duration, budget-exceeded) + a documented `otel-collector` config + the Helm flag.

## Backward-compatibility (do not break the spine)
Every change is **additive**: scalar `usage.*` aggregate fields stay; serial single-model tasks
emit exactly as before (one implicit worker); the new event phase + fields are ignored by current
consumers; idempotency extended, not changed; OTel exports only when already enabled. No change
to provider dispatch, worktree isolation, the trusted-plan fast path, or merge logic. The PARR
seam-gate stays green.

## Phasing
- **P1**: per-worker capture + OTel spans/metrics + live sub-events + CFactory per-worker/rollup
  display.
- **P2**: dashboards-as-code (Grafana/collector) + soft budget alert.

### P1 dependency order (implementation)
1. Foundation — per-worker capture (`token_attribution`) + v1.3 additive schema
   (`completion.py` + schema) + back-compat tests. **Everything else depends on the event shape.**
2. OTel instrumentation (depends on capture).
3. Live sub-event emission (depends on schema).
4. CFactory ingest + display (depends on schema).

## Verification
- Unit: per-worker attribution (2 workers / 2 models → 2 records + correct rollups); v1.3 schema
  round-trip; sub-event dedup; back-compat (single-model task aggregate unchanged).
- Integration: a 2-worker parallel build with one Ollama + one Claude subtask → 2 live worker
  events + terminal rollup `by_provider{claude,ollama}`; Ollama `cost_usd=0`, tokens>0.
- OTel: with the endpoint set, assert worker spans + the 3 metrics export; cardinality bounded.
- CFactory: ingest worker events → per-worker view renders; budget badge fires over budget.
- Regression: AIFactory backend suite + the PARR seam-gate stay green.

## Critical files
- AIFactory: `agents/{token_attribution,parallel_runner,parallel_integration}.py`,
  `core/tracing_bootstrap.py`,
  `apps/web-server/server/observability/{tracing,metrics,+metrics_otel}.py`,
  `apps/web-server/server/services/{completion.py,completion_event.schema.json}`.
- Factory: `docs/rfc/0001-*.md` (v1.3 bump), `apis/completion-events.asyncapi.yaml`.
- CFactory: `apps/backend/cfactory/{models,store}.py`, cockpit frontend; Grafana JSON + collector config.

## Out of scope (YAGNI)
Hard budget abort; per-worker live events for PFactory/TFactory (their usage is still pending —
AIFactory-first); standing up the OTel backend in-cluster; wiring the dropped contract
`provider`/`agents` fields (separate concern).
