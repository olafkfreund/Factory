---
status: draft
issue: 3737
intent: intent/2026-11-16-3737-sandbox-second-pass-revendor.md
---

# Spec: factory-sandbox second pass: re-vendor and recorded decisions

## Design

In each service: copy hub `shared/factory-sandbox/agent_sandbox/env.py` over the vendored `env.py` (the other three files are identical), set `.hub-sha` and the drift workflow pin to a hub commit on `main` that contains the change, and run the service's sandbox tests.

Recorded decisions for the other items (owner delegation 2026-11-16, no code now): (1) Policy unification: not done; the three Policy declarations stay separate because the differences are deliberate (AIFactory builds with Nix so `NIX_*` is allowed; PFactory and TFactory deny `NIX_CONFIG` and `NIX_ACCESS_TOKENS` and allow `HOME`/`XDG_*`), pinned by the verdict tables in `shared/factory-sandbox/tests/policies.py`. (2) Same-UID reads: `PR_SET_DUMPABLE=0` (merged) is the accepted mitigation; the UID split changes live pod securityContext and waits for a second reason to restructure the pods. (3) `DOCKER_CONFIG`: no compose call site exists; revisit when one does. (4) Git metadata baseline for PF/TF and pinning non-origin remotes: deferred, each needs its own intent (a worktree-lifecycle port, and a design for remote pins). (5) `AWS_PROFILE`/`KUBECONFIG` under the real HOME in catalog MCP env: kept as a documented residual.

## Alternatives rejected

Waiting for the next hub change (leaves the drift check red or pinned stale). Hand-editing the vendored file (breaks the byte check).

## Risks

A log line is added for inherited git redirection names (names only, never values). The pin must be an ancestor of hub `main`.

## Verification

The services' `agent-sandbox-drift` workflow and sandbox tests, and `assert-hub-pin-on-main.sh`.
