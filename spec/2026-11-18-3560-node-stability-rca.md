---
status: approved
issue: 3560
intent: intent/2026-11-18-3560-node-stability-rca.md
---

# Spec: node stability RCA

## Findings (read-only, 2026-11-18 16:20-16:50 UTC, context `k3d-factory`)

**F1. Two observed incident windows.** `lastState.terminated.finishedAt`
across all pods shows these instants since the 10:54 cluster recreate:

| instant (UTC) | what | evidence |
|---|---|---|
| 15:34:19-20 | kyverno admission, background, cleanup (agent-0) exit 0 | pod status; logs end in orderly shutdown |
| 15:35:58 | docker restarted `k3d-factory-server-0` (the k3s process exited 1; `RestartCount=1`, `OOMKilled=false`) | dockerd journal "restarting container ... exitCode=1"; `docker inspect` |
| 15:36:04 | 29 containers on server-0 exit 255 `Unknown` (the #3560 `runtime_lost`); fides-server and pfactory exit 1 at 15:36:25-30 | pod status |
| 16:26:45-47 | virt-template-controller (exit 1), keda-operator (exit 1), kyverno reports (exit 0), all agent-0 | pod status, previous logs |

The intent and issue count 34 exit-255 containers; the live pod status shows 29 on
server-0 now (pods since replaced or restarted again are not counted); the discrepancy is
left unresolved. So `runtime_lost` is the k3s server container restarting (apiserver, kubelet and containerd
live in that one process in k3d), not a separate containerd fault. Only `lastState` (the
latest termination) is retained per container, so earlier restarts of the same pods cannot
be placed: this spec neither confirms nor excludes a ten-minute cadence, and makes no claim
about the watchdog's "about every 10 min" wording beyond the instants shown.

**F2. Confirmed: two controllers lost their leases to timed-out renewals. Suspected: a
stalled apiserver datastore is the shared trigger.** Previous logs: virt-template-controller and keda both log
`Failed to update lease ... context deadline exceeded` (`?timeout=5s`) at 16:26:40-47 then
`leader election lost`; kyverno reports-controller exits 0 at 16:26:47 after an orderly drain
(the #561 signature); agent-0's kubelet logged `Failed to update lease ... context deadline
exceeded` at 15:33:02. k3s uses SQLite (kine, WAL) at `/var/lib/rancher/k3s/server/state.db`.
kine logged `Slow SQL` (over 1 s, including lease INSERTs) 48 times in minute 16:26 and 47 in
15:36, against at most 10 in any other minute since 15:37 (10 at 15:40, 7 at 16:34, 0-2 elsewhere). Slow lease INSERTs also appear
from 15:25. Slow SQL shows correlation in time; the direction of causality is not established (a
stalled apiserver and a busy datastore feed each other). Kyverno's orderly shutdowns do not by
themselves prove their trigger; they match the documented lease-loss signature only. The k3s
exit 1 at 15:35:58 left no fatal line in the container log; its trigger is
unproven.

**F3. Likely underlying pressure: the whole cluster shares one 238 GB SATA SSD that is 83-87%
full.** `/mnt/img_pool` (`/dev/sdd1`, Micron MTFDDAK256TBN) is the Docker data root; both k3d
nodes' containerd (33 GB + 26 GB), the SQLite state.db, 54 Docker volumes (59 GB) and
**94 GB of Docker build cache (90 GB reclaimable)** sit on it. The kubelet's "85% of
233.7 GiB used" `ImageGCFailed` / `FreeDiskSpaceFailed` events refer to this disk, not p620 `/`
(82%, nvme). DiskPressure transitioned to False at 15:24:48-52. At 16:26 the host also ran a
system rebuild (sudo at 16:26:43, per agent-bus posts) and load average was 17: coincident, not
proven causal. Disk IO latency during the stalls was not measured (iostat was idle when
sampled at 16:43), so the disk is the leading hypothesis, not a proven cause.

**F4. What is configurable in the repo.**
- KEDA 2.20.1 reads `KEDA_OPERATOR_LEADER_ELECTION_LEASE_DURATION`, `_RENEW_DEADLINE` and
  `_RETRY_PERIOD` (env only, cmd/operator/main.go at v2.20.1, via `ResolveOsEnvDuration`;
  an unparsable value makes the operator exit 1 at start, so the value format must be a Go
  duration such as `60s`). Not set today. The effective defaults were not verified (the
  5 s in the logs is a per-request timeout, not necessarily the renew deadline); the
  values below are chosen as roughly 8x that 5 s request timeout, not from a measured
  stall length.
- Kyverno v1.18.2: the 12 s lease and the renew deadline are hardcoded; only
  `--leaderElectionRetryPeriod` exists (already documented in apps/kyverno kustomization,
  Factory#561/#651). Not fixable by timeouts. No OOMKilled; exits are 0 after lease loss.
- virt-template-controller v0.2.3: `--leader-elect` only; ID hardcoded, timings are
  controller-runtime defaults, not flags. Its Deployment is owned by virt-operator, which
  would revert an in-place patch. Same signature and same seconds as keda: not a separate
  defect. Its "Waiting for required CRDs ... cdi, snapshot" line is benign (CDI not
  installed) and unrelated to the exit.
- `restartPolicy` is Always everywhere; not a contributor.
- gate-image-prepull (AIFactory#1737) keeps about 4.6 GB x 2 nodes of images. By design and
  about 9 of 59 GB; no change.

## Design

1. Factory: this artifact set plus per-issue verdict comments. No code.
2. factory-gitops PR: a kustomize patch on the keda-operator Deployment adding
   `KEDA_OPERATOR_LEADER_ELECTION_LEASE_DURATION=60s`, `_RENEW_DEADLINE=40s`,
   `_RETRY_PERIOD=5s`. If renewals succeed within the 40 s deadline the operator survives a stall that
   today ends in `leader election lost`. Accepted tradeoff: if the operator truly hangs,
   its lease is not reclaimed for up to 60 s, and the single replica is not replaced
   faster than its pod restart. Rollback: remove the patch.
3. Owner host steps (exact commands are in the plan and the verdict comments, not
   performed by agents): prune the Docker build cache (90 GB reclaimable), keep
   `/mnt/img_pool` under 70%, move build cache and the k3d state.db off the shared SATA
   SSD to nvme (k3d recreate), and avoid image builds in parallel with cluster rollouts.

## Alternatives rejected

- Raise Kyverno or virt-template memory/CPU limits: no OOM evidence; exits are lease loss.
- Patch virt-template-controller via KubeVirt `customizeComponents`: timings are not flags.
- Turn off Kyverno admission reports to cut kine writes: changes policy-report behaviour that
  apps/kyverno-policies freshness checks rely on; needs an owner call.
- Remove or shrink gate-image-prepull: saves about 9 of 59 GB and undoes AIFactory#1737.
- Change the k3d datastore or kubelet settings from this repo: host-level.

## Risks

A longer KEDA lease means a hung operator is replaced up to 60 s later: acceptable. The
mitigation does not touch the suspected cause; the five other controllers may keep
restarting, and whether freeing the disk stops that is a hypothesis to test, not a
prediction. Verdicts are "lease loss confirmed, datastore stall suspected, partial repo
mitigation", not "fixed".

## Verification

- `kustomize build apps/keda/manifests` shows the three env vars on `keda-operator` and no
  other change; repo schema checks pass.
- After sync: `kubectl -n keda get deploy keda-operator -o jsonpath` shows the env; the new
  pod starts (a parse error would exit 1 at start) and logs leader acquisition.
- Effect: compare keda's restart count against a later minute where kine logs a burst of
  Slow SQL and a lease `PUT` takes over 5 s (apiserver lease histogram); a survival with no
  `leader election lost` in that window is the evidence. Absence of a burst proves nothing.
- Unproven and stated as such: trigger of the 15:35:58 k3s exit; role of host load at 16:26;
  disk latency during stalls.
