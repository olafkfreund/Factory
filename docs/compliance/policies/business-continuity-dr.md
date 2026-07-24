# Business Continuity and Disaster Recovery

- **Domain:** Business continuity / DR (Factory#321)
- **Parent epic:** Factory#310
- **Frameworks addressed:**
  - ISO/IEC 27001:2022 — A.5.29 (information security during disruption), A.5.30 (ICT readiness for business continuity), A.8.13 (information backup), A.8.14 (redundancy of information processing facilities)
  - SOC 2 — A1.2 (environmental protections, backup, recovery infrastructure), A1.3 (recovery-plan testing)
  - SOX ITGC — computer-operations / backup-and-recovery controls supporting financial-reporting system availability and data integrity
  - PCI DSS v4.0 — 12.10.1 (incident/continuity plan; adjacent to backup and recovery obligations)
  - FFIEC — Business Continuity Management booklet (BIA, RTO/RPO, resilience, testing)
  - FedRAMP / NIST 800-53 Rev.5 — CP-9 (system backup), CP-10 (system recovery and reconstitution), CP-2 (contingency plan), CP-4 (contingency plan testing)

## Purpose

This document defines the business-continuity and disaster-recovery posture for the
Factory fleet's stateful control plane: the PostgreSQL database that holds durable
job-state for PFactory, AIFactory, TFactory, and CFactory, and the MinIO object store
that holds PARR artifacts and verification evidence. It states the honest current
reality (no backups exist today), the resulting gaps against the frameworks above, and a
phased, concrete remediation plan ending in an automated, tested restore that meets a
defined RTO and RPO.

This is the epic's **top-priority gap (Factory#310 gap #1)**. Loss of the Postgres
volume today is unrecoverable loss of all in-flight and historical job-state; loss of the
MinIO volume is unrecoverable loss of the evidence that underpins every verification
verdict and the tamper-evident audit anchor. Both currently sit on single node-local
disks with no copy anywhere.

## Current state (grounded)

As of 2026-07-24, verified against `factory-gitops/`.

### PostgreSQL — durable job-state store

Source: `factory-gitops/apps/postgres/manifests/manifests.yaml`.

- `StatefulSet postgres`, **`replicas: 1`**, image `postgres:16.4`, namespace `factory`.
- Storage: `volumeClaimTemplates` -> **`accessModes: ["ReadWriteOnce"]`, `storageClassName: local-path`, 10Gi**. This is a single node-local disk with a single writer.
- Hosts one database per service (`pfactory`, `tfactory`, `aifactory`, `cfactory`), each auto-migrated on startup via `alembic upgrade head`.
- The manifest header states plainly: *"Single replica on an RWO local-path PVC (single writer). HA Postgres (streaming replication / Patroni) is out of scope."* No read replica, no standby, no failover.
- The superuser password lives in `factory-secrets/POSTGRES_PASSWORD`, created **out-of-band and not committed** (no sealed-secrets / ESO). A cluster rebuild depends on an operator manually recreating it (tribal knowledge).
- **No backup of any kind:** no `pg_dump`/`pg_dumpall` CronJob, no `pg_basebackup`, no WAL archiving / PITR (no pgBackRest, wal-g, or Barman), no Velero, no restic. Confirmed by absence: the only `kind: CronJob` in the repo is `apps/cred-broker` (credential rotation), and there are zero matches for `velero|pgbackrest|pg_dump|wal-g|barman|restic`.

### MinIO — artifact and evidence store

Source: `factory-gitops/apps/minio/manifests/manifests.yaml`.

- `Deployment minio`, **`replicas: 1`**, `strategy: Recreate`, image `RELEASE.2025-04-08T15-41-24Z`, standalone (non-distributed) mode.
- Storage: PVC `minio-data`, **`accessModes: ["ReadWriteOnce"]`, `storageClassName: local-path`, 20Gi** — again a single node-local disk.
- Single bucket `factory-artifacts`; layout `<service>/<correlation_key>/<job_id>/<role>/...`.
- **Object lifecycle is expiry-only and no backup exists.** The `minio-create-bucket` Job installs ILM rules that *delete* `role=log` objects after 30 days. There is **no bucket versioning**, **no object-lock / WORM**, and **no replication** (no `mc replicate`, no site/bucket replication to any off-cluster target).
- Note a latent data-integrity risk: the manifest comment claims evidence is retained 90 days, but no 90-day evidence rule is actually installed — only the three 30-day `role=log` expiry rules exist. Retention intent and retention implementation diverge.

### Cluster storage reality

- Two storage classes exist: **`local-path`** (RWO, node-local, not replicated) and **`nfs`** (RWX, served by the in-cluster `nfs-ganesha` provisioner, `factory.io/nfs`).
- Both Postgres and MinIO use `local-path`, so their data is pinned to whichever node holds the disk. The cluster has spare nodes, but node-local storage means a node/disk loss loses the data outright — additional nodes add compute, not durability.
- The `nfs` RWX class is **not** a durability improvement either: its backing store is itself a **single `local-path` RWO 20Gi PVC** owned by the ganesha pod (`apps/nfs-provisioner/manifests/manifests.yaml`), so it is one more single point of failure, not a replicated volume.

### What is genuinely strong (and worth protecting)

The fleet already has a tamper-evident HMAC audit hash-chain with a daily signed,
air-gapped-verifiable anchor. That control assumes the underlying evidence and audit rows
survive — which today they would not. Backups are the missing foundation the existing
integrity controls silently depend on.

## Gaps

- **G1 — No backups anywhere (critical).** Neither Postgres nor MinIO has any backup. RPO is effectively infinite: a volume loss is total, permanent data loss. Fails ISO A.8.13, SOC 2 A1.2, SOX ITGC backup controls, NIST CP-9.
- **G2 — No tested restore.** With no backups there is no restore procedure and no restore has ever been exercised. Fails SOC 2 A1.3, FFIEC BCM testing, NIST CP-4. (An untested backup is not a control.)
- **G3 — Single-instance Postgres, no HA.** `replicas: 1` on RWO local-path. No standby, no failover; a pod/node failure is a hard outage until manual recovery. Weakens ISO A.8.14, NIST CP-10.
- **G4 — Single-instance MinIO, no versioning/replication.** Standalone MinIO on RWO local-path; lifecycle deletes objects with no version history and no second copy. Fails ISO A.8.13/A.8.14.
- **G5 — No defined RTO/RPO and no DR runbook.** No business-impact analysis, no recovery objectives, no documented reconstitution procedure. Cluster rebuild is tribal knowledge (out-of-band secret recreation, MinIO bucket recreation). Fails NIST CP-2, FFIEC BCM, SOC 2 A1.
- **G6 — Backups (once they exist) must be encrypted and off-cluster.** No at-rest encryption exists on the primary stores (epic gap #3); backups must not repeat that, and must survive loss of the whole cluster — i.e. leave the cluster. Ties to NIST CP-9(8), ISO A.8.13.
- **G7 — Retention intent vs implementation divergence.** MinIO lifecycle deletes at 30 days while comments claim 90-day evidence retention; evidence referenced by a verification claim can be purged before the claim is closed.

## Remediation plan

Phased so the highest-value, lowest-effort control (an off-cluster Postgres backup) lands
first. Each phase is independently shippable.

### Phase 1 — Automated off-cluster Postgres backups (closes most of G1; days)

- Add a `CronJob` (namespace `factory`, image `postgres:16.4` so `pg_dump` matches the server version) that runs `pg_dumpall` (or per-database `pg_dump --format=custom` for the four service DBs) on a schedule (start hourly; tune with RPO in Phase 5).
- Pipe each dump through age/gpg encryption, then ship it **off-cluster** — to an external S3/object bucket outside this cluster (not the same MinIO), or via `restic` to an external repository. Off-cluster is mandatory: a backup on the same node the DB lives on does not survive the disaster it exists for.
- Apply retention: e.g. 7 daily, 4 weekly, 3 monthly. Emit a success/failure metric and alert on missed runs (wire to the existing observe/Prometheus stack).
- Rationale for `pg_dumpall` over pgBackRest as the first step: it needs no operator, no new storage layout, and no image change — it is the smallest diff that ends the "zero backups" state. WAL/PITR comes in Phase 3 when RPO must drop below the dump interval.

### Phase 2 — MinIO durability: versioning + off-cluster replication (closes G4, G7; days)

- Enable **bucket versioning** on `factory-artifacts` (`mc version enable`) so overwrites/deletes are recoverable.
- Add **bucket replication** (`mc replicate add`) to an off-cluster S3-compatible target, or a scheduled `mc mirror` CronJob, so evidence has a second copy off the cluster.
- Fix G7: replace the log-only 30-day expiry with an explicit tiered ILM policy — `role=log` 30d, `role=evidence` retained to its actual required floor (>=90d, aligned to the longest verification-claim lifetime), and consider **object-lock (WORM)** on evidence prefixes so audit evidence is immutable for its retention window.

### Phase 3 — HA Postgres and PITR (closes G3, deepens G1; weeks)

- Adopt a Postgres operator that provides streaming replication, automated failover, and continuous WAL archiving to object storage in one package — **CloudNativePG** is the recommended target (declarative, GitOps-friendly, backups + PITR to S3 built in). This supersedes the Phase 1 CronJob for RPO but keep the CronJob until PITR restores are proven.
- Run at least a primary + one synchronous/asynchronous standby so a pod/node loss is a failover, not an outage.
- Alternatively, if HA is deferred, **document and formally accept the single-writer risk** with sign-off (an explicit risk-acceptance in the Governance register satisfies the assessor requirement to have *decided*, not defaulted).

### Phase 4 — Resolve single-node storage stranding (supports G3/G4; weeks)

- Migrate the Postgres and MinIO PVCs off single-node `local-path` onto genuinely redundant storage. Note the current `nfs` RWX class is **not** redundant (single ganesha pod on a single local-path PVC); redundancy requires either replicated storage (e.g. a distributed CSI / real NAS) or the operator-level replication from Phase 3. Do not treat "moved to nfs" as "made durable."

### Phase 5 — Define RTO/RPO, write the DR runbook, and test restores (closes G2, G5, G6)

- Run a lightweight **business-impact analysis** and set targets. Proposed initial commitments, to be ratified: **RPO <= 1 hour** (achievable with hourly dumps in Phase 1, tighter with WAL/PITR in Phase 3) and **RTO <= 4 hours** for full control-plane reconstitution.
- Write a **DR runbook** in `Factory/docs/compliance/` (or `factory-gitops/docs/`) covering: cluster/namespace rebuild, out-of-band secret recreation (`factory-secrets`, `minio-creds`), MinIO bucket recreation, Postgres restore, MinIO evidence restore, and post-restore validation (per-service `job_states` row counts, audit hash-chain re-verification against the daily anchor).
- Add a **scheduled restore test**: a periodic (at minimum quarterly, ideally an automated weekly CronJob) restore of the latest backup into a scratch namespace, asserting integrity (row counts, a sample evidence object hash, audit-chain verify), producing a dated restore-test report as evidence. Ensure backup encryption keys (G6) are themselves backed up and their recovery is part of the drill.

## Acceptance criteria

- [ ] Automated Postgres backups run on a schedule, are encrypted, and are stored **off-cluster**; backup success/failure is monitored and alerts on miss.
- [ ] Backup retention policy is defined and enforced (e.g. 7 daily / 4 weekly / 3 monthly).
- [ ] MinIO `factory-artifacts` has **versioning enabled** and an **off-cluster replica/mirror**; evidence-prefix retention matches documented requirements (>=90d) and is no longer silently expired at 30 days.
- [ ] Postgres runs HA (primary + standby with automated failover) **or** the single-writer risk is formally accepted and recorded in the risk register.
- [ ] Postgres and MinIO primary volumes no longer depend on a single node-local disk (or the residual risk is documented and accepted).
- [ ] **RTO and RPO are defined, documented, and ratified.**
- [ ] A **DR runbook** exists covering full control-plane reconstitution (secrets, buckets, DB and object restore, post-restore validation).
- [ ] **A restore has actually been tested** end-to-end into a scratch environment, with integrity validated (job-state row counts, evidence object hash, audit hash-chain re-verified) and a dated restore-test report retained.
- [ ] The restore test is **scheduled and recurring** (at least quarterly), not one-off.

## Evidence artifacts

Artifacts an assessor can request to confirm the controls operate:

- **Backup manifests** — the Postgres backup `CronJob` (or CloudNativePG `Backup`/`ScheduledBackup`) and MinIO versioning/replication configuration, in `factory-gitops`.
- **Backup success logs / metrics** — job run history and the Prometheus/observe alert rules for missed backups; sample of recent successful runs.
- **Retention policy** — the documented retention schedule and the ILM/lifecycle rules implementing it.
- **RTO/RPO record** — the ratified objectives and the BIA that justifies them (in the Governance risk register / this policy).
- **DR runbook** — the reconstitution procedure, versioned and dated.
- **Restore-test reports** — dated reports from each restore drill: what was restored, elapsed time (vs RTO), data currency (vs RPO), integrity checks performed (row counts, evidence hash, audit-chain verification) and their results.
- **Risk acceptance (if applicable)** — signed acceptance of the single-writer Postgres or single-node-storage residual risk.
