---
status: draft
issue: 1573
intent: intent/2026-11-18-1573-runner-image-missing-not-run.md
---

# Spec: Treat docker exit 125 as "test never ran"

## Design

`agents/stability_runner.py` already owns `_SHELL_NOT_RUN_CODES = (126, 127)`
(#1401). Every consumer imports it: `classify_pytest_failure` (-> `environment`
-> `apply_environment_override` -> verdict `not_run`, kept out of handbacks),
`evaluator._mutation_from_codes`, and the pytest/ts/java/rust mutate probes
(-> `NOT_RUN`). Add 125 to that tuple and update the comment. One constant fixes
every lane that shells out to `docker run`, including jest, vitest, playwright
and java, because they share DockerRunner.

pytest itself only exits 0 to 5, so 125 cannot be a real test result.

## Alternatives rejected

- Fall back to the host-venv runner when the image is missing: hides a broken
  install and changes where tests run. Not needed to stop the misgrade.
- Parse "Unable to find image" in stderr: prose matching, the defect #1344
  avoided. The exit code is the contract.
- Route the workstation to the Nix Job runner: needs the cluster PVC, cannot
  work from a local process (that is #1574).

## Risks

A test command that itself exits 125 would read as not run. None of the
runners' tools do. Verdicts become `not_run` where they were `reject`, which
is the intent.

## Verification

New unit test fails without the change: `classify_pytest_failure("", 125)` is
`environment`, and `_mutation_from_codes` gives NOT_RUN for 125. Then re-run
the TFactory verify of aifactory-demo PR #610 with the images present.
