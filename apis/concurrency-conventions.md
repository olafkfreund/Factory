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

### 1a. Autoscaling the control plane on queue depth (KEDA)

Because the admission queue is **durable in Postgres**, the control plane scales
on it directly — no separate broker. KEDA's PostgreSQL scaler polls

```sql
SELECT count(*) FROM job_states WHERE service = '<svc>' AND lifecycle_state = 'queued'
```

and scales the service's Deployment between `minReplicaCount: 1` (never scale to
zero — the API is always-on) and a bounded `maxReplicaCount`, targeting ~1-2
queued jobs per replica. The scaler reuses the **same Postgres** connection the
service uses (a `TriggerAuthentication` reading `DATABASE_URL` from the service's
DB Secret).

**Separation of concerns — KEDA does NOT bound concurrency, the in-app cap does.**
KEDA only moves *replica count* in reaction to queue depth. The **hard global
concurrency cap** is enforced **in-app** at admission (`MAX_CONCURRENT_TASKS` /
`PFACTORY_MAX_CONCURRENT_PLANS`), and because a slot is granted inside the
`SELECT ... FOR UPDATE` transaction above, the cap holds **across replicas** — two
pods cannot jointly exceed it. So: KEDA scales out to drain the queue faster;
the per-replica + global admission cap bounds the actual work in flight; excess
work stays `queued` (backpressure, no OOM).

**A service is only safe to scale >1 once its state is in shared Postgres AND it
has no pod-local fan-out.** A service with a WebSocket fan-out that keeps
per-connection state in-pod (e.g. AIFactory's rmux Live Agent Console) MUST stay
capped at `maxReplicaCount: 1` until that fan-out runs over a shared bus
(Redis pub/sub); KEDA may be wired for it but capped. The Deployment's hard
`replicas:` pin must also be removed for the KEDA-managed HPA to own replica count.

Cluster wiring (operator install + per-service `ScaledObject`s) lives in
`factory-gitops` (`apps/keda/`). RFC-0016 #192.

## 2. Object-store interface (workspaces + artifacts)

Workspaces and artifacts MUST move off `ReadWriteOnce` `local-path` PVCs (which
pin a service to one pod/node) to object storage (S3-compatible: AWS S3, MinIO,
GCS) or, where a shared filesystem is required, an RWX volume.

- **Bucket:** one artifacts bucket per environment, e.g. `factory-artifacts`.
- **Key layout (stable, joinable):**
  `<service>/<correlation_key>/<job_id>/<role>[/<path>]`
  - `service ∈ {pfactory, aifactory, tfactory}`; `role ∈ {workspace, build,
    test-report, evidence, log, doc}` (matches `artifacts[].role` in the schema;
    `doc` = rendered plan/spec/audit markdown).
  - Example: `aifactory/482/9d2c…/build/app.tar.zst`.
- **References, not blobs:** the job-state `result`/`artifacts[]` carry **URIs**
  only; never inline large content into Postgres or the contract.
- **Endpoint + credentials (env):** the store is reached over an S3 API. Services
  read connection config from the environment (set on the pods by the cluster
  MinIO deploy in `factory-gitops`); the shared client is
  [`scripts/artifact_store.py`](../scripts/artifact_store.py):
  - `S3_ENDPOINT` — e.g. `http://minio.factory.svc.cluster.local:9000`
  - `S3_BUCKET` — default `factory-artifacts`
  - `S3_ACCESS_KEY` / `S3_SECRET_KEY` — credentials (from the `minio-creds` Secret)
  - `S3_REGION` — default `us-east-1` (MinIO ignores it; boto3 requires a value)
- **Lifecycle:** apply a retention/TTL policy per `role` (e.g. logs 30d, evidence
  90d); evidence referenced by a VAL claim (RFC-0006) MUST outlive the claim.
- **Workspace handoff:** a Phase-2 Job clones/fetches its inputs and writes
  outputs to its `<…>/workspace` and `<…>/build` keys; the control plane and
  CFactory read results from object storage + Postgres, never from a shared PVC.
- **Workspace transfer via object storage (RFC-0017 §2.3) replaces the RWO
  co-mount for multi-node.** The shared client packs a worktree to the
  `<…>/workspace` key as a single `workspace.tar.gz` and restores it on the far
  side: `pack_workspace(store, ref, src_dir) -> uri` and
  `unpack_workspace(store, uri_or_ref, dest_dir)` in
  [`scripts/artifact_store.py`](../scripts/artifact_store.py). Extraction is
  path-traversal-guarded (absolute / `..` / escaping-link members are rejected
  before anything is written). The dispatcher passes the packed URI to the Job as
  `WORKSPACE_URI` (see [`scripts/job_dispatch.py`](../scripts/job_dispatch.py));
  the Job `unpack_workspace`s into `/work` at start, runs, then `pack_workspace`s
  its outputs back. Because the worktree no longer rides an RWO `local-path` PVC
  that pins it to one node, the Job can be scheduled on any node — the last
  blocker to multi-node scale-out. The RWO co-mount remains the single-node path;
  removing it from the live Deployments/Jobs is the `factory-gitops` rollout, out
  of scope for the reference lib.

## 3. Job-dispatch + result-callback contract (Phase 2)

For Phase 2 the control plane stops running work in-pod and instead **dispatches
one k8s Job per task**. This section defines that seam (reused across services;
builds on RFC-0005 sandbox + TFactory `kube_sandbox`).

- **Dispatch:** on accepting a contract, the control plane (a) writes a
  `job-state` row `lifecycle_state=queued`, (b) creates a k8s Job named
  `factory-<service>-<job_id-short>` with the contract mounted/passed and the
  artifacts bucket creds, and (c) records `worker_ref={kind:"k8s-job", namespace,
  job_name}`. Admission/KEDA (Phase 3) governs how many Jobs run at once.
- **Job image = thin nix-base (RFC-0016 §4.1, RFC-0005 Tier A):** the Job runs the
  `tfactory-runner-nix` image (nix only, no bundled toolchains) and materializes the
  task's toolchain via `nix develop path:/work#default` against the per-task
  `flake.nix` generated from the contract `environment` block. Mount the warm RWX
  `/nix/store` PVC so toolchains are cached across Jobs. Toolchains MUST come from
  Nix, not from a fat image.
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
