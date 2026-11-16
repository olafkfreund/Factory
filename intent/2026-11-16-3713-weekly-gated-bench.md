---
status: draft
issue: 3713
author: olafkfreund
---

# Intent: Weekly benchmark with a USD cap, gated on an enable variable

## Problem

Nothing measures pipeline quality on a schedule. #3727 built the nightly evaluation but left the schedule off and the cost unagreed. The recommended shape (issue thread) is a weekly run with a hard cost cap and the existing bench-regression issue path, enabled only if the cap is enforced in code.

## Proposed outcome

- Weekly schedule, running only when the repo variable `BENCH_ENABLED` is `true`.
- A USD budget enforced in code next to the token budget: no task is admitted once either is reached. This is an admission threshold: the last admitted task can overshoot (the pipeline has no mid-run ceiling), and the docs say so.
- The in-cluster question answered in the docs.

## Affected users and systems

`.github/workflows/bench-nightly.yml`, `scripts/benchmarks/nightly_eval.py`, `benchmarks/nightly-config.json`, `docs/benchmarks/nightly-eval.md`.

## Constraints

No spend without the owner setting the variable and providing a runner. Regression issue path unchanged.

## Open questions

In-cluster CronJob: not built. The SWE-bench harness needs a Docker daemon per task, which the k3d nodes lack and a privileged Docker-in-Docker pod would violate the sandbox rules. Decision: stay on the runner. Owner actions: runner, variables, secret, one dispatch run, then `BENCH_ENABLED=true`.
