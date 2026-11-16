---
status: draft
issue: 3720
author: olafkfreund
---

# Intent: factory-sandbox follow-ups from #3709 (first pass)

## Problem

#3709 landed the shared `factory-sandbox` package and deferred the items in #3720.
Verified against `main` (f512ced) and the services' `dev` (hub pin bf3cd95). The
service-policy points are observations about the current service Policies, not
guarantees of the shared code:

- `*_KEY_FILE` / `*_TOKEN_FILE` names are not matched by `CREDENTIAL_NAME`, so
  they reach non-runner children; `GL_TOKEN` (glab) is not on the deny list.
- Proxy variables are allowed and may carry `user:password@`; they reach the agent unchanged.
- `get_agent_env_blanks` blanks every non-allowed host variable, including
  `GIT_DIR` / `GIT_WORK_TREE` / `GIT_INDEX_FILE` / `GIT_COMMON_DIR`
  / `GIT_OBJECT_DIRECTORY`. A blank value makes git fail ("not a git repository").
- AIFactory `core/client.py` starts a catalog MCP server whose credential the
  sandbox cannot deliver: the probe finds AWS env keys, an IRSA role, an `az login`
  cache or the in-cluster Kubernetes account, but the server gets no `env_vars`, the
  host names are blanked and the real `HOME` is replaced by the private `AgentHome`.
  The server starts and fails on first use.

## Proposed outcome

Hub: credential-file names and `GL_TOKEN` are denied; proxy userinfo is stripped
(in `child_env` and in the agent blanks); names that break when blank are left
alone instead of blanked. They are path redirections, not secrets: the agent can
set them itself, so keeping a host value gives it nothing new. Services re-vendor the new hub pin. AIFactory skips a
catalog server it cannot give credentials to, and says so.

Every other #3720 item is closed with a written reason or moved to a new issue
(see Open questions).

## Affected users and systems

Factory `shared/factory-sandbox`; AIFactory, PFactory, TFactory `apps/backend/agent_sandbox/`
and their drift workflows; AIFactory `core/client.py`.

## Constraints

- No live-cluster change in this pass. Stdlib only in the hub package.
- Vendored copies stay byte-identical to the hub; hub merges to `main` first.
- No secret value in any log line.

## Open questions

Deferred to a new follow-up issue, each with a reason: PF/TF runner `RUNNER_KEEP`
(needs a per-runner variable inventory), same-UID reads (`PR_SET_DUMPABLE`, private
home, separate UID: the UID split is a pod securityContext change in factory-gitops),
`DOCKER_CONFIG` for compose (no compose call site in the services today),
PF/TF git metadata baseline, per-service Policy unification (needs owner decisions).
