---
status: draft
issue: 3727
author: olafkfreund
---

# Intent: LOW review findings, Factory hub (#3727, #3735, #3729)

## Problem

Three LOW findings from the wave 8 cross-PR review:

1. #3727: `.github/workflows/bench-nightly.yml` runs `gh issue create --label bench-regression`, but no step creates the label. On a fresh repo the call fails and no regression issue is created (the summary and artifacts are still published).
2. #3735: `get_agent_env_blanks` skips `BLANK_BREAKS` (`GIT_DIR`, `GIT_WORK_TREE`, ...) while `child_env(agent=True)` drops them, so the SDK agent inherits host values silently.
3. #3729: hub CI runs the drift checker with `--self-test` and its unit tests (`tests/test_check_factory_sandbox_drift.py`) but never `--service`; the question is whether any vendored copy is left unchecked.

## Proposed outcome

1. The step creates the label idempotently before use.
2. Verified: the skip is deliberate (spec 3720 item 3: a blank value breaks git, the SDK cannot unset, accepted risk). Outcome: the gap is no longer silent; a host value that reaches the agent is logged by name. No behaviour change.
3. Verified: AIFactory, PFactory and TFactory each run the checker with `--service apps/backend/agent_sandbox` against the pinned hub tree (`.github/workflows/agent-sandbox-drift.yml`, blocking). The hub holds no vendored copy. Refuted, no change.

## Affected users and systems

Hub nightly benchmark workflow; `shared/factory-sandbox` (vendored by three product repos, which need a re-vendor to pick up the log line).

## Constraints

No enforcement default flips. No product repo edits in this PR.

## Open questions

Whether services should `os.environ.pop` the BLANK_BREAKS names before launching the SDK: a behaviour change on the host process, left to the owner.
