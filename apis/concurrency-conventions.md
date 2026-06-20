# Factory Concurrency Conventions (RFC-0016 Phase 1 foundation)

> Normative conventions for running many PARR jobs concurrently. Implements
> [RFC-0016](../docs/rfc/0016-horizontal-concurrent-execution.md) issue #189.
> Consumed by PFactory, AIFactory, TFactory. Companion artifact:
> [`job-state.schema.json`](./job-state.schema.json).

This document defines the three shared seams that let the fleet scale past one
pod: (1) **shared job state** in Postgres, (2) the **object-store interface** for
workspaces and artifacts, and (3) the **Job-dispatch + result-callback contract**
for Phase 2 (k8s Job-per-task). Phase 1 fixes (admission control, runtime
isolation, event-loop offload) are already merged; this foundation makes their
state **durable** and unblocks multi-replica + Phase 2.

## 1. Shared job state (Postgres)

Each service MUST persist one row per job conforming to `job-state.schema.json`,
replacing the per-pod in-memory stores (PFactory `_sessions`, AIFactory/TFactory
`running_tasks`) and pod-local SQLite/`emptyDir`.

- **Key:** `job_id` (service-assigned). **Thread `correlation_key`** (RFC-0001
  GitHub issue number) so a job is joinable across services and in CFactory.
- **Lifecycle:** write `lifecycle_state` from the canonical set in
  [`status-taxonomy.json`](./status-taxonomy.json) (`queued · running · review ·
  done · failed · stuck`), keeping the raw `service_status` alongside. `queued`
  is the RFC-0016 admission state.
- **Durability rules:**
  - The **admission cap + queue** read live counts from this table, not memory —
    so the cap survives a control-plane restart and is consistent across replicas.
    A new control-plane replica reconstructs in-flight state by querying
    `lifecycle_state in (queued, running)` for its `service`.
  - Every terminal transition (`done`/`failed`) MUST set `ended_at` and `result`;
    `failed`/`stuck` MUST set `error` (never-overclaim, RFC-0001a/0006).
  - Writers MUST be safe under concurrency: use a transaction (or
    `SELECT ... FOR UPDATE`) when granting a slot / advancing state so two
    replicas cannot exceed the cap or double-start a `job_id`.
- **Connection:** services already accept `DATABASE_URL`; concurrency state lives
  in the same Postgres. The in-memory path remains a fallback only when
  `DATABASE_URL` is unset (single-pod dev), and that mode MUST log that it is not
  multi-replica safe.

## 2. Object-store interface (workspaces + artifacts)

Workspaces and artifacts MUST move off `ReadWriteOnce` `local-path` PVCs (which
pin a service to one pod/node) to object storage (S3-compatible: AWS S3, MinIO,
GCS) or, where a shared filesystem is required, an RWX volume.

- **Bucket:** one artifacts bucket per environment, e.g. `factory-artifacts`.
- **Key layout (stable, joinable):**
  `<service>/<correlation_key>/<job_id>/<role>[/<path>]`
  - `service ∈ {pfactory, aifactory, tfactory}`; `role ∈ {workspace, build,
    test-report, evidence, log}` (matches `artifacts[].role` in the schema).
  - Example: `aifactory/482/9d2c…/build/app.tar.zst`.
- **References, not blobs:** the job-state `result`/`artifacts[]` carry **URIs**
  only; never inline large content into Postgres or the contract.
- **Lifecycle:** apply a retention/TTL policy per `role` (e.g. logs 30d, evidence
  90d); evidence referenced by a VAL claim (RFC-0006) MUST outlive the claim.
- **Workspace handoff:** a Phase-2 Job clones/fetches its inputs and writes
  outputs to its `<…>/workspace` and `<…>/build` keys; the control plane and
  CFactory read results from object storage + Postgres, never from a shared PVC.

## 3. Job-dispatch + result-callback contract (Phase 2)

For Phase 2 the control plane stops running work in-pod and instead **dispatches
one k8s Job per task**. This section defines that seam (reused across services;
builds on RFC-0005 sandbox + TFactory `kube_sandbox`).

- **Dispatch:** on accepting a contract, the control plane (a) writes a
  `job-state` row `lifecycle_state=queued`, (b) creates a k8s Job named
  `factory-<service>-<job_id-short>` with the contract mounted/passed and the
  artifacts bucket creds, and (c) records `worker_ref={kind:"k8s-job", namespace,
  job_name}`. Admission/KEDA (Phase 3) governs how many Jobs run at once.
- **Execution:** the Job pod runs the existing entrypoint (`run.py` for
  AIFactory/TFactory; PFactory `process()` or a pool worker), isolated network +
  resources. It updates its own `job-state` row (`running` → terminal) and writes
  artifacts to object storage.
- **Result callback (idempotent):** the Job reports terminal state by writing the
  `job-state` row (`done`/`failed`, `result`, `ended_at`, `usage`) AND emitting
  the RFC-0001 completion event ([`completion-events.asyncapi.yaml`](./completion-events.asyncapi.yaml)).
  The control plane reconciles by **polling Postgres**, so a missed event never
  strands a job. Reporting MUST be idempotent (keyed by `job_id` + terminal
  state) so a retried Job does not double-emit.
- **Reaping:** the control plane (or a reconciler) marks a `job-state` row
  `failed` with `error` if its Job disappears/exceeds deadline without a terminal
  write — closing the "lanes pending, no verdict" class of stall (TFactory #464)
  at the orchestration layer.

## 4. Adoption

Per-service issues consume this foundation: PFactory #217 (`_sessions` →
Postgres), AIFactory #668 (`running_tasks` + queue → Postgres), TFactory #465
(state → Postgres), Factory #190 (object storage / RWX), and the Phase-2 Job
issues (#191/#671/#466/#218). This document + `job-state.schema.json` are the
single source of truth those implementations follow.
