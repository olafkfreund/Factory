---
status: approved
issue: 3713
spec: spec/2026-11-16-3713-weekly-gated-bench.md
coders:   # every file-editing step is done by the lead: small, security-sensitive edits where a handoff costs more than it saves
  all: lead
reviewers:
  - codex   # independent read-only review of the diff (agy is off by owner decision)
---

# Plan: Weekly benchmark with a USD cap, gated on an enable variable

Decisions carried over from the approved spec:

`budget_spent(rows, config)` (raises `KeyError` if either budget is missing) returns true when cumulative tokens (missing evidence charged the per-task cap) reach `total_token_budget` or cumulative `cost_usd` reaches `total_cost_usd_budget` (USD 30). The key is required: a config without it fails the run instead of silently dropping the USD limit. Tokens are the primary cap and are always charged (the per-task cap when evidence is missing); a task with no recorded cost is charged `per_task_cost_usd_cap` (USD 4, required like the budgets) toward the USD cap, so missing cost evidence cannot bypass the guard. `cmd_run` calls it before every task. The workflow schedule is `0 1 * * 0`; the job has `if: workflow_dispatch || vars.BENCH_ENABLED == 'true'`. Cost: about USD 17 a run, USD 75 a month.

## Steps

1. `scripts/benchmarks/nightly_eval.py`, `test_nightly_eval.py`, `benchmarks/nightly-config.json`: add `budget_spent` and use it in `cmd_run`; config `total_cost_usd_budget: 30` and `per_task_cost_usd_cap: 4` (charged for a task with no recorded cost). Check: pytest.
2. `.github/workflows/bench-nightly.yml`, `tests/test_bench_nightly_workflow.py`: weekly cron, `if` gate, wording. Check: pytest.
3. `docs/benchmarks/nightly-eval.md`: cadence, in-cluster decision, cost, enable steps. Check: read.

## Tests

`pytest -q scripts/benchmarks tests/test_bench_nightly_workflow.py`; `ruff check scripts/benchmarks tests`.

## Rollback

Revert; the schedule disappears with it.
