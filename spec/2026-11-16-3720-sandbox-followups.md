---
status: approved
issue: 3720
intent: intent/2026-11-16-3720-sandbox-followups.md
---

# Spec: factory-sandbox follow-ups from #3709 (first pass)

## Design

Hub (`shared/factory-sandbox/agent_sandbox/env.py`), three rules every service gets:

1. **Credential names.** `CREDENTIAL_NAME` becomes `(_KEY|_TOKEN)(_FILE)?$`, so
   `*_KEY_FILE` / `*_TOKEN_FILE` follow the existing `*_KEY` / `*_TOKEN` rule: dropped
   from non-runner children, never matched by the allow pattern where
   `credential_blocks_allow` is set. `GL_TOKEN` joins `BASE_DENY_EXACT`.
2. **Proxy userinfo.** Variables named `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`,
   `FTP_PROXY` (any case) lose `user:password@` when the env is for the agent:
   `child_env(agent=True)` rewrites inherited values, and `get_agent_env_blanks`
   returns the stripped value for such a variable (the SDK merges `options.env` over
   the host env, so a replacement value works where a blank cannot). Only a name the
   policy allows gets a replacement; a denied or unapproved proxy name stays blank.
   Supported forms: `scheme://user:pw@host:port` and scheme-less `user:pw@host:port`
   (everything up to the last `@` before the first `/` is removed; IPv6 hosts have no
   `@`). Fail closed: if an `@` is still present after stripping, the variable is
   blank in `get_agent_env_blanks` and dropped by `child_env(agent=True)`. Non-agent
   children (git push, gh) keep the value: they may need proxy auth. Values restored
   through `keep` or `extra` are the caller's choice and are not rewritten.
3. **Blank is not unset.** `get_agent_env_blanks` skips `BLANK_BREAKS`: `GIT_DIR`,
   `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY`,
   `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_NAMESPACE`. A blank value makes git fail;
   the SDK cannot unset. These are path redirections, not secrets, and the agent can
   set them itself, so leaving a host value costs nothing. They stay out of the agent
   allowlist, and `child_env(agent=True)` drops them unless an operator names them in
   the policy's extra variable (an explicit owner choice). Accepted risk: a host that
   exports `GIT_DIR` already misdirects the control plane's own git, so no pod sets it. Not a per-Policy field: the set is the same everywhere.

Services re-vendor the new hub SHA (`apps/backend/agent_sandbox/*` + `.hub-sha`).

AIFactory `core/client.py`, catalog loop: a stdio catalog server whose provider needs
a credential in the process env (`github`, `gitlab`, `azure_devops`, `kubernetes`,
`aws`, `azure`) is skipped when its probe returned no `env_vars`, with a warning
naming the server id and the probe `source` (never a value). With no `env_vars` the
credential would have to come from a host variable the sandbox blanks (AWS keys,
IRSA, `AZURE_USE_MSI`, `KUBERNETES_SERVICE_HOST`) or from a file under the real
`HOME` the agent no longer has (`az login`, `~/.aws`). GitHub and Azure
service-principal carry `env_vars` and stay. Operator-declared and http servers are untouched.

### Item disposition

| Item | Result |
| --- | --- |
| `*_KEY_FILE`/`*_TOKEN_FILE`, `GL_TOKEN` | fixed, hub test |
| Proxy credentials | fixed (strip for agent), hub test |
| Blank vs unset | fixed for git path names, hub test |
| Dead catalog MCP servers | fixed in AIFactory, test |
| Runner `RUNNER_KEEP` (PF/TF) | deferred: needs a per-runner variable inventory |
| Same-UID reads | deferred: UID split is a factory-gitops securityContext change |
| `DOCKER_CONFIG` | deferred: no compose call site in the services today |
| PF/TF git metadata baseline, Policy unification | deferred: lifecycle port / owner decisions |

Deferred items go into one new follow-up issue with these reasons.

## Alternatives rejected

- Strip userinfo for every child: breaks authenticated proxies for git and gh.
- Per-Policy `blank_exempt` for the git names: same set for all services, duplicated three times.
- Put `env_vars` for AWS keys into the MCP server env: hands cloud keys to the agent
  process, which #3709 removed.
- Probe-aware reachability inside `mcp_credentials.py`: larger change, same result.

## Risks

- `_FILE` names now dropped from non-runner children: a child that read
  `AIFACTORY_API_TOKEN_FILE` or `AWS_WEB_IDENTITY_TOKEN_FILE` must name it in `keep`.
  Checked by running each service's suite against the new pin.
- A host-set `GIT_DIR` now reaches the agent CLI; accepted above.
- A skipped catalog server removes tools an agent had in name only (they failed on use).
- `AWS_PROFILE` or a `KUBECONFIG` under the real `HOME` carry `env_vars` but may point
  at files the private home hides: residual, listed in the follow-up issue.

## Verification

Hub: `pytest shared/factory-sandbox/tests` (new cases per rule). Each service: its
sandbox/child_env/auth tests plus the drift check against the new SHA. AIFactory: a
client test for the skip (no `env_vars` skipped and reported; GitHub kept). CI green on the PR heads.
