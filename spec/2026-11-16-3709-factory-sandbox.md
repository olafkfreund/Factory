---
status: approved
issue: 3709
intent: intent/2026-11-16-3709-factory-sandbox.md
---

# Spec: one shared factory-sandbox package for agent env and spawn rules

## Design

### D1. Package and name

`shared/factory-sandbox/` in the Factory hub, stdlib-only, importable as
`agent_sandbox`. The directory name follows the issue; the import name avoids
`scripts/factory_sandbox.py` (the container primitive of RFC-0005), which a
hub test could otherwise shadow.

```
shared/factory-sandbox/
  README.md
  agent_sandbox/__init__.py
  agent_sandbox/env.py        # rules, blanks, child_env
  agent_sandbox/git_pins.py   # pin_git_config, merge_driver_pins
  tests/test_env.py, tests/test_git_pins.py
```

### D2. Rules are data, behaviour is shared

`env.py` holds the logic the three copies share: `is_denied_env_key`,
`is_agent_env_allowed`, `get_agent_env_blanks`, `child_env`,
`without_host_secrets`, and the dropped-name log (names only). The rules
themselves differ in small ways that matter, so they are data in one frozen
`Policy`, and **each service's Policy reproduces that service's current rules
exactly**. Nothing is unified by guess:

| Field | AIFactory | PFactory / TFactory |
| --- | --- | --- |
| `extra_env` (opt-in list) | `AIFACTORY_AGENT_ENV_EXTRA` | `PFACTORY_...` / `TFACTORY_AGENT_ENV_EXTRA` |
| `deny_exact` | its current set | its current set (incl. `NIX_CONFIG`, `NIX_ACCESS_TOKENS`, `<PREFIX>_*`) |
| `deny_pattern` | current pattern | current pattern (has `SIGNING_KEY`) |
| `allow_pattern` | current pattern | current pattern (adds `HOME\|XDG_\w+_HOME\|CODEX_HOME`) |
| `keep` | `_AGENT_ENV_KEEP` | `CLAUDE_KEEP` |
| `keep_is_allowed` | True (keep names pass `is_agent_env_allowed`) | False (keep names are only exempt from blanking) |
| `credential_blocks_allow` | False | True (a credential-shaped name is not allowed by pattern) |
| `strip_vars` (dropped by name whatever the verdict) | `ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_FILE`, `AIFACTORY_TRUSTED_CONTRACT` | none (a regression test pins `ANTHROPIC_API_KEY_FILE` as today) |
| `blank_exempt` (callable) | `ANTHROPIC_API_KEY` when API-key auth is on | none |

`child_env` keeps the AIFactory keyword arguments `runner` and `agent` and
their defaults: the AIFactory shim calls it with `agent=False` (deny-based) as
today; the PFactory and TFactory shims bind `agent=True` (allow-based).
Public function names stay (`is_denied_env_key`, `is_agent_env_allowed`,
`get_agent_env_blanks`, `child_env`), so each service's `core/child_env.py`
becomes a thin shim binding its `Policy`, and no call site changes. In
AIFactory the rule functions live in `core/auth.py`; `is_denied_env_key`,
`is_agent_env_allowed` and `get_agent_env_blanks` there delegate to the shared
functions with the Policy (keeping the lazy import that avoids the
`core.auth`/`core.child_env` cycle), so the old API cannot keep duplicate
rules or miss the new denials. The
shared part is what is identical today (logic, the base provider/cloud key
names in all three sets, the three new names); the differences stay visible
as per-service data and a later unification is a separate, reviewed change.

### D3. Deny-list additions (issue comment)

