# Business Continuity Policy

- **Policy owner:** Security Owner (CISO function) — see [roles.md](../roles.md)
- **Applies to:** The fleet's stateful systems and the ability to recover them
- **Review cadence:** Annually, and after any restore test or DR event
- **Frameworks:** ISO/IEC 27001:2022 A.5.29-.30, A.8.13-.14; SOC 2 A1.2-.3;
  SOX ITGC (backup/recovery); NIST CP-2/CP-4/CP-9/CP-10

Control detail and current-state grounding live in
[business-continuity-dr.md](business-continuity-dr.md) (Factory#321), the fleet's
highest-priority open risk.

## Purpose

To ensure the fleet can recover its state and resume operation after data loss,
corruption, or infrastructure failure, within defined objectives, and to close the
current absence of any backup.

## Scope

The stateful systems: the Postgres job-state store (four databases, single instance,
RWO local-path volume), the MinIO object store (artifacts and verification evidence,
single instance), Redis, and Keycloak. Also the ability to rebuild the k3d cluster and
its configuration.

## Objectives

- **RPO (proposed): 1 hour.** No more than one hour of data may be lost.
- **RTO (proposed): 4 hours.** Service is restored within four hours of a decision to
  recover.

These objectives are proposed pending a business-impact analysis; until backups exist
the actual RPO is unbounded, which is why this is the program's top risk (R-001).

## Policy statements

1. **Backups are required.** Postgres and MinIO must be backed up on a schedule that
   meets the RPO. Today there are no backups of either — no `pg_dump`/`pg_basebackup`/WAL
   archiving for Postgres, and MinIO has expiry-only lifecycle rules with no versioning
   or replication. Introducing an off-cluster encrypted `pg_dumpall` job and MinIO
   versioning/replication is Wave 2 remediation (risk R-001).
2. **Backups are off-cluster and encrypted.** A backup on the same single node it
   protects is not a backup. Backups are stored off-cluster and encrypted in transit and
   at rest.
3. **Restore is tested.** A backup that has not been restored is a hope, not a control.
   A restore test is performed at least quarterly and the result recorded as evidence.
4. **A DR runbook exists.** Cluster and data-store recovery must be documented, not
   tribal knowledge. The runbook covers rebuild order (cluster, secrets, data stores,
   applications) and references the operational
   [incident-response runbook](incident-response.md) for coordination during a DR event.
5. **Resilience is a goal, not just recovery.** Single-instance Postgres and MinIO on
   node-local storage are single points of failure. HA Postgres with point-in-time
   recovery (for example CloudNativePG) and redundant object storage are Wave 3 targets;
   until then the single-instance risk is documented and, if accepted, signed off in the
   register.
6. **The audit chain depends on this.** The tamper-evident audit hash-chain and its
   daily anchor assume the underlying data survives. Without backups that assumption is
   false; recovering the audit store is in scope of this policy.

## Roles and responsibilities

- **Control owner (BC/DR)** — implements and schedules backups, owns the DR runbook, and
  runs the restore tests.
- **Incident Commander** — directs recovery during a declared DR event.
- **Security Owner** — owns the policy, sets RPO/RTO after the BIA, and signs off any
  acceptance of the single-instance risk.

## Related controls

- [business-continuity-dr.md](business-continuity-dr.md) — domain assessment and evidence
- [incident-response-policy.md](incident-response-policy.md) — coordination during recovery
- [encryption-key-mgmt.md](encryption-key-mgmt.md) — backup encryption
- [risk-register.md](../risk-register.md) — R-001 (no backups), R-007 (single-instance data stores)
