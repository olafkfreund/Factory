# Nightly standing evaluation (Factory#3713)

A fixed 15-task subset of `benchmarks/swebench-verified-50.json` runs through
the pipeline, is scored by the official SWE-bench harness (never self-scored),
and is stored with what produced it. Each run is compared with the previous one.
This is quality, not the seam gate: `parr-nightly.yml` checks that services talk
to each other; this checks that the agents produce correct patches.

**Status: the schedule is OFF.** The workflow `.github/workflows/bench-nightly.yml`
runs on `workflow_dispatch` only until the owner provides a runner and agrees the
cost below.

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
`bench-regression`. The report also notes a changed prompt hash or task list.

## Cost (agree before enabling)

From the 2026-07 baseline: average 2.37M tokens and USD 1.15 per task, heavy tail
12.5M tokens. 15 tasks is about 36M tokens and USD 17 a night on average, about
USD 520 a month. The baseline ran on subscription OAuth, so this draws quota
rather than an API bill. Bounds: 15 tasks, `timeout_min` 45 per task (on timeout
the driver stops the task), and no new task starts once cumulative tokens reach
`total_token_budget` (40M; the last task can overshoot, and a task without token
evidence is charged the cap). `per_task_token_cap` (4M) is checked after the
task and flagged as `over_cap`; the pipeline has no mid-run token ceiling.

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
3. Agree the cost above, run `workflow_dispatch` once, then uncomment `schedule`.

Try it without calling anything: `AIFACTORY_DIR=<checkout> python3
scripts/benchmarks/nightly_eval.py run --dry-run`.
