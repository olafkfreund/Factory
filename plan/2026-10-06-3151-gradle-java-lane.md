---
status: draft
issue: 3151
spec: spec/2026-10-06-3151-gradle-java-lane.md
---

# Plan: Gradle-built Java verifies in-cluster

## Approved decisions (carried from intent + spec)

- **Build it** (intent option A). The work is TFactory only. **No hub change:**
  `scripts/nix_provisioner.py` and its four vendored copies stay as they are, so
  there's no re-vendoring and no `HUB_PIN_SHA` bump.
- **The runner picks the build tool from the manifest at run time.** The Planner
  pin stays `(java, maven, unit)` and no registry descriptor is added. The plan
  shows `framework: maven` for Gradle-Java, and the lane's `argv` and JUnit
  evidence show what actually ran.
- **Rule:** Java runs **Gradle** only when the project has **no `pom.xml`
  anywhere** and has a Gradle marker (`settings.gradle(.kts)` or
  `build.gradle(.kts)`). Every other case, including both or neither, runs
  **Maven** exactly as today.
- **Toolchain:** Gradle-Java gets `java_environment(spec_dir, gradle=True)`,
  which adds `"gradle"` to `system_packages`. `generate_flake` prepends
  `_LANG_ATTRS["java"]` = jdk21 + maven, so the shell is jdk21 + maven + gradle.
  Maven-Java's flake is byte-identical to today's.
- **Reuse, don't fork:** `run_gradle_lane_via_nix` gains `env=`. Its module
  discovery, job script, evidence rule and JUnit merge are already
  language-neutral.
- **Out of scope:** Planner misdetection of Kotlin-DSL-only Java repos, mixed
  Java + Kotlin builds, pitest, and AIFactory's QA sandbox.
- **Done means** a real in-cluster run through the Java lane path with real
  JUnit counts, a mutated test that fails, and `maven-min` still green.

## Where

- Repo: `olafkfreund/TFactory`. Branch `fix/3151-gradle-java-lane` from
  `origin/dev`. The PR targets **`dev`**.
- Line numbers below are `origin/dev` @ `c2015a29`. Re-check them if dev has
  moved.
- Tests live at repo-root `tests/`, not `apps/backend/tests` as the spec says.
  That's a path correction, not a design change.
- Test command: `apps/backend/.venv/bin/pytest tests/ -m "not slow" -q` (CI
  `ci.yml:80`).

## Steps

