---
status: draft
issue: 3713
intent: intent/2026-11-16-3713-weekly-gated-bench.md
---

# Spec: Weekly benchmark with a USD cap, gated on an enable variable

## Design

`budget_spent(rows, config)` (raises `KeyError` if either budget is missing) returns true when cumulative tokens (missing evidence charged the per-task cap) reach `total_token_budget` or cumulative `cost_usd` reaches `total_cost_usd_budget` (USD 30). The key is required: a config without it fails the run instead of silently dropping the USD limit. Tokens are the primary cap and are always charged (the per-task cap when evidence is missing); a task with no recorded cost counts as USD 0 toward the USD cap, because the token cap still bounds it. `cmd_run` calls it before every task. The workflow schedule is `0 1 * * 0`; the job has `if: workflow_dispatch || vars.BENCH_ENABLED == 'true'`. Cost: about USD 17 a run, USD 75 a month.

## Alternatives rejected

In-cluster CronJob (no Docker for the harness). Leaving the schedule commented (nothing would ever run). A hard mid-task token ceiling (the pipeline has none; the last task can overshoot, which the doc states).

## Risks

A skipped scheduled run is silent; the doc says to check that a result exists after enabling. Last task can overshoot either cap.

## Verification

`pytest scripts/benchmarks tests/test_bench_nightly_workflow.py` and ruff.
