---
layout: post
title: "The last node-pin: making a packed build node-agnostic"
subtitle: "Packing the workspace to object storage freed /work — but the build still nailed itself to one node through the Nix store. Here is how we cut the last wire, and the honest line on what is proven."
date: 2026-06-23 12:00:00 +0000
author: Olaf Freund
---

The Factory PARR pipeline — **PFactory** (plan), **AIFactory** (code), **TFactory**
(verify), watched in the **CFactory** cockpit — has been moving, leg by leg, from a
single pod that does everything to a fleet of short-lived Kubernetes Jobs that scale
out. [RFC-0016](/rfc/horizontal-concurrent-execution/) shipped the substrate;
[RFC-0017](/rfc/job-native-scale-out/) is the slow, honest work of making every leg
genuinely node-agnostic so the cluster scheduler — not a buried volume mount — decides
where work runs.

This post is about one wire. The last one pinning an AIFactory build to a single node.
It is a small change with a long tail of reasons, which makes it a good example of the
kind of engineering that does not show up in a feature list but is the whole difference
between "runs concurrently on one box" and "scales across a cluster."

## What a build actually needs from its node

When AIFactory builds a task, it dispatches a Kubernetes Job that runs `run.py` — the
coder agent that writes the code. Two things that Job touches used to live on the node:

- **The workspace** (`/work`) — the task's git checkout. The coder writes here.
- **The Nix store** (`/nix`) — the toolchain cache. The coder runs its verification
  gates inside `nix develop`, and those tools come from Nix.

Both were **RWO `local-path` PersistentVolumeClaims**. A `local-path` PV is physically a
directory on one node, and its `nodeAffinity` pins any pod that mounts it to that node.
Mount one, and the scheduler has no choice left: the Job lands where the volume lives.
Fine on a single-node cluster. Fatal to multi-node scale.

[RFC-0017 #207](/rfc/job-native-scale-out/) already solved the first one. Instead of
co-mounting the workspace PVC, the producer **packs** the populated `/work` to
object storage (an in-cluster MinIO bucket) and threads an `s3://` URI onto the Job; the
Job **unpacks** it into a writable `emptyDir` before the build. No workspace PVC, no node
pin from `/work`.

But the build stayed pinned anyway — because of the second mount.

## A short detour: how toolchains reach a task

It is worth being precise about why a build needs `/nix` at all, because it explains why
the fix is shaped the way it is.

Factory does not ship a fat image with every language baked in. Instead, every task
carries an **environment manifest** in its contract (this is
[RFC-0005](/rfc/environment-provisioning/)), and from that manifest
we **generate a `flake.nix`** — a reproducible Nix flake pinned to an exact nixpkgs
revision. The flake is materialized into the worktree, and build and verify commands run
through it:

```
nix develop path:/work#default --command bash -c "<command>"
```

Nix evaluates the flake, fetches or builds the toolchain closure into `/nix/store`, and
drops into a dev shell with exactly the right compilers and libraries on `PATH`. The
elegant part is that **TFactory verifies through the same generated flake** the coder
built against, so the environment the test runs in cannot drift from the environment the
code was written in. (No `devenv`, no Dockerfile per language — just a plain flake and a
pinned nixpkgs.)

The catch: that closure has to come from somewhere. The fast path was a **warm
`/nix/store` PVC** — a shared cache so repeat builds did not re-fetch the world. Warm,
fast, and node-pinned. So even with the workspace packed to object storage, every packed
build Job still co-mounted that one RWO Nix-store PVC and got dragged back to its node.

The last wire.

## Cutting it: bake the store into the image

The store does not have to be a volume. It can be a layer.

The fix landed as three small, independently reversible changes:

1. **A gate in the dispatcher.** A flag, `AIFACTORY_PACKED_NIX_IN_IMAGE`, that — on the
   packed path only — drops the Nix-store PVC from the build Job manifest entirely. The
   gate is the contract: with it off, nothing changes; with it on, the Job carries no
   node-pinned volume.

2. **A `-nix` build image.** A dedicated image variant that is the ordinary AIFactory
   runtime image **plus a baked `/nix/store`** — the warm closure, frozen into a layer at
   build time instead of mounted at run time. It is published on demand by its own
   workflow, kept separate from the per-commit deploy image so the multi-gigabyte store is
   not rebuilt on every push.

3. **The flip.** Point the build Job at the `-nix` image and turn the gate on. The Job now
   resolves `nix develop` from the image's own `/nix/store`, carries no Nix-store PVC, no
   workspace PVC — and therefore carries **no node affinity at all**.

A packed build Job is now node-agnostic by construction. There is nothing left in its
manifest that ties it to a node. The scheduler is free.

## The honest line

This is where these posts always tell the truth, because the truth is the useful part.

What is **shipped and live**: the gate, the `-nix` image, and the gitops flip pointing the
build at it. We verified the chain end to end at the layers we can verify without new
hardware — the image is published and resolvable, the manifest the dispatcher emits for a
packed build has no Nix-store volume, and the toolchain resolves from the baked store. The
build Job is node-agnostic **by construction**.

What is **not yet proven**: an actual landing on a *different* node. The live cluster is a
single node today, so there is no second node for the scheduler to place a build on. "No
node affinity in the manifest" is a strong structural guarantee, but it is not the same as
watching a packed build run on node B while node A is cordoned. That demonstration is
waiting on one thing — a second node — and not on any more code. When the node is there,
the proof is a five-minute exercise: cordon the control-plane node, dispatch a packed
build, watch it schedule elsewhere and resolve its toolchain from the image.

We would rather ship the mechanism, say exactly where the line is, and show the landing
when the hardware is real, than imply a cluster we do not yet run. The wire is cut. The
demonstration is scheduled.