`CFACTORY_READ_KEY`, `CFACTORY_GITHUB_TOKEN`, `GITLAB_TOKEN` join the deny
set of every Policy (the one shared base set), so `*_AGENT_ENV_EXTRA` cannot opt them in. `DOCKER_CONFIG` is not
added to a keep list here (its private-registry behaviour is in #3720).

### D4. Git pins: one implementation, applied where git runs

`git_pins.py` owns `pin_git_config(env)` and
`merge_driver_pins(cwd, run=None, env=None, check=None)`, moved from AIFactory
unchanged in behaviour. The only new seam is `check`: AIFactory passes its
`core.git_metadata.check_git_metadata` (baseline drift check, bound to
AIFactory's worktree lifecycle, #1746/#1747); PFactory and TFactory pass
nothing and get the key enumeration (merge drivers, clean/smudge/process
filters pinned empty, fail closed on any git error) without a baseline. The
baseline lifecycle for PF/TF is recorded in #3720, not built here.

`child_env(..., pin_git=True)` applies `pin_git_config`. AIFactory keeps
`pin_git=True` as today. PFactory and TFactory shims default `pin_git=False`
for generic children (docker, preflight, providers) and expose
`git_env(keep=(), extra=None)` = `child_env(..., pin_git=True)` for git
callers.

PFactory and TFactory adoption of the pins, by call site (the git calls
also gain `--no-ext-diff --no-textconv` on `diff`, `show` and `log`, since no
pin covers a repo-defined diff program):

- `tools/git_writer.py` `_default_runner_fn`: pass
  `env=git_env(keep=GITHUB_KEEP)`. TFactory's push already authenticates with
  `-c credential.https://github.com.helper=!gh auth git-credential` and reads
  `GH_TOKEN`/`GITHUB_TOKEN` from the inherited env, so those two names must
  be kept; the pins' own helper reset followed by the same gh helper keeps it
  working.
- Both `git_writer` modules (`write_tests_to_branch`, `write_paths_to_branch`)
  run `checkout` and `add`, which run content filters, so they call
  `merge_driver_pins(repo_dir)` once per write, prefix the `-c key=` pairs to
  every git argv of that write. Enumeration runs only for a real write
  (never in `dry_run`, which promises no subprocess) and goes through the
  supplied `runner_fn` when one is injected, as does the global `gpg.program`
  lookup. When enumeration raises `RuntimeError` the write fails closed through
  the existing contract: it returns `GitWriteResult(ok=False, error=...)`, it
  does not raise.
- Commit signing, in both writers and both write functions: the commit argv
  always carries `-c commit.gpgSign=false` unless TFactory's
  `TFACTORY_TRIAGER_GIT_SIGN` is on. When it is on, `-S` plus
  `-c gpg.program=<git config --global gpg.program, else gpg>`, so a
  repo-local `commit.gpgSign` or `gpg.program` is never honoured.
- `core/workspace/git_utils.py` and `merge/git_utils.py` (every `subprocess.run`
  of git there): `env=git_env()`, and
  `merge_driver_pins(project_dir)` prefixed to merge/diff/checkout argv that
  can run a driver or filter, as AIFactory's `core/workspace/git_utils.py`
  does (`-c <key>=` pairs before the subcommand).
- The web-server helper `run_git_command` (PF `server/services/git_utils.py`,
  TF `server/routes/git.py`): `env=git_env(keep=GITHUB_KEEP)` and
  `-c core.gitProxy=` on fetch/pull/push, no driver enumeration (it runs git in
  the user's own project and `fetch origin` needs the token).

### D5. Distribution and drift gate

Same model as `factory_common` and `factory-github`: the hub copy is
canonical, each service vendors a byte-identical copy at
`apps/backend/agent_sandbox/`, and a new
`scripts/check_factory_sandbox_drift.py` (modelled on
`check_factory_github_drift.py`, same exit codes, self-test, wired into
`contracts.yml` next to the existing drift gates, tests in `tests/`) fails CI
on drift. The web servers import the shim through the existing
`from core.child_env import ...` in `subprocess_env.py`; no second copy.
Their `make_subprocess_env()` (built from `os.environ.copy()`) is not
changed by these PRs, and adoption tests cover the shim, not that function.

### D6. Order of work and coordination

1. Hub PR: package, tests, drift gate, CI step, README (`security/3709-factory-sandbox`, also carrying these artifacts).
2. Per-service PRs on `dev`, one each for AIFactory, PFactory, TFactory:
   vendored copy, shim, tests green unchanged, and (PF/TF) the git-pin
   adoption. Independent of each other; PF and TF rebase on `dev` after team
   f3710's `.env` change to `agent_service.py` lands, and do not touch that
   file.
3. #3720 holds the deferred items, including a PF/TF metadata baseline.

## Alternatives rejected

- **Pip-installable package from the hub.** The services do not install from
  the hub today; coder pods and CI run from a checkout. A vendored,
  drift-gated copy matches `factory_common` and costs no new deployment path.
- **One flat module with `if SERVICE == ...` branches.** Hides the per-service
  names in code; a frozen `Policy` is data and testable.
- **Port `git_metadata` baseline to PF/TF now.** It is wired into AIFactory's
  worktree creation; a baseline without that lifecycle is a late-baseline
  warning only. Deferred to #3720 with the reason.
- **Pins in every PF/TF child.** Resetting `credential.helper` in generic
  children (docker, providers) is churn with no threat there; pins go where
  git runs.
- **Do the whole issue in one PR.** Runner env, same-UID reads and
  blank-versus-unset each need the owner's decision or a design; they would
  block the part that closes the git-hook gap.

## Risks

- **Behaviour drift on adoption.** Mitigation: each service's existing
  `test_child_env.py` cases run unchanged against the shim (new cases are added); the shared tests encode
  each service's current suite plus the table in Risks.
- **A Policy that differs from the old rules.** Mitigation: a per-service
  test pins the allow/deny verdict for a table of names (taken from each
  service's current tests plus the env of a CI run) before and after.
- **PF/TF git push loses credentials.** Mitigation: `git_writer` test with a
  fake runner asserts `GH_TOKEN` survives and the helper pin order; the
  TFactory push helper stays.
- **Vendored copies and byte checks.** `artifact_store.py` style byte checks
  mean no per-service edits to `agent_sandbox/`; ruff excludes it like the
  other vendored mirrors.
- **Rebase conflicts with f3710** in `agent_service.py`: avoided by not
  editing it.
- No live-cluster change; services are released by the owner.

## Verification

- Hub: `pytest shared/factory-sandbox/tests tests/test_check_factory_sandbox_drift.py`;
  drift gate self-test; ruff and mypy per hub CI (`contracts.yml`).
- Each service: its existing `tests/test_child_env.py` (PF, TF) and AIFactory
  env/git-pin tests (`tests/test_merge_driver_pins.py` and the child_env
  tests) green with the shim; new tests: deny of the three new names even via
  `*_AGENT_ENV_EXTRA`; PF/TF `git_writer` passes pinned env; PF/TF
  `git_utils` calls carry `merge_driver_pins` (a repo with
  `merge.x.driver` and a clean filter does not run it).
- Drift gate run against all three vendored copies.
- Each service's own CI on the PR head SHA green.
