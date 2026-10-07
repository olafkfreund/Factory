---
status: approved
issue: 3151
author: olafkfreund
---

# Intent: Gradle-built Java verifies in-cluster

## Problem

A Java project built with Gradle cannot be verified in the cluster. TFactory's
Planner pins every Java unit subtask to `(java, maven, unit)`, and the
evaluator runs `mvn -B test`, which finds no `pom.xml` and fails. The verdict
is then wrong for a reason unrelated to the code under test.

#3151 frames this as a toolchain gap in `scripts/nix_provisioner.py:460`
(`"java": ["jdk21", "maven"]`). Reading the code (TFactory `origin/dev` and
the hub, 2026-10-06) shows the toolchain is the smallest part of it.

## What the code shows

- **The toolchain mechanism already exists.** `_LANG_ATTRS` is prepended to
  `system_packages` (`nix_provisioner.py:535-546`), and the comment at L456-459
  states the intended path: "a project that wants [gradle] names it in
  system_packages". A Java env with `system_packages: ["gradle"]` already
  renders a flake with jdk21 + maven + gradle. #3151's option 1 (adding gradle
  to the hub table) is not needed to get gradle into the shell.
- **The evaluator ignores the framework.** `_resolve_java_runner_fn`
  (`agents/evaluator.py` ~L2265) always calls `run_maven_lane_via_nix`. It routes
  by `language == "java"` alone, so a gradle framework pin would still run `mvn`.
- **A Gradle executor exists, but it is Kotlin's.** `run_gradle_lane_via_nix`
  (`agents/nix_env.py:1139`) is hard-wired to `kotlin_environment()`. Its module
  discovery (`_gradle_module_dir`) and JUnit parsing are not Kotlin-specific.
- **The registry allows one framework per language and lane.** `java.unit` is
  `frameworks/maven` only. `frameworks/gradle` is `language: kotlin`, and its
  header says it keeps Kotlin-only manifest signals so it never collides with
  `frameworks/junit`. `frameworks/junit` claims `build.gradle(.kts)` for Java but
  no longer claims `unit`. Two frameworks claiming `java.unit` would make the
  Planner's choice ambiguous unless the manifest (`pom.xml` vs `build.gradle*`)
  breaks the tie.

So the gap is routing, in TFactory: the Planner, the framework registry and the
evaluator. The hub provisioner and its four vendored copies probably need no
change.

## Proposed outcome

- A Java project whose build is Gradle (`build.gradle` / `build.gradle.kts`, no
  `pom.xml`) is planned with a Gradle unit lane, and the evaluator runs
  `gradle test` in the per-task nix shell with jdk21 + gradle. JUnit results are
  parsed the same way as for Kotlin.
- A Maven Java project is unchanged: same pin, same `mvn -B test`, same store
  cost.
- Proven the way #1712 and TFactory#1321 were proven: a minimal Gradle Java
  fixture runs `gradle test` to completion in-cluster through the evaluator's
  real lane path, passes, and fails when a test is mutated.
- The comments that call Gradle-Java "the follow-up" (`frameworks/maven`
  header, `java_environment` docstring, `nix_provisioner.py:456-459` if it
  changes) state the new truth.

## Affected users and systems

- TFactory: `agents/evaluator.py` (Java runner routing), `agents/nix_env.py`
  (the Gradle runner takes an environment instead of assuming Kotlin's, or a
  Java-Gradle env builder), `frameworks/` (how `java.unit` resolves to gradle vs
  maven), the Planner's framework pin and `_validate_framework_consistency`.
- Hub `scripts/nix_provisioner.py`: a comment fix at most. A code change here
  means re-vendoring into four services with pin bumps, which this intent aims
  to avoid.
- Anyone sending a Gradle-built Java deliverable through PARR. None has come
  through yet.

## Constraints

- **Maven-Java must not pay for this.** No gradle in the default Java flake.
  Only Gradle-shaped projects get it.
- **Measure, don't assume.** It counts as done only on a real in-cluster run with
  real test counts and a failing mutation, through the evaluator path. A started
  Job or a bare exit code doesn't count.
- **No ambiguous pin.** For any given project the Planner must pick exactly one
  of maven or gradle, decided by the manifest. Never a coin flip between two
  registry entries.
- **Don't fork the Gradle runner.** Reuse `run_gradle_lane_via_nix` rather than
  copying ~100 lines for Java.
- Out of scope: Gradle multi-language builds (Java + Kotlin in one build), and
  `gradle pitest` / mutation lanes. AIFactory's QA sandbox is a different
  substrate (AIFactory#1560).

## Open questions

1. **Build now, or park until there's demand?** #3151 says "not urgent — no
   Gradle-built Java deliverable has come through yet". The routing gap means a
   Gradle-Java task would get a wrong red verdict, not a hang. Options:
   - **A (recommended): build it.** It's TFactory-only, small, and reuses the
     Kotlin runner. The failure it prevents is a wrong verdict, which is
     expensive to diagnose when it does happen.
   - **B: guard only.** Make the Java lane detect "no `pom.xml`, Gradle build
     present" and return an explicit "gradle-java lane not supported" result,
     not a misleading `mvn` failure. File the lane for later.
   - **C: park.** Close #3151 as won't-do-yet, with this analysis attached.
2. **How Gradle is chosen for Java** (spec-level, but it affects scope): a new
   `frameworks/gradle-java` descriptor with manifest-based disambiguation, or
   one `java.unit` framework whose runner picks maven or gradle from the
   manifest at run time. The second avoids a registry change but hides the
   build tool from the plan.

## Decisions on approval (2026-10-06)

1. **Option A: build it.** The recommended option, approved without amendment.
2. How Gradle is chosen for Java is deferred to the spec, as stated above.
