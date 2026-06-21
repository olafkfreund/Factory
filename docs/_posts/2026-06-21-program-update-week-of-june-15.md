---
layout: post
title: "Program update: week of June 15–21, 2026"
subtitle: "SpecKit-informed interop and the concurrency core shipped; Job-native defaults are converging — the honest fleet-wide status across PFactory, AIFactory, TFactory and CFactory"
date: 2026-06-21
author: Olaf Freund
---

This is a program-level weekly update across the whole Factory fleet. Where the
per-service posts go deep on one product, this one steps back: what shipped this
week across PFactory, AIFactory, TFactory and CFactory, what is genuinely live on
the cluster, and — just as important — what is still on its way and should not be
claimed as done. Links to each service's own post for the week are at the bottom.

## Shipped this week

### RFC-0015 — Spec-driven interop, end to end

The fleet now speaks the same spec-driven language that tools like GitHub's
`spec-kit` validate the thesis for. This week RFC-0015 went from schema foundation
to a working end-to-end proof, with the epic (#183) and all ten of its children
closed.

What that means in practice:

- A **constitution** — a declarative set of house rules — is ingested by PFactory
  and carried through the contract so AIFactory and TFactory consume the same
  standards the planner was held to.
- `.specify`-style spec ingest and emit, so a SpecKit project and the Factory
  pipeline can hand work back and forth without lossy translation.
- An **adversarial spec-review** pass that argues against a spec before it is
  approved, surfacing gaps the happy-path review would miss.
- **Requirement → test traceability**, so every acceptance criterion can be traced
  to the test that exercises it (or flagged as unproven).
- A **declarative extension registry** that lets the schema grow without code
  changes scattered across four repos.

This is the connective-tissue work paying off: one contract, one set of rules,
read the same way at plan, code and verify time.

### RFC-0016 — the concurrency core, proven live

For most of the program the PARR pipeline ran one task at a time. RFC-0016 changes
that, and the **core landed and was verified live this week** (epic #188). The
pieces:

- A **stateless control plane** — the web servers hold no per-run state, so they
  can be replicated.
- **Durable job-state in Postgres** — the source of truth for every in-flight run,
  survivable across restarts and replicas.
- **Admission / concurrency caps** wired to the cost budget from RFC-0014, so
  fan-out is bounded by money as well as by cluster capacity.
- The **Nix-per-task Kubernetes Job** substrate as the default for build and verify
  gates — each task gets a reproducible, isolated environment.
- A shared **MinIO / S3 object store** for artifacts so Jobs on different nodes can
  exchange inputs and outputs.
- **KEDA** queue-depth autoscaling.

The proof is the part that matters: on the factory cluster we ran **8 concurrent**
Job-per-task executions, and watched **KEDA scale a worker deployment 1→3** under
queue pressure. That is the substrate the fleet needed to stop being a
single-lane road.

### RFC-0017 — Job-native execution mechanisms

RFC-0017 is the follow-through on RFC-0016: take the Job-native substrate and make
it the *default* path for build and verify across replicas. This week the
**mechanisms** shipped (epic #206):

- **Job-native log streaming**, so a build or verify running inside a Kubernetes
  Job streams its output back to the portal the same way an in-pod run does.
- A **Redis-backed multi-replica run-multiplexer (rmux)** — and multi-replica is
  now **running live**, so more than one control-plane replica can serve and
  observe runs.
- **Workspace pack/unpack via object storage** (#207), the mechanism that lets a
  workspace produced on one node be consumed on another.

Read the next section before treating RFC-0017 as finished — it is not.

### AWS demo resources cleaned up

The App Runner and EKS demo stacks from the recent deploy-then-verify and
three-tier posts were torn down. There is **zero ongoing cloud spend** from the
demos.

## In progress — honestly not done yet

The temptation each week is to round "mechanisms merged" up to "shipped." Here is
the part that is still converging.

### RFC-0017 default flips — NOT live

The Job-native **build+verify default flips** (#671 / #466) are **not yet live.**
The credential-injection work they depend on has merged (AIFactory #688, TFactory
#480), but the flips themselves are still on **safe in-pod defaults** and are
converging through bug rounds:

- The **build** default flip is blocked on a `/work`-has-no-`.git` problem — the
  Job's workspace arrives without the git metadata the build step expects.
- The **verify** default flip is pending re-validation after that build path is
  sound.

Until those are green, the truthful statement is: the *mechanisms* exist and
multi-replica is live, but build and verify still run in-pod by default. We will
flip them when they are proven, not before.

### Stage E — multi-node workspace consumption

Workspace pack/unpack exists, but the full **multi-node consumption** path — a
workspace packed by one Job and unpacked by another across nodes as the normal
flow — is **Stage E** and still has code to land. It is the last structural piece
between "concurrency core proven" and "fully job-native by default."

## Where the RFC ladder stands

- **RFC-0014** (cost-aware routing) — *Proposed.* Referenced as a dependency by
  0015 and 0016; not yet implemented on its own.
- **RFC-0015** (spec-driven interop) — *Implemented*, end-to-end proof landed.
- **RFC-0016** (horizontal & concurrent execution) — *Core implemented and
  verified live*; remaining default flips and multi-node workspace consumption
  tracked under RFC-0017.
- **RFC-0017** (full Job-native default execution & scale-out) — *In progress*;
  mechanisms shipped and multi-replica live, default flips converging.

The [program roadmap](/roadmap/) and the [RFC index](/rfc/0016-horizontal-concurrent-execution.md)
carry the same status, kept deliberately in sync with this post.

## Per-service posts for the week

Each product has its own write-up for the week of June 15–21:

- **PFactory** — [olafkfreund.github.io/PFactory/blog/](https://olafkfreund.github.io/PFactory/blog/)
- **AIFactory** — [olafkfreund.github.io/AIFactory/blog/](https://olafkfreund.github.io/AIFactory/blog/)
- **TFactory** — [olafkfreund.github.io/TFactory/blog/](https://olafkfreund.github.io/TFactory/blog/)
- **CFactory** — [olafkfreund.github.io/CFactory/blog/](https://olafkfreund.github.io/CFactory/blog/)

The bet has not changed: lead with governance, verification and observability, and
make the substrate underneath strong enough to run many of them at once. This week
moved the substrate a long way — and was honest about the last mile that remains.
