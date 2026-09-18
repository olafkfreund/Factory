---
status: draft
issue: 1712
intent: intent/2026-09-18-1712-kotlin-in-cluster-lane.md
---

# Spec: the Kotlin verify lane runs in-cluster

All code is in **TFactory** (`dev`) except the descriptor, which is hub-first.
Paths are relative to `apps/backend/` unless stated otherwise.

## What the code shows (read 2026-09-18)

- In-cluster lanes run as per-task nix Jobs via functions in
  `agents/nix_env.py`. `run_gotest_lane_via_nix` (L844, TFactory#543) is the
  model: `go_environment()` → `materialize_flake()` → `nix_runner_from_env()`
  sandbox → a generated job script (`set +e`, run the tests, echo an exit
  marker) → `nix develop path:<mount>#default --command bash <script>` →
  collect JUnit/coverage from a staging dir into a `DockerRunResult`.
- Evaluator wiring for Go (`agents/evaluator.py`):
  - partition at ~L2124: `lane in ("unit","functional") and language == "go"`
  - `_stage_go_test` (L2129): copies generated test files into the worktree
  - `_resolve_go_runner_fn` (L2144): wraps the runner; an unconfigured
    sandbox yields an honest failing result, never a silent pass
  - `_build_go_signal_bundle` (L2177): stability is computed once per module
  - `_build_all_bundles(..., jest, go)` (L2465) is the dispatcher
- **Today a Kotlin subtask falls into the `unit` bucket, which uses the
  pytest/`DockerRunner` path. That is wrong for Kotlin, and the cluster has no
  container runtime anyway.**
- Stability is decided purely on return codes (`stability_runner.py`:
  `{0}` → STABLE, one non-zero code → CONSISTENT_FAIL, mixed → FLAKY). JUnit
  and coverage are persisted as evidence (`_with_durable_artifacts`) but do
  not decide the verdict.
- The environment's `"network": "none"` is metadata. Only `DockerRunner`
  enforces it. Nix Jobs are dispatched by `tools/runners/job_dispatch.py` with
  the label `factory.io/kind=task`, which is the policy measured on #1712: public
  443 is open, and Maven Central, the plugin portal and services.gradle.org all
  complete.
- No prompt teaches Kotlin test generation (`prompts/planner.md` covers only
  Go's `_test.go`).

## Design

### 1. `kotlin_environment()` and `run_gradle_lane_via_nix()` (`agents/nix_env.py`)

- `kotlin_environment(spec_dir)`: mirrors `go_environment`. It uses the
  contract env if it is a Kotlin nix env, else synthesizes
  `{"language": "kotlin", "system_packages": [<the descriptor's nix.packages:
  kotlin, gradle, jdk21>], "verify_commands": ["gradle test"], "provisioning":
  {"method": "nix", "generated": True}}`. The packages are **read from the
  vendored descriptor** (`tools/runners/languages/kotlin.yaml`), not copied as
  literals, so hub and runner cannot drift. `network` is not set to `none`: the
  lane needs the network, and the value is only metadata anyway.
- `run_gradle_lane_via_nix(spec_dir, project_dir, *, hint=None, extra_env=None,
  timeout=900)`: same shape as the Go runner:
  - module root = the nearest dir holding `settings.gradle(.kts)` or
    `build.gradle(.kts)` above the hint, else the worktree root;
  - job script: `export GRADLE_USER_HOME=<stage>/gradle-home` (the Job runs
    as non-root, so `~/.gradle` may not be writable), then `cd <module> &&
    gradle test --no-daemon --console=plain 2>&1; echo __GRADLE_EXIT=$?`;
  - **JUnit:** gradle writes one `TEST-*.xml` per class under
    `build/test-results/test/`. The script merges them into
    `<stage>/junit.xml` under a single `<testsuites>` root (dropping each file's
    XML declaration), so `DockerRunResult.junit_xml_path` stays a single file
    for the existing evidence path. No coverage in this change
    (`coverage_xml_path=None`), the same as the Go bundle's `coverage_delta=None`.
  - returns None when the sandbox is not configured (the caller falls back
    honestly).

### 2. Evaluator wiring (`agents/evaluator.py`)

- Partition Kotlin subtasks exactly like Go: `lane in ("unit","functional")
  and language == "kotlin"`, and take them **out of** `unit` so they never
  reach the pytest runner.
- Add `_resolve_kotlin_runner_fn`, the twin of `_resolve_go_runner_fn`
  (unconfigured → a failing `DockerRunResult` with an explicit stderr).
- Reuse `_stage_go_test` and `_build_go_signal_bundle` as they are: neither
  contains anything Go-specific except its name (copy generated files to repo
  paths; module-wide stability computed once). Renaming them to
  `_stage_module_test` / `_build_module_signal_bundle` is left out, to keep the
  diff small; a comment at the Kotlin call site says they are shared.
- `_build_all_bundles(..., jest, go, kotlin)` gains a `kotlin` branch
  mirroring `go`.

### 3. The fixture (`tests/fixtures/kotlin-min/`)

A minimal Gradle Kotlin/JVM module (intent decision 1): `settings.gradle.kts`,
`build.gradle.kts` (the `kotlin("jvm")` plugin, JUnit 5, `useJUnitPlatform()`),
`src/main/kotlin/Calc.kt`, and `src/test/kotlin/CalcTest.kt` with a small
passing suite. It lives in TFactory, beside the lane it proves.

### 4. The descriptor (hub first)

`contracts/languages/kotlin.yaml` L18-22: replace the egress claim with the
truth. Egress is open (measured, #1712), and the lane runs in-cluster via
TFactory's `run_gradle_lane_via_nix`. Then re-vendor byte-exact into TFactory,
PFactory and AIFactory, and bump the drift pins in the drift-gate landing order.

## Alternatives rejected

- **A generic "run any descriptor command via nix" runner.** That is the right
  long-term shape (Swift would need it next), but the three existing runners
  differ in real ways (pytest staging, gotestsum JUnit, the jest npm install).
  The first Kotlin runner should follow the proven pattern. Generalize when
  the third descriptor-only language arrives.
- **Proving via a full TFactory task** (planner → generated Kotlin tests →
  lane). No prompt generates Kotlin tests yet (`planner.md` is Go-only), so
  this would test the generator, not the lane. Out of scope; it is filed as a
  follow-up (see Verification).
- **Using the repo's `./gradlew`** instead of nix `gradle`. The wrapper
  downloads its own distribution and is outside the flake's pinned toolchain.
  The descriptor declares nix `gradle`. A repo whose build requires the
  wrapper's exact Gradle version is a follow-up, if it happens.

## Risks

- **Non-root writes on the co-mounted worktree.** Gradle writes `build/` and
  `.gradle/` inside the module. If the worktree is not writable by the Job's
  uid, the lane fails. Mitigation: `GRADLE_USER_HOME` goes to the stage dir,
  and the plan's first live run checks the project dir. If needed, the job
  script copies the module into the stage dir and builds there.
- **First-run time.** Resolving the Kotlin plugin and dependencies with no
  cache costs minutes on every run (the Go lane has no equivalent). The timeout
  is 900 s; a persistent Gradle cache is a later optimization.
- **Three stability runs = three cold Gradle runs.** Acceptable for proving
  the lane; the cache follow-up also covers this.
- **Descriptor drift gate.** Re-vendoring touches three repos' pinned copies;
  landing order matters (pins bump before registration).

## Verification

- **Unit tests** (`tests/test_nix_env*.py` style, fake sandbox): the job script
  contains `gradle test --no-daemon`, the `__GRADLE_EXIT` marker and the
  `GRADLE_USER_HOME` export; an unset `TFACTORY_NIX_RUNNER_IMAGE` returns None;
  the JUnit merge yields one `<testsuites>` file from several `TEST-*.xml`.
  Evaluator: a `language=kotlin` subtask is routed to the Kotlin runner and
  never to the pytest `unit` runner (mutation: route it back to `unit` → the
  test fails).
- **Live, in-cluster (the proof #1712 asks for):** from the TFactory pod, call
  `run_gradle_lane_via_nix` on the fixture. It must dispatch a real nix Job,
  report `returncode=0`, and produce a JUnit file with the fixture's test count
  and 0 failures. Then mutate one assertion in the fixture's test (in a scratch
  copy), and the same run must report non-zero with the failing test in JUnit.
- **Descriptor:** the drift gates stay green in all three repos after the
  re-vendor.
- **Follow-up filed:** Kotlin test generation (`planner.md` guidance), so a
  planner-driven Kotlin task exercises this lane end to end.