1. **`apps/backend/agents/nix_env.py` `run_gradle_lane_via_nix` (L1139-1235):**
   - Add the keyword-only argument `env: dict[str, Any] | None = None`.
   - Replace `env=kotlin_environment(spec_dir)` in the `materialize_flake`
     call with `env=env if env is not None else kotlin_environment(spec_dir)`.
   - Add one line to the docstring: the env defaults to Kotlin's, and Java
     passes its own (#3151).

   → verify by: `pytest tests/test_nix_env.py tests/test_evaluator_kotlin_lane.py -q`
   passes unchanged.

   Traps: keep the parameter keyword-only (after `*`). Tests patch
   `agents.nix_env.run_gradle_lane_via_nix` with `lambda *a, **k`, so the
   signature change doesn't break them.

2. **`apps/backend/agents/nix_env.py` `java_environment` (L857-884):**
   - Add the keyword-only argument `gradle: bool = False`.
   - When it's true, return a copy of the env (contract-declared *or*
     synthesized) with `"gradle"` appended to `system_packages` if it isn't
     already there (case-insensitive), and `verify_commands` set to
     `["gradle test --no-daemon --console=plain"]`.
   - When it's false, return exactly what the function returns today.
   - Update the docstring: replace the "gradle is deliberately absent … names it
     in system_packages" sentence with "a Gradle build gets gradle via
     `system_packages` (`gradle=True`, #3151); Maven-Java's flake is unchanged".

   → verify by: the step 6 tests.

   Traps: never mutate the contract dict in place. `environment_from_contract`
   may return a shared object, so copy first (`dict(env)` and
   `list(env.get("system_packages") or [])`).

3. **`apps/backend/agents/evaluator.py`, new helper above
   `_resolve_java_runner_fn` (~L2263):**
   ```python
   def _java_build_tool(project_dir: Path) -> str:
       """'gradle' only when no pom.xml exists anywhere and a Gradle build does (#3151)."""
       from agents.nix_env import _GRADLE_BUILD_MARKERS, _GRADLE_ROOT_MARKERS  # noqa: PLC0415
       pd = Path(project_dir)
       if next(pd.rglob("pom.xml"), None) is not None:
           return "maven"
       for name in (*_GRADLE_ROOT_MARKERS, *_GRADLE_BUILD_MARKERS):
           if next(pd.rglob(name), None) is not None:
               return "gradle"
       return "maven"
   ```

   → verify by: the step 6 tests.

   Traps:
   - Keep the import lazy, the way the file already does for nix_env.
   - `rglob` on a missing dir yields nothing, which falls through to maven.
     That's correct.
   - The constants live at `nix_env.py:1000-1002`. Reuse them, don't redefine
     them.

4. **`apps/backend/agents/evaluator.py` `_resolve_java_runner_fn`
   (L2264-2297):**
   - Compute `tool = _java_build_tool(_project_dir)` once, in the outer
     function. Rename the parameter from `_project_dir` to `project_dir`
     because it's now used.
   - Import `run_gradle_lane_via_nix` and `java_environment` lazily next to
     `run_maven_lane_via_nix`.
   - In `_run`, when `tool == "gradle"`, call
     `run_gradle_lane_via_nix(spec_dir, Path(project_dir_arg), hint=hint, env=java_environment(spec_dir, gradle=True))`.
     Otherwise keep today's maven call.
   - Make the fail-closed `DockerRunResult` name the chosen tool:
     - argv `["nix", "develop", "--", "gradle", "test"]` or today's mvn argv;
     - stderr `"java nix lane unavailable: TFACTORY_NIX_RUNNER_IMAGE unset"`,
       unchanged.
   - Update the docstring: Maven, or Gradle when the project has no pom.xml
     (#3151).

   → verify by: `pytest tests/test_evaluator_java_lane.py -q`. All existing
   tests must stay green, in particular
   `test_java_never_goes_through_the_gradle_or_pytest_lane` (L93): its project
   dir has no build files, so it gets maven.

   Traps:
   - Tests patch `agents.nix_env.run_*_lane_via_nix` on the module. The
     imports must stay inside the function (`# noqa: PLC0415`), or the patches
     bind past them.
   - Don't touch the Kotlin resolver or `_build_all_bundles`.

5. **Truth in comments and prompts:**
   - `frameworks/maven/descriptor.yaml`, header L9-13 ("Why Maven and not
     Gradle … Gradle-built Java is the follow-up"): rewrite it to say that the
     runner picks gradle when the project has no `pom.xml` (#3151), and that the
     hub table still carries maven only, with no hub change.
   - Same file, `context_block`: add one line after the Placement bullets: "The
     same placement and naming apply under a Gradle build (`src/test/java`,
     `*Test`, JUnit 5)."

   → verify by: `pytest tests/ -q -k "framework_registry or descriptor"` (the
   descriptor validator) passes.

   Traps: the descriptor is validated by
   `framework_registry/validator.py`. Change comments and `context_block` text
   only, no keys.

6. **Tests (`tests/test_nix_env.py`, `tests/test_evaluator_java_lane.py`):**
   - `test_nix_env.py`:
     1. `java_environment(spec)` (no contract) is unchanged: no gradle, and
        verify `mvn -B test`.
     2. `java_environment(spec, gradle=True)` lists `gradle` exactly once and
        verifies `gradle test …`.
     3. With a contract Java nix env that already lists `Gradle`, there's no
        duplicate and the contract dict isn't mutated.
     4. `generate_flake(java_environment(spec, gradle=True))` contains
        `jdk21`, `maven` and `gradle`, and `generate_flake(java_environment(spec))`
        contains no `gradle`.
     5. `run_gradle_lane_via_nix(..., env=X)` passes X to `materialize_flake`
        (monkeypatch `materialize_flake` to capture its `env` and return None).
   - `test_evaluator_java_lane.py`, one test per routing case, each with a
     tmp project. Patch both runners: the wrong one raises, the right one
     records its call and the `env` it got.
     1. `pom.xml` only → maven.
     2. `settings.gradle` + `build.gradle` only → gradle, and the `env`
        includes `gradle` with `language == "java"`.
     3. `pom.xml` + `build.gradle` → maven.
     4. Neither → maven.
     5. Gradle with the sandbox unconfigured (gradle runner returns None) →
        returncode 1, and the argv names `gradle`.

   → verify by: `pytest tests/test_nix_env.py tests/test_evaluator_java_lane.py tests/test_evaluator_kotlin_lane.py -q`
   is green. Then mutation-check the routing: temporarily make
   `_java_build_tool` always return `"maven"`. Cases 2 and 5 must fail. Revert.

   Traps:
   - **No `xml.etree` in tests.** The security-sink gate rejects it (S314,
     seen on #1712). Use textual asserts.
   - Run `ruff format` on the touched tests. CI's ruff-format check is
     blocking.

7. **Fixture `tests/fixtures/gradle-java-min/`, the Gradle twin of
   `maven-min`:**
   - `settings.gradle`: `rootProject.name = 'gradle-java-min'`.
   - `build.gradle`:
     - `plugins { id 'java' }`, `repositories { mavenCentral() }`;
     - dependencies `testImplementation platform('org.junit:junit-bom:5.10.2')`,
       `testImplementation 'org.junit.jupiter:junit-jupiter'` and
       `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'`;
     - `test { useJUnitPlatform() }`.
   - `src/main/java/Calc.java` and `src/test/java/CalcTest.java`: copy
     `maven-min`'s, so there are the same 3 tests.

   → verify by: step 8.

   Traps: **Groovy DSL on purpose.** `settings.gradle.kts` is a Kotlin manifest
   signal in `frameworks/gradle`. Gradle 9 needs `junit-platform-launcher`
   explicitly, and including it is harmless on 8.x.

8. **Live in-cluster proof, through the Java lane path** (before the PR, as
   evidence):
   - Find the TFactory pod's mount path for `tfactory-data` (the workspaces PVC
     the nix Job co-mounts) from the pod spec.
   - Copy `gradle-java-min` and `maven-min` to scratch dirs under that mount,
     each with a scratch `spec_dir`.
   - In the pod, run the **new code** over stdin (no files in the pod change):
     `_resolve_java_runner_fn(spec_dir, project_dir)(test_file, project_dir, 0)`,
     with `test_file = spec_dir/src/test/java/CalcTest.java`.
   - The run must pass these checks:
     1. gradle-java-min dispatches a real nix Job, the argv names `gradle`,
        `returncode == 0`, and `junit.xml` shows `tests="3" failures="0"`.
     2. After changing one assertion in the scratch `CalcTest.java`, the same
        call returns non-zero and `junit.xml` names the failing test.
     3. maven-min through the same call: argv names `mvn`, `returncode == 0`,
        and 3 tests.
   - Record the commands, the Job names and the junit snippets in the PR body.

   → verify by: the three outcomes above. If gradle can't write `build/` or
   `.gradle` as the Job's uid, the job script's existing copy-into-stage
   behaviour (from #1712) applies. If it doesn't, stop and report; don't
   improvise a fix.

   Traps: the pod runs the deployed image. Pipe the changed module source in
   over stdin, as #1712 did. The cluster recovered from the 2026-10-06 runtime
   restart (#3463), so check that the nix runner image is set
   (`TFACTORY_NIX_RUNNER_IMAGE`) before blaming the code.

9. **PR into TFactory `dev`:**
   - Title: `feat(evaluator): Gradle-built Java runs gradle test in-cluster (Factory#3151)`.
   - Body:
     - links to Factory `intent/`, `spec/` and `plan/2026-10-06-3151-gradle-java-lane.md`;
     - the step 8 evidence;
     - which steps the coder did.
   - All required checks green. Comment on Factory#3151 with the PR link, and
     close it once the PR merges and the image deploys.

## Tests

- `apps/backend/.venv/bin/pytest tests/ -m "not slow" -q` → green.
- `apps/backend/.venv/bin/pytest tests/test_nix_env.py tests/test_evaluator_java_lane.py tests/test_evaluator_kotlin_lane.py -q`
  → green, including the new tests from step 6.
- The routing mutation check in step 6 fails as expected, then is reverted.
- The live proof in step 8: three outcomes as stated.

## Rollback

Revert the TFactory PR. Every change is additive and behind the
"no pom.xml + Gradle marker" condition. Maven-Java and Kotlin paths are
untouched, and there's no hub, vendoring, schema or data change to unwind.
