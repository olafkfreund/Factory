---
status: draft
issue: 3737
author: olafkfreund
---

# Intent: factory-sandbox second pass: re-vendor and recorded decisions

## Problem

#3737 lists second-pass items from #3720. The hub fix (Factory#3735, plus the inherited-git-redirection log line in #3760) is on `main`, but AIFactory, PFactory and TFactory still vendor the older `env.py` pinned at `92663f4`, and the drift check compares them with the hub. Several other items need an owner decision.

## Proposed outcome

- The three services vendor the current hub `agent_sandbox/env.py` and pin the hub commit.
- Each remaining item has a recorded decision (below), taken as the recommended one.

## Affected users and systems

AIFactory, PFactory, TFactory `apps/backend/agent_sandbox/` and their `agent-sandbox-drift.yml` pins (PRs to `dev`).

## Constraints

Vendored files are byte-checked against the hub. The hub copy only changes `env.py`.

## Open questions

Decisions taken (owner delegation 2026-11-16): per-service Policy unification: no, keep the three declarations (differences are deliberate: AIFactory builds with Nix so `NIX_*` is allowed, PFactory and TFactory deny `NIX_CONFIG` and `NIX_ACCESS_TOKENS`; the verdict tables in `shared/factory-sandbox/tests/policies.py` pin them). Same-UID reads: accept `PR_SET_DUMPABLE=0` (merged) as the mitigation; the UID split is a pod securityContext change in live pods and is deferred until a second reason to restructure the pods exists. `DOCKER_CONFIG`: no compose call site, no work. Git metadata baseline for PF/TF and non-origin remote pinning: deferred as separate features with their own intent (they port a worktree lifecycle and need a design). AWS_PROFILE/KUBECONFIG catalog residual: keep as documented residual.
