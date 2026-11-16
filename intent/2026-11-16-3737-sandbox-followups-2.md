---
status: draft
issue: 3737
author: olafkfreund
---

# Intent: factory-sandbox follow-ups, second pass (#3737)

## Problem

#3720 left follow-ups. Four need no owner credential and no live-cluster change:
the service copies of `agent_sandbox` are behind the hub (#3735 changed `env.py`);
PFactory and TFactory pass the whole control-plane environment to their runner
subprocesses (`make_subprocess_env` copies `os.environ`, including secrets no runner reads); their web servers stay
dumpable, so a same-UID agent can read `/proc/<pid>/environ`; and the AWS catalog
MCP probe finds credentials under the real `HOME` that the private AgentHome hides.

## Proposed outcome

- AIFactory, PFactory and TFactory vendor the hub package at the #3735 commit.
- PF/TF runners no longer receive control-plane-only secrets (JWT, DB and trusted-plan
  names that no runner code reads, listed in the spec); every name a runner reads still passes.
- PF/TF web servers call `PR_SET_DUMPABLE=0` before serving, as AIFactory does.
- An AWS catalog server given a profile or default credentials file receives the
  file path in its env, so it works under the private HOME.

## Affected users and systems

AIFactory, PFactory, TFactory backends and the hub package in Factory.

## Constraints

No secret value is read or logged. No live-cluster change. Vendored files stay
byte-identical to the hub. The runner strip must not remove a name a runner reads.

## Open questions

Out of scope, kept as follow-ups: UID split (factory-gitops securityContext),
git metadata baseline for PF/TF (worktree lifecycle port), per-service Policy
unification (owner decision per difference), other remotes than `origin`
(needs a hub change merged first, then service wiring), `DOCKER_CONFIG` for compose
(no compose call site exists).
