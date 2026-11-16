---
status: draft
issue: 3727
intent: intent/2026-11-16-3727-review-low-findings-factory.md
---

# Spec: LOW review findings, Factory hub

## Design

1. #3727: in `bench-nightly.yml`, before `gh issue list`, add `gh label create bench-regression --force --description ... --color ...` (idempotent: `--force` updates an existing label). Same step, same `GH_TOKEN`; `issues: write` is already needed by `gh issue create`, which also covers labels. Regression test: `tests/test_bench_nightly_workflow.py` parses the workflow YAML and asserts the label-create command precedes any `--label bench-regression` use in the same step.
2. #3735: in `get_agent_env_blanks`, log (names only, once per process, with its own module-level dedup set, NOT `_log_dropped`/`_logged_dropped`, which `child_env(agent=True)` fills first and would swallow the message) the `BLANK_BREAKS` names that are set in the host env and so reach the SDK agent. No blanking, no unsetting: a blank breaks git, and the SDK cannot unset (spec 3720 item 3, accepted). Test in `shared/factory-sandbox/tests/test_env.py` with `caplog`: call `child_env(agent=True)` first, then `get_agent_env_blanks` twice: exactly one inheritance message, no value logged, name not blanked. Product repos pick this up on their next re-vendor.
3. #3729: no change. Each product repo's `agent-sandbox-drift.yml` runs `--service apps/backend/agent_sandbox` against the pinned hub tree (blocking). The hub has no vendored copy to check.

## Alternatives rejected

- #3735 `os.environ.pop` of the names before launch: mutates the host process, a behaviour change. Left to the owner.
- #3735 neutralising value (e.g. a dummy path): any value redirects git; a blank errors.
- #3729 hub `--service` run: no target path exists in the hub.

## Risks

Log line only for #3735. For #3727 `gh label create --force` needs issues write permission, already used by the step.

## Verification

`pytest tests/test_bench_nightly_workflow.py shared/factory-sandbox/tests`; CI contracts job.
