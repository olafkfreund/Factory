# Disaster recovery: backup, restore, RTO/RPO

> Factory#321 (business continuity / DR, under the #310 compliance program)
>
> **Frameworks:** ISO/IEC 27001 A.5.29–30, A.8.13 · SOC 2 Availability **A1.2–A1.3**
> · SOX ITGC (backup & recovery) · FFIEC BCM · FedRAMP CP
>
> A1.3 and A.5.30 require the recovery procedure to be **tested**, not merely
> defined. The drill below is that evidence.

## What is protected, and what is not

| Asset | Backed up | Where the backup lives |
|---|---|---|
| Postgres (durable job-state, all 5 databases) | **yes** — daily `pg_dumpall` | MinIO `factory-backups/postgres/` |
| MinIO object store (artifacts, **audit evidence**) | **not yet**: backup written, disabled until the off-site target exists (Factory#3681, Factory#3691) | `apps/backups/minio-offsite` in factory-gitops, to the off-site S3 bucket |
| Keycloak, Redis, per-service PVCs | **no** | — |

`postgres-backup` is a CronJob at `15 2 * * *` (02:15 UTC): an init container runs
`pg_dumpall -h postgres -U factory --clean | gzip -9`, and the main container
uploads it with `mc`. The declared `backups-14d` lifecycle rule expires dumps after 14 days and
noncurrent versions after 7 (as declared; the `minio-create-bucket` Job's read-back checks the rule ID).

## Scheduled restore drill (Factory#3691)

The 2026-08-10 drill below was manual and proved the restore once. Since
Factory#3691 the `postgres-restore-drill` CronJob (factory-gitops
`apps/backups/drill`, daily 04:15 UTC, after the 02:15 dump) repeats it every
day:

1. fetches the newest `postgres-backup` dump from MinIO;
2. rejects it if it is not valid gzip, older than 25h, future-dated, or cut
   short (no `pg_dumpall` end marker);
3. restores it into a throwaway Postgres inside the job pod (unix socket only;
   the live database is never touched, and nothing is left behind: the cluster
   is an `emptyDir` that dies with the pod);
4. checks the restored data: all five databases present, the four service
   databases with tables, rows present, no restore errors other than the three
   that every fresh-cluster replay gives,
   `pg_dump -s` works per database; per-database row counts are recorded;
5. writes the result to `factory-evidence/control-plane-push/restore-drill/<UTC>.json`
   and to the OpenObserve `job_health` stream (`source = 'restore-drill'`);
6. fails the Job when any step fails. `job-watchdog` covers it like every other
   CronJob: a failing drill is `failing`, a drill that stops running is
   `stale`, and both open an issue.

Read the latest result:

```sql
SELECT _timestamp, status, rto_seconds, fetch_seconds, initdb_seconds,
       restore_seconds, check_seconds, dump, dump_age_seconds, databases,
       tables, rows, problems
FROM "job_health" WHERE source = 'restore-drill' ORDER BY _timestamp DESC
```

An assessor asking "when did the restore last run, and did it work" gets that
query, or `mc ls fac/factory-evidence/control-plane-push/restore-drill/`.

**What the drill does not prove:** that live row counts match (RPO makes them
differ by design; counts are recorded for a human), that services work against
the restored database, or anything about MinIO restore. It proves the newest
dump is complete, fresh and replayable.

## Measured RTO and RPO

From the drill of **2026-08-10** (see Evidence). These are measurements, not targets:

| Metric | Measured | Notes |
|---|---|---|
| Fetch dump from MinIO | **< 1s** | 34 KiB gzipped |
| **Restore into a running Postgres** | **17s** | 52 tables, 5 databases |
| Total drill job | **24s** | fetch + restore |
| **RPO** | **up to 24h** | daily 02:15 schedule; the drill's dump was 8h33m old |
| Demonstrated data delta | **1 row** | `pfactory.job_states` 102 live vs 101 restored |

**Do not quote 24s as the RTO.** It is the *data restore step only*.

**Full-path RTO (Factory#3691).** Every drill run records `rto_seconds`: the time
from starting the fetch to the end of validation, covering fetch, standing up a
fresh Postgres (`initdb` and start), replay and the checks, with the phase
split beside it. It does **not** include pod scheduling or the first image pull, nor
the manual steps of a real recovery: repointing services at the replacement
Postgres, scaling writers back up, and application validation. Those are listed
in the procedure below and remain unmeasured; a stated RTO must add an
estimate for them and say so.

First value of record: **pending the first scheduled run on the cluster.**
After the first run, read `rto_seconds` with the query above and record it
here with the date. The drill was verified before release in CI against a
synthetic five-database cluster only; that number is not an RTO.

## The single-failure-domain problem (READ THIS FIRST)

**Every copy of everything is on one machine.** Measured 2026-08-10:

| Volume | Node | Storage class |
|---|---|---|
| `data-postgres-0` (the database) | `k3d-factory-server-0` | `local-path` |
| `minio-data` (evidence store **and every Postgres backup**) | `k3d-factory-server-0` | `local-path` |
| `nfs-provisioner-backing` (backs the whole `nfs` class) | `k3d-agent-0-0` | `local-path` |

- The backups are uploaded **into MinIO**, which sits on the same node, on the
  same node-local storage class, as the database they protect.
- `local-path` uses `reclaimPolicy: Delete`, so deleting a PVC destroys the data.
- The **`nfs` storage class is not a second failure domain.** It is served by an
  in-cluster `nfs-provisioner` Deployment whose export is itself a `local-path`
  PVC. It provides RWX semantics, not durability.
- Both k3d "nodes" are containers on **one physical host**, reporting the same
  kernel and an empty `machineID`.

So losing that host — or that volume — loses the database, every backup of it,
and the entire audit-evidence store **in one event**. There is no in-cluster
target that fixes this; an off-box destination is required and is a decision
about infrastructure, not code. Tracked on Factory#3681.

The `nfs`-is-not-durable half was already recorded in
[`policies/business-continuity-dr.md`](policies/business-continuity-dr.md)
("its backing store is itself a single `local-path` RWO 20Gi PVC"). It is
repeated here because it was measured independently on 2026-08-10 while
evaluating `nfs` as a backup target — and because the recommendation to use it
was made anyway. A finding written down in one document does not stop the next
person reaching the opposite conclusion; that is the argument for the runbook
carrying it too.

## Restore procedure

### The gotcha that will cost you an hour at 3am

`pg_dumpall` includes the **source cluster's role definitions**, so partway
through the restore an `ALTER ROLE factory ... PASSWORD` executes and replaces
the target's password with production's. Every subsequent `\connect` in the same
restore then authenticates with the *source* credential.

Observed on the first drill attempt — the restore stopped at the first database
boundary, **after** `DROP DATABASE` and `CREATE DATABASE` had already run:

```
UPDATE 1
DROP DATABASE
CREATE DATABASE
ALTER DATABASE
\connect: ... FATAL:  password authentication failed for user "factory"
```

That leaves a **half-rebuilt cluster**, and it presents as an auth error, which
reads like a misconfiguration rather than a restore that stopped halfway.

**Do one of these before restoring:**

- give the target `POSTGRES_HOST_AUTH_METHOD=trust` (fine for a scratch target,
  never for anything reachable), or
- authenticate the restore with the **source** cluster's `POSTGRES_PASSWORD`
  (`factory-secrets/POSTGRES_PASSWORD`).

### Steps

1. **Stand up a target.** For a drill use a scratch namespace; for a real
   recovery this is the replacement Postgres.

   ```
   kubectl --context factory create namespace dr-drill
   kubectl --context factory -n dr-drill run pg-restore-target \
     --image=postgres:16.4@sha256:e62fbf9d3e2b49816a32c400ed2dba83e3b361e6833e624024309c35d334b412 \
     --env=POSTGRES_USER=factory --env=POSTGRES_PASSWORD=drill-throwaway-only \
     --env=POSTGRES_DB=postgres --env=POSTGRES_HOST_AUTH_METHOD=trust \
     --labels=run=pg-restore-target
   kubectl --context factory -n dr-drill expose pod pg-restore-target --port=5432
   ```

2. **Fetch and restore.** Run the Job in `docs/compliance/dr-restore-drill.yaml`
   — it lives in the `factory` namespace because that is where `minio-creds` is,
   and it targets the scratch service.

   ```
   kubectl --context factory apply -f docs/compliance/dr-restore-drill.yaml
   kubectl --context factory -n factory logs -l job-name=dr-restore-drill -c restore
   ```

   Two things the manifest gets right that a hand-rolled version will not:

   - the restore container runs under **`/bin/bash`, not `/bin/sh`**. The
     postgres image's `sh` is **dash**, which has no `pipefail`, and
     `set -euo pipefail` aborts immediately with
     `set: Illegal option -o pipefail`. This is the same trap that once made
     `postgres-backup` silently never run.
   - the object is located with `mc find ... | sort | tail -1`, not
     `mc ls | awk`. The `mc` image ships no `awk` (the failure mode there is a
     silently empty variable), and **`mc find` does not guarantee ordering** —
     without the explicit `sort` this can restore an *arbitrary* dump and still
     report success. The names embed an ISO-8601 UTC stamp
     (`factory-cluster-YYYYMMDDThhmmssZ.sql.gz`), so they sort lexicographically
     in time order.

3. **Verify against the artefact, never the exit code.** The Job runs psql with
   `ON_ERROR_STOP=0` so a partial restore still exits 0. Compare row counts:

   ```
   Q="select table_schema||'.'||table_name from information_schema.tables
      where table_type='BASE TABLE'
        and table_schema not in ('pg_catalog','information_schema') order by 1;"
   # run per database against BOTH clusters and diff the results
   ```

4. **Tear down** (drill only): `kubectl --context factory delete namespace dr-drill`

## Evidence — drill of 2026-08-10

- **Dump restored:** `factory-cluster-20260810T021505Z.sql.gz`, 34 KiB gzipped,
  taken 02:15:05Z, restored 10:48Z (age **8h 33m**).
- **Result:** 52 of 52 tables restored across all 5 databases; roles restored
  (`factory`); **zero** error lines in the restore output.
- **Row counts:** identical on every table except `pfactory.job_states`
  (live 102, restored 101) — one row written after the backup was taken. That is
  RPO, not data loss.
- **Production untouched:** the drill ran against a scratch namespace throughout;
  `pfactory.job_states` on the live cluster read 102 before and after.
- **First attempt failed** on the role-password behaviour above. Recorded rather
  than hidden: it is the single most useful thing this drill produced, and it
  would have surfaced during a real outage instead.

## Outstanding (Factory#321 closed 2026-08-10)

- [ ] **Off-box backup destination (Factory#3681)** — the single-failure-domain problem above.
      Needs an infrastructure decision (second machine, NAS, or real S3).
- [x] **MinIO versioning** — enabled on all three buckets.
- [~] **MinIO backup (Factory#3691)** — versioning is not a backup. The backup
      CronJob `minio-backup-offsite` (`factory-artifacts`, `factory-evidence`,
      never deletes or overwrites at the destination, verifies every object)
      is written and tested but **not deployed**. **Owner action:** provide the
      off-site S3 target and create the `offsite-s3-creds` Secret (Factory#3681),
      then add `- ../minio-offsite` to `apps/backups/manifests/kustomization.yaml`
      in factory-gitops. `factory-backups` has its own copy (Factory#3681).
- [~] **Full-path RTO (Factory#3691)** — measured by every scheduled drill run
      (see above); record the first value once it exists. The manual recovery
      steps (repointing, scale-up, app validation) remain unmeasured.
- [ ] **HA Postgres (Factory#3690)**, or a written single-writer risk acceptance.
      Options, RPO/RTO and a draft acceptance: [r007-ha-options.md](r007-ha-options.md).
- [x] **Scheduled re-drill (Factory#3691)** — `postgres-restore-drill`, daily,
      results in `job_health` and `factory-evidence`, watched by `job-watchdog`.
