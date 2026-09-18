---
status: draft
issue: 1712
author: olafkfreund
---

# Intent: the Kotlin verify lane runs in-cluster, not only on the docker host

## Problem

The Kotlin lane (Factory#1707, `contracts/languages/kotlin.yaml`) is proven only
on the docker-host substrate. For in-cluster verify Jobs, the descriptor itself
warns (L18-22) that Gradle's plugin and dependency fetches "stall there until
the Maven/Gradle hosts are allowlisted". So a Kotlin project verified in the
cluster is either expected to hang or is quietly routed elsewhere.

That warning is now known to be wrong. Measured 2026-09-18 (comment on #1712):

- The build-Job policy `factory-sandbox-jobs-egress` allows TCP 443 to **all
  public IPs**. There is no per-host allowlist.
- A pod under that policy fetched Maven Central, the Gradle plugin portal and a
  136.7 MB Gradle distribution **completely**, in 2.1 s.

So the blocker #1712 was filed for does not exist. What is still missing is the
proof the issue asked for: **nobody has run a real Kotlin `gradle test` to
completion inside the cluster**. Until someone does, the descriptor keeps
warning off in-cluster Kotlin verification, and a Kotlin task's verification
evidence depends on which substrate happened to run it.

## Proposed outcome

- A real in-cluster Kotlin verify run (TFactory's per-task nix Job substrate)
  of a minimal Gradle module completes: tests run, pass, and a mutated test
  fails.
- `contracts/languages/kotlin.yaml` states what is true: the lane is proven
  in-cluster, and it no longer says fetches stall. The hub copy is corrected
  first, then re-vendored into TFactory, PFactory and AIFactory, with the
  drift pins bumped.
- #1712 closes on that evidence, not on the policy reading alone.

## Affected users and systems

- Hub: `contracts/languages/kotlin.yaml` (the canonical descriptor).
- Vendored copies: TFactory `apps/backend/tools/runners/languages/kotlin.yaml`,
  PFactory `apps/backend/plan/languages/kotlin.yaml`, AIFactory
  `apps/backend/core/languages/kotlin.yaml`, and their drift gates and pins.
- TFactory's evaluator nix-Job lane path (the substrate the run goes through).
- Anyone verifying a Kotlin project in the cluster, e.g. the
  `pfactory-friends-demo` Kotlin lanes.

## Constraints

- **Measure, don't assume.** A lane counts as proven only when a real run
  completes with real test results, including a mutated test that fails. A Job
  that starts, or an exit code without test counts, does not count.
- Run it **through the factory's own lane path** (TFactory's nix Job), not a
  hand-rolled pod, so the proof covers the path real tasks take.
- **One engine, no drift:** fix the hub canonical first, then re-vendor
  byte-exact and bump the pins in the right order (the drift-gate landing
  order).
- **Out of scope:** AIFactory's QA sandbox lacking `java`/`gradle`. That is a
  different substrate, tracked in AIFactory#1560.
- No change to the egress policy. It already admits what Gradle needs.

## Open questions

1. **What to run:** a dedicated minimal Kotlin fixture module, or one of
   `pfactory-friends-demo`'s real Kotlin lanes? Proposed: the minimal fixture,
   so the proof is independent of that demo's open PR conflicts (#51/#53).
2. **Also prove `gradle pitest` (mutation lane) in-cluster, or `gradle test`
   only?** #1712's "Done means" names `gradle test`. Proposed: test only, with
   pitest as a follow-up if it behaves differently.
