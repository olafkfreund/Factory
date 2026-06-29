---
layout: default
title: "RFC-0017: Full Job-Native Default Execution & Control-Plane Scale-Out"
permalink: /rfc/job-native-scale-out/
---

# RFC-0017 — Full Job-Native Default Execution & Control-Plane Scale-Out

> **Status:** In progress (epic #206; mechanisms shipped — Job-native log
> streaming, Redis-backed multi-replica rmux, workspace pack/unpack #207, and
> multi-replica running live. The Job-native build+verify *default* flips
> (#671/#466) are **not yet live** — they are converging through bug rounds on
> safe in-pod defaults. Stage E workspace pack/unpack runs live, and the last
> node-pin on the packed build path — the warm Nix-store PVC — was cut by baking
> the store into a `-nix` build image (#190); a packed build Job now carries no
> node affinity. The cross-node *landing* is now **proven live** (2026-06-29): a
> node-agnostic Job on the `-nix` build image scheduled onto a second cluster node
> with the control-plane cordoned, resolving toolchains from the baked store
> offline — closing the last infra-gated item (#215).) ·
> **Created:** 2026-06-21 · **Updated:** 2026-06-29 · **Extends:**
> [RFC-0016](./0016-horizontal-concurrent-execution.md) (Job-per-task substrate,
> durable state, KEDA), [RFC-0005](./0005-environment-manifest-and-toolchain-provisioning.md)
> (Nix Jobs) · **Affects:** AIFactory (build default, logs/rmux, Redis),
> TFactory (verify default), Factory (workspace pack/unpack), platform (Redis,
> replica pins, HA Postgres)

## 1. Motivation

RFC-0016 shipped and verified the concurrency substrate end-to-end: durable
Postgres state, admission caps, the Nix-per-task Job substrate (default for
build/verify gates), KEDA autoscaling (pfactory/tfactory 1→N proven), object
storage, and an **opt-in** control/execution split (run.py/verify as a k8s Job).
Three follow-ups were deliberately deferred because each needs genuinely new
supporting work and a validated live rollout — this RFC scopes them.

The opt-in Job split exists and is tested, but is **not the default** because the
in-pod path still owns two things a Job doesn't yet provide: **live log streaming
+ the rmux Live Agent Console**, and AIFactory is **pinned to one replica** because
rmux WebSocket fan-out is pod-local. And workspaces still live on **RWO
`local-path` PVCs**, which pin a service to one node — fine on the single-node k3d
cluster today, but the blocker to true multi-node scale.

## 2. Scope (the three follow-ups)

### 2.1 Job-native logs + flip the split to default (RFC-0016 #671/#466)
Make the Job-per-task split the **exclusive default** for AIFactory build and
TFactory verify. Prerequisite: **Job-native log streaming** — the control plane
must stream a running Job's logs (and feed the rmux console) from the Job pod
(`kubectl logs -f` equivalent via the k8s API / a log sink in object storage)
instead of the in-pod pty. Once logs are Job-native and a live validation passes,
flip `AIFACTORY_BUILD_BACKEND` / `TFACTORY_VERIFY_EXEC` default to `kubejob` and
retire the in-pod subprocess path (kept as a fallback).

### 2.2 AIFactory multi-replica via Redis-backed rmux
AIFactory is capped at 1 replica because the rmux Live Agent Console fans WebSocket
events out from a **pod-local** panes store. Move that fan-out onto **Redis
pub/sub** (a shared bus) so any replica can serve any console session; persist the
panes index in Redis (or Postgres) rather than a pod-local PVC. Then raise the
AIFactory KEDA `maxReplicaCount` and remove its `replicas: 1` pin — bringing it to
parity with pfactory/tfactory (which already autoscale).

### 2.3 Workspace migration off RWO local-path (RFC-0016 #190 tail)
Move task **workspaces** off RWO `local-path` PVCs to object storage / RWX. A
Phase-2 Job **packs** its inputs from object storage into its ephemeral worktree
and **unpacks** outputs back (the `workspace` role in `artifact_store`, RFC-0016
§2); the control plane and CFactory read results from object storage + Postgres,
never a shared PVC. Then remove the RWO worktree mounts — the last blocker to
scheduling Jobs across **multiple nodes**.

> **Status (2026-06-23).** Shipped. The producer packs the populated `/work` to
> object storage (in-cluster MinIO) and the build Job unpacks it into a writable
> `emptyDir`, dropping the RWO workspace co-mount. One pin survived that change:
> the build Job still co-mounted the warm **Nix-store** RWO `local-path` PVC at
> `/nix` (the toolchain cache the per-task flake resolves against), which re-pinned
> every packed build back to that PVC's node. Cut in three reversible slices —
> a dispatcher gate (`AIFACTORY_PACKED_NIX_IN_IMAGE`) that drops the Nix-store PVC
> on the packed path (#730), a `-nix` build image that bakes `/nix/store` into a
> layer (#732), and the gitops flip pointing the build at it (#733 + gitops). A
> packed build Job now carries **no node affinity** by construction. **Cross-node
> landing proven live (2026-06-29):** with a second agent node (`k3d-agent-0-0`)
> joined to the `factory` k3d cluster and the control-plane node
> (`k3d-factory-server-0`) cordoned, a node-agnostic Job on the `-nix` build image
> was bound by the scheduler to the agent node and resolved a toolchain from the
> baked `/nix/store` fully offline. See §4.

### 2.4 (Optional, later) HA Postgres
Postgres is single-replica today (fine for "durable state exists"). Streaming
replication / a managed Postgres is a later hardening concern, noted here for
completeness, not required by this RFC.

## 3. Principles

1. **No regression on the live console.** Flipping to Job-native must preserve the
   rmux Live Agent Console + live logs users rely on — that is the gating
   prerequisite, not an afterthought.
2. **Fallback always.** The in-pod path stays as a fallback behind the env flag;
   the flip changes the default, it does not delete the escape hatch.
3. **Validate live before flipping.** Each default flip lands only after a real
   build/verify runs green Job-native on the cluster with logs intact.
4. **Object storage is the source of truth for artifacts + workspaces** — no
   shared mutable PVC across pods once §2.3 lands.

## 4. Verification

- **Job-native logs:** a running build/verify Job streams live logs to the cockpit
  + rmux console identically to the in-pod path; flip the default; a real run is
  green with no console regression.
- **AIFactory multi-replica:** with Redis-backed rmux, scale AIFactory to 2+, open
  a console session served by a different replica than the one that started the
  build; KEDA scales it on queue depth like pfactory/tfactory.
- **Workspace migration:** a Job packs/unpacks its workspace via object storage; a
  build/verify completes with NO RWO worktree mount; results readable from object
  storage by the control plane + CFactory; schedule two Jobs on (simulated) two
  nodes without a shared PVC.
- **Cross-node landing (RFC-0016 #190 depin, Factory #215): proven live 2026-06-29.**
  A second agent node (`k3d-agent-0-0`) is joined to the `factory` k3d cluster. With
  the control-plane node (`k3d-factory-server-0`) cordoned, a node-agnostic Job on
  the packed `-nix` build image (`AIFACTORY_BUILD_IMAGE` `…aifactory:sha-24b2796-nix`)
  was bound by the scheduler to the agent node in ~2s, ran `nix` 2.30.1 and executed
  a toolchain binary from the baked `/nix/store` (121 store paths) fully offline, and
  completed green — while the 28-pod control-plane fleet was undisturbed and the node
  was uncordoned immediately afterward. This closes the only infra-gated item under
  epic #206.

## 5. Adoption (tracked by the epic)

AIFactory: Job-native log streaming + build-backend default flip (#671) + Redis
rmux + multi-replica. TFactory: verify-exec default flip (#466). Factory:
`workspace`-role pack/unpack in `artifact_store`/`job_dispatch`. Platform: Redis,
KEDA `maxReplicaCount` raise + replica-pin removal for AIFactory, RWO mount
removal. Plus the live verification proofs above.
