# Nightly standing evaluation (Factory#3713)

A fixed 15-task subset of `benchmarks/swebench-verified-50.json` runs through
the pipeline, is scored by the official SWE-bench harness (never self-scored),
and is stored with what produced it. Each run is compared with the previous one.
This is quality, not the seam gate: `parr-nightly.yml` checks that services talk
to each other; this checks that the agents produce correct patches.

**Cadence: weekly (decision 2026-11-16, was nightly).** `.github/workflows/bench-nightly.yml`
(the file keeps its name) runs Sundays 01:00 UTC, but only when the repo variable
`BENCH_ENABLED` is `true`; `workflow_dispatch` always runs. Until the owner sets the variable the
scheduled run is skipped, so nothing waits on a runner that does not exist. The spend cap is
enforced in code (see Cost), which is the condition for having a schedule at all.

**Why not an in-cluster CronJob.** The official SWE-bench harness builds and runs a Docker
container per task; the k3d nodes have no Docker daemon, and a Docker-in-Docker pod would need a
privileged container, which the sandbox rules forbid. The runner path keeps the harness
host-side. Revisit when a rootless harness exists.

## What runs

- Config: `benchmarks/nightly-config.json` (task ids, `tier`, per-task `timeout_min`,
  `per_task_token_cap`, `total_token_budget`, `regression_drop_tasks`, `min_paired`,
  `prompt_globs`, and the 2026-07 outcomes for the same ids as `baseline`).
- `scripts/benchmarks/nightly_eval.py run | compare | report`.
- Each run writes `<NIGHTLY_RESULTS_DIR>/<run_id>.json` (`run_id` is a UTC
  timestamp, so two runs on one day never overwrite each other).

## What each result records

- `provenance.models_configured`: role to model id read from AIFactory's
  `DEFAULT_PHASE_MODELS` plus `NIGHTLY_MODEL_OVERRIDES` (must mirror the server's
  environment). These are aliases and intent; `tasks[].models_observed` lists the
  model strings found in each task's `token_usage.json` / `COMPLETED.json`.
- `provenance.prompt_hash`: sha256 of the files matching `prompt_globs` in the
  AIFactory checkout.
- `provenance.commits`: `git rev-parse HEAD` of Factory and each `<SERVICE>_DIR`
  checkout (`null` when not set; never guessed).
- `label`: `factory-pipeline-<8 hex>` of the three above, used as the
  prediction `model_name_or_path` (replaces the old `MODEL_NAME` constant).
- Per task: pipeline status, tokens, cost, duration, `over_cap`, and the harness
  outcome (`resolved`, `unresolved`, `empty-patch`, `harness-error`,
  `skipped_budget`, `driver_error`).

## Regression rule

Only tasks scored in both runs count (harness errors, budget skips and driver
crashes are excluded on both sides). Regression = net resolved falls by
`regression_drop_tasks` (2) or more, with at least `min_paired` (10) paired
tasks. `compare` exits 3; the workflow opens or refreshes an issue labelled
`bench-regression`. The report also notes a changed prompt hash or task list. When nothing could be
graded (harness failed) or too few tasks pair up, `run`/`compare` exit 4: the job
goes red, but no regression issue is opened.

## Cost (agree before enabling)

From the 2026-07 baseline: average 2.37M tokens and USD 1.15 per task, heavy tail
12.5M tokens. 15 tasks is about 36M tokens and USD 17 a run on average, about
USD 75 a month weekly (USD 520 nightly). The baseline ran on subscription OAuth, so this
draws quota rather than an API bill. Bounds, all in code: 15 tasks, `timeout_min` 45 per task
(on timeout the driver stops the task), and no new task starts once cumulative tokens reach
`total_token_budget` (40M) or cumulative cost reaches `total_cost_usd_budget` (USD 30). Both budgets and
`per_task_cost_usd_cap` (USD 4) are required keys: a config without them fails the run rather
than dropping the limit. The last task can overshoot either; a task without token evidence is
charged the per-task token cap, and one without a recorded cost the per-task USD cap.
`per_task_token_cap` (4M) is checked after the task and flagged as `over_cap`; the pipeline has
no mid-run token ceiling.

## Owner steps to enable

1. A self-hosted runner labelled `factory-bench` with Docker, the `swebench`
   Python package, a local AIFactory server (see `pipeline-driver-design.md`:
   `APP_HOST=127.0.0.1`, no stale `~/.aifactory/claude-profiles.json`) and model
   credentials.
2. Repo variables: `NIGHTLY_RESULTS_DIR` (absolute path on the runner, required),
   `BENCH_AIFACTORY_DIR` (required), `BENCH_PFACTORY_DIR`, `BENCH_TFACTORY_DIR`,
   `BENCH_CFACTORY_DIR`, `BENCH_AIFACTORY_URL`, optional
   `NIGHTLY_MODEL_OVERRIDES`. Repo secret `BENCH_APP_API_TOKEN` (the local
   AIFactory `APP_API_TOKEN`).
3. Agree the cost above, run `workflow_dispatch` once, then set the repo variable `BENCH_ENABLED=true`.

Try it without calling anything: `AIFACTORY_DIR=<checkout> python3
scripts/benchmarks/nightly_eval.py run --dry-run`.
