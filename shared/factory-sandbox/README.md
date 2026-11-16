# factory-sandbox (canonical agent sandbox rules)

Single source of truth (Factory#3709) for the env allow/deny rules and git
config pins that AIFactory, PFactory and TFactory each copied into
`core/child_env.py` and `core/auth.py`. Stdlib only.

## What lives here

| File | Role |
| --- | --- |
| `agent_sandbox/policy.py` | `Policy`: the per-service rules as data. |
| `agent_sandbox/env.py` | `child_env`, `is_denied_env_key`, `is_agent_env_allowed`, `get_agent_env_blanks`, `without_host_secrets`, `BASE_DENY_EXACT`. |
| `agent_sandbox/git_pins.py` | `pin_git_config` (hooks, fsmonitor, ext transport, ssh, pager, editor, askPass, credential helpers) and `merge_driver_pins` (empty `merge.*.driver`, `filter.*.clean/smudge/process`). |
| `tests/` | Logic tests plus one verdict table per service Policy. |

The import name is `agent_sandbox` (not `factory_sandbox`, which would shadow
`scripts/factory_sandbox.py`).

## Policy

A service keeps its own `Policy` in its `core/child_env.py` shim; the hub holds
the logic and the names every service denies (provider and cloud keys,
`GITHUB_TOKEN`, `GH_TOKEN`, `CFACTORY_READ_KEY`, `CFACTORY_GITHUB_TOKEN`,
`GITLAB_TOKEN`).

| Field | Meaning |
| --- | --- |
| `extra_env` | Env var naming the operator's extra allowed names. |
| `deny_exact`, `deny_pattern` | Service denials on top of the base set. |
| `allow_pattern`, `keep` | Names the agent may see; `keep` is never blanked. |
| `keep_is_allowed` | `keep` names pass `is_agent_env_allowed` (AIFactory). |
| `credential_blocks_allow` | `*_KEY`/`*_TOKEN` never match by pattern (PFactory, TFactory). |
| `strip_vars` | Upper-case names `child_env` always drops. |
| `blank_exempt` | Callable: names `get_agent_env_blanks` leaves alone. |

`child_env(policy, keep, extra, *, runner, agent, pin_git)`.

## Vendoring

Each service carries a byte-identical copy at `apps/backend/agent_sandbox/` plus
`apps/backend/agent_sandbox/.hub-sha` (the hub commit on `main` it was copied
from). Change the hub first. `scripts/check_factory_sandbox_drift.py` compares a
service copy with this directory; the per-service workflow
`agent-sandbox-drift.yml` runs it against the pinned hub SHA.
