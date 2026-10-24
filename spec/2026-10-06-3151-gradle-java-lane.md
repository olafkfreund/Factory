---
status: approved
issue: 3151
intent: intent/2026-10-06-3151-gradle-java-lane.md
---

# Spec: Gradle-built Java verifies in-cluster

All code references are TFactory `origin/dev` as read on 2026-10-06. The work
lands in TFactory. The hub (`scripts/nix_provisioner.py` and its vendored
copies) is not changed.

## Design

**The Java runner picks the build tool from the manifest at run time** (intent
open question 2, second option). The Planner's pin stays `(java, maven, unit)`
for every Java project. The evaluator decides deterministically, per project,
whether `mvn` or `gradle` runs.

### Rule

At the resolved project, Java runs Maven **unless there is no `pom.xml`
anywhere under the project and a Gradle build marker
(`settings.gradle(.kts)` / `build.gradle(.kts)`) exists**. Then it runs Gradle.

- Any project with a `pom.xml` behaves exactly as today. This is the "Maven-Java
  must not pay" constraint, met by construction.
- A project with neither marker also behaves as today (Maven, which fails
  loudly).
- A project with both prefers Maven. That is today's behaviour, and the rare
  dual-build repo gets the build tool it already got.

### Changes

1. **`agents/nix_env.py` `run_gradle_lane_via_nix` (L1139):** add a keyword
   argument `env: dict | None = None`, falling back to
   `kotlin_environment(spec_dir)` when it's `None`. Kotlin's call site is
   unchanged. This is the only change to the runner: `_gradle_module_dir`,
   `gradle_job_script`, `_gradle_evidence_failure` and the JUnit merge are already
   language-neutral.
2. **`agents/nix_env.py` `java_environment` (L857):** add a keyword argument
   `gradle: bool = False`. When true, add `"gradle"` to `system_packages` (on the
   synthesized env *and* on a contract-declared Java env, without duplicates) and
   set `verify_commands` to `gradle test --no-daemon --console=plain`.
   `generate_flake` already prepends `_LANG_ATTRS["java"]` (jdk21, maven), so the
   shell is jdk21 + maven + gradle. `gradle` is a real nixpkgs attr at the pinned
   rev, because Kotlin's descriptor already uses it. The cost is paid only by
   Gradle-shaped Java.
3. **`agents/evaluator.py` `_resolve_java_runner_fn` (L2264):** apply the rule
   once per project, using a small `_java_build_tool(project_dir) -> "maven" |
   "gradle"` helper next to it. On `"gradle"`, `_run` calls
   `run_gradle_lane_via_nix(..., env=java_environment(spec_dir, gradle=True))`.
   The fallback `DockerRunResult` argv/stderr names the tool actually chosen.
   The Kotlin path is untouched.
