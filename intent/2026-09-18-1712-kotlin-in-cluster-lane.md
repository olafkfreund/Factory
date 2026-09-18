---
status: draft
issue: 1712
author: olafkfreund
---

# Intent: the Kotlin verify lane runs in-cluster, not only on the docker host

Revision 2. Revision 1 was approved on the premise that TFactory's nix-Job lane
path could already run a Kotlin lane and only needed proving. Reading the code
showed it cannot (see "What the code shows" below), so this is back to draft.

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

## What the code shows (TFactory `dev`, 2026-09-18)

- The only **in-cluster** lane executors are per-language nix functions in
  `agents/nix_env.py`: `run_pytest_lane_via_nix`, `run_gotest_lane_via_nix`
  (TFactory#543, ~150 lines), `run_jest_lane_via_nix`, and the deploy lane.
  **There is no gradle/Kotlin equivalent.**
- Every other lane goes through `tools/runners/lane_dispatch.py` →
  `DockerRunner` (`docker run`), which needs a container runtime. The cluster
  has none, which is why #1707's proof ran on the docker host.
- So egress was never what kept Kotlin out of the cluster. **No in-cluster
  executor exists**, whatever the network allows.

## Proposed outcome

Depends on the scope decision below. Either way:

- `contracts/languages/kotlin.yaml` stops blaming egress and states the true
  reason and status. Hub first, then re-vendored into the three services with
  the pins bumped.
- #1712 closes on evidence, and the executor gap is tracked on its own if it
  is not built here.

**Option A (recommended): build the executor.** Add a
`run_gradle_lane_via_nix` in TFactory, mirroring `run_gotest_lane_via_nix`
(generated flake from the descriptor's `nix.packages`, `gradle test` in the
per-task nix Job, JUnit results parsed into the lane result), wired into the
evaluator the same way. Then prove it: a minimal Kotlin fixture's
`gradle test` completes in-cluster, passes, and a mutated test fails. Kotlin
then verifies in-cluster like Python, Go and JS.

**Option B: correct the record only.** Fix the descriptor's caveat to "no
in-cluster gradle executor; docker-host only", close #1712's egress question,
and file the executor as a new issue. Small, but Kotlin still cannot verify
in-cluster.

## Affected users and systems

- Hub: `contracts/languages/kotlin.yaml` (the canonical descriptor).
- Vendored copies: TFactory `apps/backend/tools/runners/languages/kotlin.yaml`,
  PFactory `apps/backend/plan/languages/kotlin.yaml`, AIFactory
  `apps/backend/core/languages/kotlin.yaml`, and their drift gates and pins.
- TFactory `agents/nix_env.py` and `agents/evaluator.py` (Option A: new
  `run_gradle_lane_via_nix` and its call site).
- Anyone verifying a Kotlin project in the cluster, e.g. the
  `pfactory-friends-demo` Kotlin lanes.

## Constraints

- **Measure, don't assume.** A lane counts as proven only when a real run
  completes with real test results, including a mutated test that fails. A Job
  that starts, or an exit code without test counts, does not count.
- Option A's proof runs **through the evaluator's real lane path** (the new
  nix runner), not a hand-rolled pod, so it covers what real tasks take.
- **One engine, no drift:** fix the hub canonical first, then re-vendor
  byte-exact and bump the pins in the right order (the drift-gate landing
  order).
- **Out of scope:** AIFactory's QA sandbox lacking `java`/`gradle`. That is a
  different substrate, tracked in AIFactory#1560.
- No change to the egress policy. It already admits what Gradle needs.

## Decisions carried from revision 1 (still valid)

1. **Fixture:** a dedicated minimal Kotlin module, independent of
   `pfactory-friends-demo`.
2. **Scope of the proof:** `gradle test`; `gradle pitest` is a follow-up.

## Open questions

1. **Option A or Option B?** A is a medium feature in TFactory (~150-line
   runner on an existing pattern, plus evaluator wiring and JUnit parsing). B
   is a docs correction plus a new issue.
