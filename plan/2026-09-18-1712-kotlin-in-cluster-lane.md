---
status: approved
issue: 1712
spec: spec/2026-09-18-1712-kotlin-in-cluster-lane.md
---

# Plan: the Kotlin verify lane runs in-cluster

## Approved decisions (self-contained)

- **Why:** TFactory runs lanes in-cluster only as per-language nix Jobs
  (pytest, go test, jest, deploy). Every other lane uses `DockerRunner`, and
  the cluster has no container runtime. Today a Kotlin subtask falls into the
  pytest `unit` bucket. Egress is **not** the blocker: public 443 is open, and a
  136.7 MB Gradle download completes in 2.1 s (measured, #1712).
- **Build** `run_gradle_lane_via_nix` in TFactory `agents/nix_env.py` on the
  `run_gotest_lane_via_nix` pattern (L844):
  - toolchain from `kotlin_environment()`, whose packages are read from the
    vendored `tools/runners/languages/kotlin.yaml` (`nix.packages`), not copied
    as literals;
  - job script: `GRADLE_USER_HOME` in the stage dir; `gradle test --no-daemon
    --console=plain`; `__GRADLE_EXIT` marker;
  - JUnit: merge the per-class `build/test-results/test/TEST-*.xml` into one
    `<stage>/junit.xml` under `<testsuites>`; no coverage;
  - returns None when the sandbox is unconfigured.
- **Wire** the evaluator: a Kotlin partition (`lane in (unit, functional)` and
  `language == "kotlin"`), taken **out of** `unit`; a
  `_resolve_kotlin_runner_fn` twin of the Go one; reuse `_stage_go_test` and
  `_build_go_signal_bundle` unchanged, with a comment that they are shared;
  a `kotlin` branch in `_build_all_bundles`.
- **Fixture:** a minimal Gradle Kotlin/JVM module at
  `tests/fixtures/kotlin-min/` in TFactory.
- **Scope:** `gradle test` only (no pitest). Proof via the runner itself, live
  in-cluster. Kotlin test *generation* is a follow-up issue (no prompt teaches
  it).
- **Descriptor:** hub `contracts/languages/kotlin.yaml` L18-22 corrected
  first; then each service re-vendors byte-exact **and** bumps `HUB_PIN_SHA`
  in `.github/workflows/verification-core-drift.yml` in the same PR. The pin
  must be a hub `main` SHA (`assert-hub-pin-on-main.sh`). The hub does not run
  the comparison itself; each service does, at its pin. So the order is hub
  merge first, then the services.
- Constraints: a lane is proven only by a real run with real test counts plus
  a mutated failing test; no change to the egress policy; out of scope:
  AIFactory's QA sandbox (AIFactory#1560).

## Steps

TFactory work on branch `feat/1712-gradle-nix-lane` off `dev`, one commit per
step.

1. **Fixture** `tests/fixtures/kotlin-min/`: `settings.gradle.kts`
   (`rootProject.name`), `build.gradle.kts` (`kotlin("jvm")` plugin, `mavenCentral()`,
   `testImplementation(kotlin("test"))` + JUnit 5, `tasks.test {
   useJUnitPlatform() }`, `kotlin { jvmToolchain(21) }` only if the nix JDK needs
   it), `src/main/kotlin/Calc.kt`, and `src/test/kotlin/CalcTest.kt` with 3 tests.
   → verify: locally, `nix develop` with `kotlin gradle jdk21` → `gradle test`
   passes with 3 tests (catches fixture mistakes before the cluster does).
2. **`kotlin_environment()`** in `nix_env.py`: reads `nix.packages` from the
   vendored descriptor via the existing descriptor loader
   (`tools/runners/language_descriptors.py`).
   → verify: a unit test asserts it returns the descriptor's packages, and
   that changing the descriptor changes the result (no literals).
3. **`run_gradle_lane_via_nix()`**, including a module-root resolver
   (`settings.gradle(.kts)` or `build.gradle(.kts)`) and the JUnit merge in the
   job script.
   → verify, in `tests/test_nix_env.py` with a fake sandbox: the script has
   `gradle test --no-daemon`, `__GRADLE_EXIT`, `GRADLE_USER_HOME=<stage>`;
   an unset `TFACTORY_NIX_RUNNER_IMAGE` returns None; the exit marker is parsed;
   the merge turns two `TEST-*.xml` into one `<testsuites>` file (running the
   script's merge snippet with bash on sample files).
4. **Evaluator wiring:** the Kotlin partition, `_resolve_kotlin_runner_fn`,
   and the `_build_all_bundles` branch.
   → verify: a routing test where a `language=kotlin` unit subtask reaches the
   Kotlin runner and not the pytest one. **Mutation:** put Kotlin back in `unit`
   and the test must fail.
5. **Gates:** ruff format (pinned), both cq-ratchet legs (ruff + mypy, base
   `origin/dev`), the full relevant pytest (`tests/test_nix_env.py`, evaluator
   tests), and each new test module collected **alone**.
6. **Live in-cluster proof** (before the PR, as evidence):
   - find the TFactory pod's mount path for `tfactory-data` (the workspaces
     PVC the nix Job co-mounts) from the pod spec;
   - copy `tests/fixtures/kotlin-min` to a scratch dir under that mount, with
     a scratch `spec_dir`;
   - in the pod, run the **new code** over stdin (no files in the pod change):
     `run_gradle_lane_via_nix(spec_dir, project_dir)`. It must dispatch a real
     nix Job and return `returncode=0`, and `junit.xml` must show `tests=3
     failures=0`;
   - edit one assertion in the scratch copy; the same call must return
     non-zero, with the failing test named in `junit.xml`;
   - if gradle cannot write `build/`/`.gradle` as the Job's non-root uid,
     apply the spec's mitigation (build a copy inside the stage dir), record it
     as a plan deviation, and re-run;
   - delete the scratch dirs.
7. **TFactory PR → `dev`** with the step 6 evidence. Merge when the checks are
   green and the threads are resolved.
8. **Hub descriptor:** a Factory PR editing `contracts/languages/kotlin.yaml`
   L18-22 to state that the lane is proven in-cluster via TFactory's
   `run_gradle_lane_via_nix` (#1712), egress is open (measured), and the
   docker-host substrate also works. Merge it; record its `main` SHA.
9. **Re-vendor ×3:** in TFactory, PFactory and AIFactory, copy the hub file
   byte-exact to the vendored path and set `HUB_PIN_SHA` in
   `verification-core-drift.yml` to the step 8 SHA, in one PR each (auto-merge).
   → verify: `vendored copies match` / `verification-core drift gate` green in
   each.
10. **Release:** TFactory through its release process (coordinate: another
    session released 0.9.26 today; check for an open release PR before
    starting one). AIFactory/PFactory: the descriptor change is data only and
    rides their next release.
11. **Close out:** file the follow-up (Kotlin test generation in
    `planner.md`), close #1712 with the step 6 evidence, and update memory.

## Deviations recorded during implementation

- **Step 2 (TFactory `e52abb61`):** `kotlin_environment()` does not read the
  descriptor itself. `generate_flake` already resolves descriptor-declared
  languages first and prepends their `nix.packages`, so the environment only
  names `language: kotlin`. Same intent (the descriptor is the single source,
  no literals), through the existing path. Tests run the real generator and
  swap the descriptor; hard-coding the packages fails two of them.

- **Step 3 (TFactory `97ceabae`):** build in `/tmp`, not the stage dir. The
  code documents that `/work` is read-only to the Job's uid (`_DEPS_TARGET`),
  and Gradle writes `build/` and `.gradle/` inside the module. So the job
  script copies the module to `/tmp/tf_gradle_src` and sets `GRADLE_USER_HOME`
  under `/tmp`; only the merged JUnit goes to the writable stage dir. This is
  the spec's mitigation, applied from the code's own documentation rather than
  after a failed live run.
- **Step 4 (TFactory `cc716cc4`):** there was nothing to take "out of `unit`".
  A Kotlin subtask matched no lane filter (pytest admits only Python), so it was
  dropped and a Kotlin-only plan came back `evaluated_empty`. The change adds the
  lane. Because the helper tests cannot see the call site, a `run_evaluator`
  test covers it; dropping `kotlin_completed` from the real call fails that test
  while the four helper tests stay green.

## Tests

```sh
# TFactory
.venv/bin/python -m pytest tests/test_nix_env.py -q -k "gradle or kotlin"
.venv/bin/python -m pytest tests/ -q -k "evaluator and kotlin"
# each new test module alone (collection-order free-riding)
apps/backend/.venv/bin/python scripts/cq_ratchet.py --tool ruff --base origin/dev ...
apps/backend/.venv/bin/python scripts/cq_ratchet.py --tool mypy --base origin/dev ...
```

Expected: every new test fails before its step's code and passes after; the
routing mutation fails; the live run reports 3/0, then non-zero on mutation.

## Rollback

- TFactory: revert the PR. Kotlin subtasks go back to the `unit` bucket (the
  current behaviour); nothing else uses the new runner.
- Descriptor: revert the hub PR and re-vendor the previous text with the pin
  bumped back. It is data only, so there is no runtime effect.
