---
status: draft
issue: 3709
author: olafkfreund
---

# Intent: one shared factory-sandbox package for agent env and spawn rules

## Problem

AIFactory, PFactory and TFactory each carry their own copy of the agent
environment rules (`apps/backend/core/child_env.py`, plus `core/auth.py` in
AIFactory): `is_denied_env_key`, `is_agent_env_allowed`,
`get_agent_env_blanks`, `child_env`. The copies share names on purpose, but
they already differ (service prefixes, `pin_git_config`, `merge_driver_pins`,
`git_metadata`, `RUNNER_KEEP` exist only in AIFactory). Three copies drift,
which is how #3708 opened.

The drift has a security cost today:

- PFactory and TFactory run git (`tools/git_writer.py`,
  `core/workspace/git_utils.py`) in agent-writable repositories. A hook,
  clean filter, merge driver or fsmonitor set by the agent runs with the
  runner's credentials. AIFactory closes this with `pin_git_config` and
  `merge_driver_pins` (#1680, #1746); the other two do not have it.
- `CFACTORY_READ_KEY`, `CFACTORY_GITHUB_TOKEN` and `GITLAB_TOKEN` are dropped
  by default but are not on the deny list, so an operator can opt them in
  through `*_AGENT_ENV_EXTRA`.

## Proposed outcome

- One `factory-sandbox` package under `shared/` in the Factory hub owns the
  allow and deny rules, the spawn helpers and the git pins. The three
  services use it instead of their own copies, kept identical by a drift gate
  like the existing ones.
- PFactory and TFactory pin git config and merge drivers the way AIFactory
  does: the same command-scope pins, the same enumeration of merge drivers
  and content filters (fail closed on a git error), and no diff/textconv
  program or repo-local signing program run by their git calls.
- The three missing names are on the deny list for every service.
- Everything else in #3709 and its comment is tracked in follow-up issue
  #3720 with its own owner questions, not silently dropped.

## Affected users and systems

- Factory hub: `shared/`, `scripts/` drift gate, CI.
- AIFactory, PFactory, TFactory backends and web servers (`core/child_env.py`,
  `server/utils/subprocess_env.py`, git callers). Behaviour for agents changes
  only where a new deny name or a git pin applies.
- Operators who set `*_AGENT_ENV_EXTRA` to one of the three newly denied names
  lose that opt-in (intended).
- Team f3710 is changing project `.env` loading in PFactory and TFactory
  `agent_service.py` at the same time; adoption must rebase on its result.

## Constraints

- Each service keeps its current filtering mode and keyword arguments
  (AIFactory deny-based by default with `runner`/`agent`; PFactory and
  TFactory allow-based), so no child sees more than today.
- Must not change what an agent can see beyond the new deny names and git
  pins; existing per-service tests keep passing unchanged where possible.
- Stdlib only, importable from CI and coder pods (like `factory_common`).
- Names of the public functions stay, so call sites do not churn.
- Never print or log secret values; log names only.
- No live-cluster change. Service releases are the owners' decision.
- The git metadata baseline (AIFactory `core/git_metadata.py`, #1746/#1747)
  is bound to AIFactory's worktree lifecycle. It stays AIFactory-only in
  these PRs; its port to PFactory and TFactory is in #3720. The residual
  risk is stated: without a baseline PF/TF detect no tampering, but the
  pins and the call-time enumeration still neutralise merge drivers, content
  filters, hooks, fsmonitor and the `ext::` transport.
- A scope cut: first PRs are package, adoption and git pinning. Runner
  `RUNNER_KEEP`, same-UID reads, proxy credentials, blank-versus-unset and
  dead catalog MCP servers go to #3720.

## Open questions

None. The owner scoped the first round in the task: package, adoption and
git-hook pinning, with the rest filed as a follow-up.
