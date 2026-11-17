---
status: draft
issue: 3782
author: olafkfreund
---

# Intent: per-node NetworkPolicy enforcement probe and k3d restart runbook

## Problem

Factory#3770: after both k3d node containers restarted, Docker swapped the
node IPs (.2/.3). Each kube-router kept the stale peer IP, so it wrote pod
firewall rules for the other node's pods. Task pods on agent-0 had no
NetworkPolicy. The `netpol-gate` init container failed closed, so no task ran
unconfined, but nothing told the owner a node was unenforced: the first sign
was failed spec runs. The fix (restart nodes one at a time, re-add the
`/etc/hosts` entries that `docker restart` drops) exists only in an issue
comment.

## Proposed outcome

- A scheduled check proves NetworkPolicy enforcement on every node and
  raises an issue through the existing alert path within about an hour of a
  node losing it.
- A runbook in factory-gitops documents the safe k3d restart procedure and the
  iptables check that proves enforcement afterwards.

## Affected users and systems

factory-gitops (new app, new doc), the `factory` namespace, the k3d-factory
cluster (server-0, agent-0). Existing consumers: apps/job-watchdog.

## Constraints

- Least privilege: no RBAC, no service account token, no hostNetwork, not
  privileged.
- Must not loosen the policy or the gate. No node restarts (owner action).
- Reuse the alert path (job-watchdog turns a failing CronJob into an issue);
  no new notification code.

## Open questions

None. Owner delegated the recommended option (Decision 2026-11-17 on #3782).
