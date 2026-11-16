---
status: approved
issue: 3727
spec: spec/2026-11-16-3727-review-low-findings-factory.md
coders:
  1: you
  2: you
  3: you
reviewers:
  - codex
---

# Plan: LOW review findings, Factory hub

Approved decisions (spec): (1) create label `bench-regression` idempotently with `gh label create --force` before first use in the regression step; (2) log, name-only and once per process with a dedicated dedup set, the `BLANK_BREAKS` names set in the host env in `get_agent_env_blanks`; no blanking or unsetting; (3) #3729 refuted, no change (product repos run `--service` against the pinned hub tree). Coders: all steps are small, done by the lead (no handoff: under the 3-step/3-file threshold per step).

## Steps

1. `.github/workflows/bench-nightly.yml` regression step (~line 72): add `gh label create bench-regression --force --description "Nightly benchmark regression" --color B60205` before `gh issue list`. Check: `tests/test_bench_nightly_workflow.py` (new, PyYAML: label-create precedes `--label bench-regression` in that step) passes.
   Traps: SHA-pinned actions untouched; jscpd budget, keep the test small.
2. `shared/factory-sandbox/agent_sandbox/env.py` `get_agent_env_blanks`: add `_logged_inherited: set[str]` and log once the `k.upper() in BLANK_BREAKS` names present in `os.environ`. Check: new `caplog` test in `shared/factory-sandbox/tests/test_env.py`: clear `env._logged_inherited` first (monkeypatch), call `child_env(agent=True)` with host `GIT_DIR` set, then `get_agent_env_blanks` twice: exactly one inheritance message, the value not logged, `GIT_DIR` not in blanks.
   Traps: stdlib only; file is vendored byte-exact, so product repos need a re-vendor (not in this PR); do not log values.
3. Run `pytest tests/ shared/factory-sandbox/tests/` and `ruff check`/format on touched files.

## Tests

`pytest -q tests/test_bench_nightly_workflow.py tests/test_check_factory_sandbox_drift.py shared/factory-sandbox/tests` all pass.

## Rollback

Revert the PR; the label stays harmlessly.