4. **Truth in comments and prompts:**
   - The `frameworks/maven/descriptor.yaml` header: "Gradle-built Java is the
     follow-up" becomes "the runner picks gradle when the project has no
     pom.xml (#3151)".
   - Its `context_block` gets one line: tests are placed and named the same
     under a Gradle build (`src/test/java`, `*Test`, JUnit 5). That's true of
     Gradle's `java` plugin, so the generated tests need no change.
   - The `java_environment` docstring.
5. **Fixture `tests/fixtures/gradle-java-min/`:** the Gradle twin of
   `maven-min`: `settings.gradle`, `build.gradle` (`java` plugin, JUnit
   Jupiter, `test { useJUnitPlatform() }`), `src/main/java/Calc.java` and
   `src/test/java/CalcTest.java`.
   - It uses the Groovy DSL on purpose. `frameworks/gradle` claims
     `settings.gradle.kts` as a **Kotlin** manifest signal (see Risks).

### What the user sees

A Gradle-Java subtask still reads `framework: maven` in the plan. The lane
result's `argv` (`nix develop ... -- gradle test`) and the JUnit evidence show
what actually ran. That mislabel is the accepted cost of this option.

## Alternatives rejected

- **A `frameworks/gradle-java` descriptor (intent option 2, first choice).**
  `_unit_framework_for_language` (`prompts_pkg/prompts.py:822`) picks among
  `java.unit` frameworks by "declares `source_extensions`", then alphabetically.
  A second `.java`-owning descriptor named `gradle-java` would sort ahead of
  `maven` and take **every** Java project, including Maven ones.
  - Fixing that means making the picker manifest-aware: a new code path in the
    Planner prompt, a descriptor, a registry-validator pass and prompt tests.
    All of that just to put the right word in the plan.
  - The generated tests are identical either way, so the label buys nothing
    the evidence doesn't already show.
  - Revisit if a Gradle-specific test convention ever has to differ.
- **Add gradle to `_LANG_ATTRS["java"]` in the hub (#3151 option 1).** Every
  Maven-Java task would pay the store cost. It also means a hub PR, re-vendoring
  into four services and pin bumps. It isn't needed, because
  `system_packages` already carries it.
- **A separate `run_gradle_java_lane_via_nix`.** That copies ~100 lines that
  differ only in the env. The `env=` argument is one line.
- **Choosing per subtask, from the test file path.** Gradle and Maven Java
  share the `src/test/java` layout, so the path can't tell them apart. The
  manifest is the only signal.

## Risks

- **Kotlin-DSL Java builds read as Kotlin in the Planner's last fallback.**
  `frameworks/gradle` maps `settings.gradle.kts` to `kotlin`, and manifest
  signals are signal 4 of 4 in language detection (`prompts.py` ~L870). Signals
  1–3 (changed-file extensions, spec file names, AC commands) come first, and a
  Java deliverable carries `.java`. A repo whose only evidence is
  `settings.gradle.kts` could still be pinned Kotlin. This is out of scope here:
  it's a Planner detection issue that predates this work. File it if it's seen.
- **Mixed Java + Kotlin Gradle builds** route by whichever language the
  Planner pinned, and both run `gradle test` over the whole build. That's
  acceptable and already out of scope per the intent.
- **The first Gradle-Java run resolves the Gradle distribution and plugins
  cold.** It's covered by the 900 s timeout already sized for Kotlin, and egress
  is measured open (#1712).
- **A dual-build repo (both `pom.xml` and Gradle)** keeps Maven. If its Maven
  build is stale, the verdict is wrong exactly as it is today: no regression,
  no fix.
- **Host:** TFactory only, in-cluster nix Jobs. Nothing changes for the
  docker-host junit lane.

## Verification

1. **Unit tests** (TFactory `apps/backend/tests`):
   - `test_nix_env.py`:
     - `java_environment(gradle=True)` lists gradle once, for both the
       synthesized and the contract env.
     - `java_environment()` is unchanged.
     - `run_gradle_lane_via_nix(env=...)` materializes the given env, not
       Kotlin's.
   - `test_evaluator_java_lane.py`:
     - A `pom.xml` project calls the maven runner.
     - A Gradle-only project calls the gradle runner with a Java env containing
       gradle.
     - A project with both calls maven.
     - A project with neither calls maven.
   - `test_evaluator_kotlin_lane.py` passes unchanged.
2. **Generated flake:** `generate_flake(java_environment(..., gradle=True))`
   contains `jdk21`, `maven` and `gradle` and evaluates (`nix flake show` / eval
   on the pinned rev).
3. **Live, in-cluster, through the evaluator's real Java lane path**, the way
   #1712 and TFactory#1321 were proven:
   - `gradle-java-min` runs `gradle test` to completion with real JUnit counts
     (passed > 0, failed = 0).
   - A mutated `Calc` makes the same lane fail with failed > 0.
   - `maven-min` still passes through the same path, as the regression check
     for the Maven route.
4. **CI:** TFactory's required checks are green on the PR.
