---
layout: default
title: "Enterprise scale"
permalink: /guides/enterprise-scale/
---

# Enterprise scale

**User story.** As a platform owner in a regulated organisation, I want many
teams to use the factory concurrently with evidence of what happened, so that
throughput does not come at the cost of being able to answer an auditor.

---

## What is shipped

| Concern | Capability |
|---|---|
| Concurrency | task execution as isolated Kubernetes Jobs, autoscaled |
| Multi-tenancy | tenant claim carried from the identity provider into requests |
| Evidence | audit log with scheduled forwarding and anchoring |
| Access | OIDC via Keycloak in front of the cockpit |

---

## Concurrency: what actually limits you

Nodes are usually not the constraint. Storage is. Task workspaces on
`ReadWriteOnce` volumes bind to one node, and a pod scheduled elsewhere cannot
attach. An `ReadWriteMany` class (NFS here) removes that ceiling.

**Before scaling out, check which constraint you are actually hitting.** Adding
nodes to a storage-bound cluster changes nothing and costs money.

```bash
kubectl get storageclass
kubectl get pvc -n factory
```

---

## Tenancy

Tenant identity comes from the identity provider as a claim and is injected
into requests as a header. Two consequences:

- **A machine client needs a token carrying the same claims a human's does.**
  Service-account tokens do not have an email or tenant by default, and a proxy
  keying sessions on those claims will reject them. Give the machine identity
  explicit claim mappers rather than relaxing the proxy.
- **Give each automation its own client.** A mapper on a shared client applies
  to every token it issues, including real users'. A hardcoded email on the
  human client would override genuine ones.

---

## Evidence and audit

Audit records are collected and forwarded on a schedule. For an audit you need
three things to be true, and the third is the one that usually fails:

1. The events are recorded.
2. They are retained long enough.
3. **The collection is still running.**

A scheduled forwarder that has been failing quietly produces a gap nobody
notices until someone asks for the records. Check the schedule's recent runs,
not just its existence:

```bash
kubectl get cronjobs -n factory
kubectl get pods -n factory | grep -E "audit|evidence"
```

Look at whether the *recent* runs completed. Old `Error` pods from a transient
blip are noise; a run that has not completed since last week is a finding.

---

## Operating at scale: the failures worth instrumenting

Each of these was observed in this fleet, and none announced itself.

**A deploy that silently no-ops.** Concurrent merges cancel each other's
pipelines; a cancelled run reports neither success nor failure. Compare the
deployed tag to the newest deployable commit on a schedule.

**A GitOps controller reporting `Synced` while behind.** `Synced` means synced
to the last revision fetched. Compare its revision to repository HEAD.

**Orphaned tasks.** A worker dies, nothing writes the terminal status, and the
task shows active forever. Report with `GET /api/maintenance/stale-tasks`.
Never judge by
age alone -- tasks awaiting a human are legitimately old.

**Scheduled jobs that stopped.** The general form of all of the above. If a
schedule matters, alert when it has not succeeded recently, rather than when it
fails -- a job that stops running never fails.

---

## Options reference

| Setting | Options | Default | Unset behaviour |
|---|---|---|---|
| Storage class | RWO / RWX | cluster default | RWO pins workspaces to one node |
| Tenant claim | claim name | `tenant` | sessions cannot be scoped by tenant |
| Stale threshold | hours | 4 | 4h applies |
| Audit forwarding | schedule | every 15 min | events accumulate unforwarded |

---

## Next

- [Testing scenarios]({{ '/guides/testing/' | relative_url }})
- [Cloud development]({{ '/guides/cloud-development/' | relative_url }})
