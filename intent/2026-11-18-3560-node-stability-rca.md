---
status: draft
issue: 3560
author: olafkfreund
---

# Intent: node stability RCA (runtime_lost and leader-controller restarts)

Covers Factory#3560 (job-watchdog `runtime_lost` on `k3d-factory-server-0`) and the
restart-watchdog issues #3823 (virt-template-controller), #3437, #3434, #3430, #3429
(Kyverno cleanup, reports, background, admission) and #3407 (keda-operator), all
reopened 2026-11-18.

## Problem

Seven leader-electing controllers restart repeatedly (exit 0 or 1) and the watchdog
reports 34 containers killed at once with exit 255. Nobody has established whether
these are one fault or seven, or whether the repo can fix any of it. Earlier
closures (Factory#561, #571, #582) were each a node fault; this one has no verdict yet.

## Proposed outcome

- One evidence-backed verdict per issue, posted as an issue comment.
- Every repo-fixable contributor fixed by PR in factory-gitops.
- Every host-only step written as an exact owner command, not performed by an agent.

## Affected users and systems

p620 factory k3d cluster (`k3d-factory`, nodes server-0 and agent-0); apps `keda`,
`kyverno`, `kubevirt` in factory-gitops; the job-watchdog and restart-watchdog.

## Constraints

- Investigation is read-only: no live change, no restart, no kubectl apply/delete.
- Host disk, kubelet and containerd config and k3d recreate settings are the owner's.
- The watchdog closes the issues itself after 24 h; nothing is closed by hand.

## Open questions

None. Decision (owner delegation 2026-11-18): fix only what the repo can express;
leave host steps to the owner.
