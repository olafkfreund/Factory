---
status: approved
issue: 3737
spec: spec/2026-11-16-3737-sandbox-second-pass-revendor.md
coders:   # every file-editing step is done by the lead: small, security-sensitive edits where a handoff costs more than it saves
  all: lead
reviewers:
  - codex   # independent read-only review of the diff (agy is off by owner decision)
---

# Plan: factory-sandbox second pass: re-vendor and recorded decisions

Decisions carried over from the approved spec:

In each service: copy hub `shared/factory-sandbox/agent_sandbox/env.py` over the vendored `env.py` (the other three files are identical), set `.hub-sha` and the drift workflow pin to a hub commit on `main` that contains the change, and run the service's sandbox tests.

Recorded decisions for the other items (owner delegation 2026-11-16, no code now): (1) Policy unification: not done; the three Policy declarations stay separate because the differences are deliberate (AIFactory builds with Nix so `NIX_*` is allowed; PFactory and TFactory deny `NIX_CONFIG` and `NIX_ACCESS_TOKENS` and allow `HOME`/`XDG_*`), pinned by the verdict tables in `shared/factory-sandbox/tests/policies.py`. (2) Same-UID reads: `PR_SET_DUMPABLE=0` (merged) is the accepted mitigation; the UID split changes live pod securityContext and waits for a second reason to restructure the pods. (3) `DOCKER_CONFIG`: no compose call site exists; revisit when one does. (4) Git metadata baseline for PF/TF and pinning non-origin remotes: deferred, each needs its own intent (a worktree-lifecycle port, and a design for remote pins). (5) `AWS_PROFILE`/`KUBECONFIG` under the real HOME in catalog MCP env: kept as a documented residual.

## Steps

1. AIFactory, PFactory, TFactory (one PR each, base `dev`, branch `fix/3737-revendor-sandbox` off `origin/dev`): copy hub `shared/factory-sandbox/agent_sandbox/env.py` from hub `main` HEAD (`b3844b8` when written; use the HEAD at implementation time) over `apps/backend/agent_sandbox/env.py`; write that full SHA to `apps/backend/agent_sandbox/.hub-sha` and to `HUB_SHA` in `.github/workflows/agent-sandbox-drift.yml`. Checks per repo: `python <hub>/scripts/check_factory_sandbox_drift.py --self-test`; `python <hub>/scripts/check_factory_sandbox_drift.py --canonical <hub>/shared/factory-sandbox/agent_sandbox --service apps/backend/agent_sandbox`; `.github/scripts/assert-hub-pin-on-main.sh <sha> HUB_SHA` (needs `GH_TOKEN`); the repo's sandbox tests (`pytest tests/test_agent_sandbox.py` in AIFactory; the matching sandbox/child_env tests in PFactory and TFactory).
   Traps: the pin must be an ancestor of hub `main`; vendored files are byte-checked, never hand-edit; use plain names in parenthesised imports (ruff sorting trap).
2. Issue comment with the decisions above; the issue stays open for the deferred items.

## Tests

Per service: the existing sandbox tests and the drift check.

## Rollback

Revert the PR.
