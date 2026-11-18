---
status: draft
issue: 3823
author: olafkfreund
related: [3829, 3831, 3832, 3560]
---

# Intent: measure disk latency at node-stall time, and settle the netpol probe alert

## Problem

1. The node-stability RCA (Factory#3560, PR #3824) suspects that slow k3s
   SQLite on the shared SATA SSD `sdd` (/mnt/img_pool, 83-87% full) causes the
   lease-loss restarts in Factory#3823, #3829, #3831 and kyverno #3429, #3430,
   #3434, #3437. Disk latency during a stall was never measured, so the
   hypothesis stays unproven and each restart opens a new issue with the same
   open question.
2. Factory#3832 (critical): `netpol-node-probe-agent` fails every run. The
   CronJob pod stays Pending: agent-0 now carries the taint
   `rfactory.io/desktops=true:NoSchedule` (RFactory#3) and the Kyverno policy
   `rfactory-desktops-toleration` admits that toleration only on desktop
   launcher pods. Nothing in the cluster shows a loss of NetworkPolicy
   enforcement; the probe cannot run at all.

## Proposed outcome

- `restart-watchdog` records `sdd` await and utilisation on every run, in a
  stable schema, and puts the same numbers in every issue it opens or updates,
  so the next restart issue carries disk evidence. Observe-only, no
  privileges, no host write, no new volume.
- The agent probe stops raising a false critical, and the runbook says why and
  what to do if the taint is lifted. Findings are on Factory#3832.

## Affected users and systems

factory-gitops `apps/restart-watchdog`, `apps/netpol-node-probe`,
`docs/runbooks/k3d-restart.md`; the owner reading restart issues.

## Constraints

- No host changes, nothing in nixos_config, no live-cluster writes by hand
  (Argo CD syncs the merged change).
- Probe must never change the watchdog exit code or suppress an alert.
- Must not weaken the Kyverno toleration policy (owned by RFactory).
- Owner-only host steps stay with the owner: `docker builder prune`,
  `iostat -x 1 30` during a stall, nvme datastore at next cluster recreate.

## Open questions

None. Decision (owner delegation 2026-11-18): record in restart-watchdog
(not job-watchdog, which has no restart event); retire the agent probe rather
than widen a security policy owned by another repo.
