# R-007: HA options for Postgres and MinIO

> Factory#3690 (risk R-007, under the #310 compliance program). **Decided under
> owner delegation on 2026-11-16 (option A): the acceptance is recorded as AR-003
> in [risk-register.md](risk-register.md). The Security Owner's signature is
> still open.** The options below are the advice that decision rests on. Nothing
> here is deployed, and the draft acceptance in the last section is **UNSIGNED**.
>
> Artifacts: [intent](../../intent/2026-11-16-3690-r007-ha-options.md) ·
> [spec](../../spec/2026-11-16-3690-r007-ha-options.md) ·
> [plan](../../plan/2026-11-16-3690-r007-ha-options.md) ·
> [decision](../../spec/2026-11-16-3690-dr-encryption-offsite.md)

## Facts (each with its source)

| Fact | Source |
|---|---|
| `postgres` StatefulSet runs `replicas: 1` on `storageClassName: local-path` | factory-gitops `apps/postgres/manifests/manifests.yaml` |
| `minio` Deployment runs `replicas: 1`, PVC `minio-data` on `local-path` | factory-gitops `apps/minio/manifests/manifests.yaml` |
| Both k3d "nodes" are containers on one physical host; `nfs` is not a second failure domain | [dr-runbook.md](dr-runbook.md), "single-failure-domain problem" |
| No PodDisruptionBudget anywhere, by design: over one replica a PDB blocks node drain | factory-gitops `apps/README.md` (Factory#550) |
| Postgres dump daily 02:15 UTC; restore drill daily 04:15 UTC | factory-gitops `apps/backups/manifests`, `apps/backups/drill` |
| MinIO versioning on all three buckets; versioning is not a backup | [dr-runbook.md](dr-runbook.md) |
| Off-site copies of Postgres dumps (`apps/backups/offsite`, Factory#3681) and of the MinIO buckets (`apps/backups/minio-offsite`, Factory#3691) are written but **not deployed** | factory-gitops `apps/backups/*/cronjob.yaml` headers |

## What recovery looks like today

- **Postgres RPO:** up to 24h (daily dump). After host loss it is the newest
  complete dump that reached off-site storage, so it is **not met at all until
  the off-site copy is deployed** (the dumps live in the MinIO on the same host).
- **MinIO (evidence, artifacts):** versioning protects against an overwrite or
  delete. It does not protect against loss of the volume or the host. No copy
  exists off the host until `minio-offsite` is deployed.
- **RTO:** only the data step is measured (17s manual drill, 2026-08-10). The
  `postgres-restore-drill` CronJob is configured daily and records
  `rto_seconds`, but its first cluster result is still pending (see
  dr-runbook). Rebuilding a cluster, repointing services and validating are
  **unmeasured**; any RTO quoted today is an estimate (hours, not minutes).

## Options

"Needs verification" means the feasibility claim is not checked against the
product's current documentation or this cluster.

| Option | Gives | Cannot give | Cost class | Owner action |
|---|---|---|---|---|
| **A. Accept the risk** (AR-003 below) and deploy the off-site copies | Recovery path after host loss; no new moving parts | Availability; any HA | none beyond an S3 target | Decide; create the off-site Secret (below) |
| **B. Hourly dump** (same host) | Lower dump-age RPO target | Guarantee: needs each dump to finish (the job waits on MinIO, `concurrencyPolicy: Forbid`) and be copied off-site; no HA | none | Edit one schedule line (below) |
| **B2. WAL archiving / PITR** | Recovery to a moment between dumps (the register names PITR) | Availability; helps host loss only if the archive is off the host; needs an operator or archive tooling (needs verification) | engineering + storage | Choose tooling and archive target |
| **C. Single-host operator HA** (e.g. CloudNativePG 2-3 instances; MinIO distributed mode) | May survive a pod, process or rolling-upgrade failure, with failover | Host or disk loss: every replica is on the same physical disk. Reopens the PDB question (Factory#550). Needs verification | engineering, ops load | None recommended for R-007 |
| **D1. Standby Postgres on another host** (streaming replication or WAL shipping) | Second failure domain for Postgres; promotion manual or operator-driven | Automatic cross-host failover for the apps (they need repointing); needs verification | second host | Provide a host and network path |
| **D2. Multi-host Kubernetes** (k3d cannot span hosts, so this is a migration, e.g. k3s with agents on a second machine) | Real replicas across hosts | Cheap or quick: a platform migration | second host, migration effort | Provide hardware; decide migration |
| **D3. MinIO site replication to a peer on another host** | Second failure domain for objects | Needs verification of fit with the current single-deployment setup | second host | Provide a host |
| **D4. Copy to external S3** | Off-host backup of objects and dumps | HA: it is a backup (this is Factory#3681/#3691) | S3 storage fees | Provide S3 target (same as A) |
| **E. Managed Postgres and object store** | Provider SLA and replicas | Free of cost; data-residency review needed | recurring | Choose a provider |

What is **not** achievable on this cluster: any option that claims HA while
all replicas stay on this one host (C) does not lower the host-loss scenario
that R-007 describes. Only D or E add a second failure domain, and only
the owner can supply the host, network target or budget. Whether any option
reaches the register's target score of 6 is for the owner to reassess after it
is implemented and measured.

## Recommendation (advice)

A now (it is nearly finished: the code is written). B as an optional, cheap
tightening, stated as a target and measured by the existing drill. D (or E)
when a regulated tenant or customer contract needs SOC 2 A1.2. Skip C for
R-007; it is an availability-during-maintenance choice, not a host-loss one.

## Owner actions (copy-paste; none run by the agent)

1. Create the off-site target Secret (values come from you; never commit them):

   ```bash
   kubectl --context factory -n factory create secret generic offsite-s3-creds \
     --from-literal=OFFSITE_S3_ENDPOINT='<https://s3.example>' \
     --from-literal=OFFSITE_S3_BUCKET='<bucket>' \
     --from-literal=OFFSITE_S3_ACCESS_KEY='<access key>' \
     --from-literal=OFFSITE_S3_SECRET_KEY='<secret key>'
   ```

2. In factory-gitops, enable both copies, then let Argo CD sync:

   ```bash
   cd factory-gitops
   $EDITOR apps/backups/manifests/kustomization.yaml   # add under resources:
   #   - ../offsite
   #   - ../minio-offsite
   ```

3. Optional hourly dump (option B), in `apps/backups/manifests/manifests.yaml`:
   change `schedule: "15 2 * * *"` to `schedule: "15 * * * *"`, and move the
   off-site and drill schedules so they still follow a finished dump.
4. After the first off-site run and the first scheduled drill, record the
   measured `rto_seconds` in [dr-runbook.md](dr-runbook.md) (query in that file).
5. To accept, copy the text below into the Risk-acceptance log in
   [risk-register.md](risk-register.md) with the Security Owner's name and date.

## Draft acceptance AR-003 (UNSIGNED, not in the register)

- **Risk:** R-007. Postgres and MinIO are single instances on node-local
  storage on one physical host; no HA.
- **Proposed decision:** accept for six months while the off-site copies are
  deployed and measured. Residual score to be reassessed by the owner.
- **Compensating controls (evidence):** daily `postgres-backup` (factory-gitops
  `apps/backups/manifests/manifests.yaml`); daily `postgres-restore-drill`
  (`apps/backups/drill`, watched by `job-watchdog`); MinIO versioning on all
  buckets (`apps/minio/manifests/manifests.yaml`); off-site copies
  (`apps/backups/offsite`, `apps/backups/minio-offsite`) **once deployed**.
- **Review by:** 2027-05-16, or earlier on a revisit trigger.
- **Revisit triggers:** a regulated tenant or contract requiring A1.2; an
  availability requirement from a customer; a host or disk failure; a second
  host becoming available.
- **Sign-off:** Security Owner: ______ Date: ______
