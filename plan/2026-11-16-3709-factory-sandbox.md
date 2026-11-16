---
status: draft
issue: 3709
spec: spec/2026-11-16-3709-factory-sandbox.md
coders:
  1: codex   # tricky: Policy-driven rules must reproduce three current rule sets
  2: agy     # mechanical move of pin_git_config / merge_driver_pins
  3: agy     # port of the three existing test suites
  4: coder   # drift gate, CI step, README: follows existing gate
  5: coder   # AIFactory shim
  6: agy     # PFactory shim and vendored copy
  7: agy     # PFactory git call sites (mechanical, many sites)
  8: codex   # TFactory shim, git call sites and signing logic
reviewers:
  - codex    # independent read of each diff against this plan
  - agy      # second independent read; failure is reported, not retried
---

# Plan: one shared factory-sandbox package (#3709)

Decisions carried from the approved spec (do not reopen):

- Package `shared/factory-sandbox/agent_sandbox/` in the Factory hub,
  stdlib-only, modules `env.py` and `git_pins.py`. The import name is
  `agent_sandbox`, not `factory_sandbox` (shadows `scripts/factory_sandbox.py`).
- Rules are data: one frozen `Policy` per service reproduces that service's
  current rules exactly (fields: `extra_env`, `deny_exact`, `deny_pattern`,
  `allow_pattern`, `keep`, `keep_is_allowed`, `credential_blocks_allow`,
  `strip_vars`, `blank_exempt`). Shared: logic, base provider/cloud key names, the three new
  deny names `CFACTORY_READ_KEY`, `CFACTORY_GITHUB_TOKEN`, `GITLAB_TOKEN`.
- `child_env(keep, extra, *, runner=False, agent=False, pin_git=True)`.
  AIFactory shim: `agent=False`, `pin_git=True` (as today). PF/TF shims:
  `agent=True`, `pin_git=False`; they add `git_env(keep, extra)` =
  `pin_git=True`. Public names stay in each service's `core/child_env.py`.
- Hub signature `merge_driver_pins(policy, cwd, run=None, env=None, check=None)`.
  Every service shim exposes the old call shape `merge_driver_pins(cwd,
  run=None, env=None)` bound to its Policy; AIFactory's binds
  `check=core.git_metadata.check_git_metadata`, PF/TF bind no check (metadata
  baseline for them is #3720). Call sites in services never pass `policy`.
- Git adoption in PF/TF: `git_env(...)` on every git subprocess;
  `merge_driver_pins` prefixed to checkout/add/commit/merge/diff argv and
  fail closed (writers: only for real writes, via the injected runner, result
  `ok=False` not an exception); `--no-ext-diff --no-textconv` on diff/show/log; commits always
  carry `-c commit.gpgSign=false` unless `TFACTORY_TRIAGER_GIT_SIGN` is on,
  then `-S -c gpg.program=<global gpg.program else gpg>`. `GITHUB_KEEP` kept
  for pushes (TFactory pushes with the gh credential helper).
- Distribution: hub canonical; each service vendors a byte-identical copy at
  `apps/backend/agent_sandbox/` with `apps/backend/agent_sandbox/.hub-sha`;
  a hub script `scripts/check_factory_sandbox_drift.py` plus a per-service
  workflow `agent-sandbox-drift.yml` (copy of `factory-github-drift.yml`).
- Out of scope, in #3720: runner `RUNNER_KEEP`, same-UID reads, proxy
  credentials, blank-versus-unset, dead catalog MCP servers, `DOCKER_CONFIG`,
  PF/TF metadata baseline. Do not touch `agent_service.py` (team f3710).

Phases. **A (hub, this branch `security/3709-factory-sandbox`, base `main`):**
steps 1-4, one PR with the three artifacts. **B (services):** starts only
after A is merged to hub `main` (the service workflows pin a hub SHA that
`assert-hub-pin-on-main.sh` requires on main) and, for PF/TF, after team
f3710's `agent_service.py` PR is on `dev`; rebase on `origin/dev` first.
Steps 5, 6 then 7, and 8 run in separate worktrees (5, 6 and 8 in parallel; 7 after 6) under
`/tmp/claude-1000/.../scratchpad/teams/f3709/<Repo>` and may run in parallel.

## Steps

A. Hub

1. `shared/factory-sandbox/agent_sandbox/__init__.py`, `env.py` (new):
   `Policy`; `is_denied_env_key(policy, name)`,
   `is_agent_env_allowed(policy, name)`, `get_agent_env_blanks(policy)`,
   `child_env(policy, keep, extra, *, runner, agent, pin_git)`,
   `without_host_secrets(policy, env)`; base deny set; dropped-name log
   (names only, once per process). Source of truth for behaviour:
   `origin/dev:apps/backend/core/auth.py` lines 100-260 and
   `core/child_env.py` in AIFactory; `core/child_env.py` in PFactory/TFactory.
   Ship three ready-made policy constructors only in tests, not in the
   package (service names live in the shims). → verify by
   `pytest shared/factory-sandbox/tests/test_env.py` (step 3); `env.py` imports `git_pins` for `pin_git_config`.
   Traps: stdlib only; ruff.toml/mypy per hub; no secret values in logs.
2. `shared/factory-sandbox/agent_sandbox/git_pins.py` (new): move
   `_GIT_PINS`, `pin_git_config`, `_MERGE_DRIVER_KEYS`, `merge_driver_pins`
   from `origin/dev:apps/backend/core/child_env.py` lines 36-135 (AIFactory),
   replacing the `core.git_metadata` import with the `check` parameter, and
   adding a `policy` parameter used only when neither `run` nor `env` is
   given (then `child_env(policy, agent=True)`, never deny-based). The PF/TF
   shims always pass `env=git_env()`. → verified with step 3
   (`test_git_pins.py`); steps 1-3 land as one commit series.
   Traps: keep the surrogateescape decode and the "key contains '='" refusal.
3. `shared/factory-sandbox/tests/test_env.py`, `test_git_pins.py` (new): port
   the cases of AIFactory `tests/test_merge_driver_pins.py`,
   `tests/test_child_process_env.py` and the PF/TF `tests/test_child_env.py`; add per-service verdict tables (allow/deny for
   a fixed list of names, one table per Policy as the services will define
   them), the three new deny names including through `extra_env`,
   `pin_git` on and off, and a temp-repo test that `merge.x.driver` and
   `filter.x.clean` are pinned empty. → verify by
   `pytest shared/factory-sandbox/tests -q` green.
   Traps: tests insert their own package root on `sys.path`; no network.
4. `scripts/check_factory_sandbox_drift.py` (new, modelled on
   `scripts/check_factory_github_drift.py`: `CANONICAL_FILES`, completeness
   guard, `--canonical/--service/--self-test`, `gate_evidence.digest`),
   `tests/test_check_factory_sandbox_drift.py` (new, modelled on
   `tests/test_check_factory_github_drift.py`),
   `.github/workflows/contracts.yml` (add the self-test next to the existing
   drift gates, near lines 130-175; the existing whole-directory `pytest`
   step must also take `shared/factory-sandbox/tests/`),
   `shared/factory-sandbox/README.md` (new: what lives here, Policy table,
   how a service vendors it, the `.hub-sha` and workflow contract),
   `ruff.toml` (exclude nothing: this is canonical code, linted). →
   verify by `pytest tests/test_check_factory_sandbox_drift.py`,
   `python scripts/check_factory_sandbox_drift.py --self-test`, `ruff check`,
   `ruff format --check`, `mypy`, and the jscpd budget check
   (`scripts/check_jscpd_budget.py`) as `contracts.yml`/`jscpd.yml` run them.
   Traps: the jscpd clone budget only ratchets down (do not copy the whole
   github gate; keep the new script small); `mypy.ini` applies.

B. Services (after A merged; HUB_SHA = hub merge commit on main)

5. AIFactory (base `dev`, branch `fix/3709-agent-sandbox`):
   `apps/backend/agent_sandbox/` (vendored copy + `.hub-sha`),
   `apps/backend/core/child_env.py` (shim: `Policy` from the current values
   in `core/auth.py` lines 100-260; re-export `pin_git_config`,
   `merge_driver_pins` bound with `check=check_git_metadata`, `child_env`
   with its current signature; keep `lfs_push_argv`, `lfs_upload`,
   `GITHUB_KEEP`), `apps/backend/core/auth.py` (`is_denied_env_key`,
   `is_agent_env_allowed`, `get_agent_env_blanks` call the shared functions
   with the Policy (keep the lazy import against the cycle; `_STRIP_VARS`
   becomes `Policy.strip_vars`); keep `_log_dropped`, `api_key_auth_enabled` as the
   `blank_exempt` callable), `.github/workflows/agent-sandbox-drift.yml`
   (copy of `factory-github-drift.yml`, tarball path
   `shared/factory-sandbox/*`), ruff/mypy config (exclude the vendored
   `apps/backend/agent_sandbox/` the way `factory_common` is excluded).
   First record the allow/deny verdicts of the OLD code for the verdict
   table, then swap in the shim and assert the same table. → verify by AIFactory's existing
   `tests/test_child_process_env.py`, `tests/test_merge_driver_pins.py`,
   `tests/test_git_metadata_baseline.py` unchanged and green; the new deny
   names test; `ruff check`, `ruff format --check`, mypy as in
   `.github/workflows`. Traps: the generated autonomy matrix conflicts after
   merges: regenerate, never hand-merge; ruff vs `standards/ruff.toml` on
   parenthesised `as` imports: use plain names; do not edit the vendored
   copy; the circular import `core.auth` <-> `core.child_env` must stay
   lazy as today.
6. PFactory (base `dev`, branch `fix/3709-agent-sandbox`):
   `apps/backend/agent_sandbox/` + `.hub-sha`,
   `apps/backend/core/child_env.py` (shim with its Policy; `CLAUDE_KEEP`,
   `SDK_ENV_VARS` unchanged; `agent=True`, `pin_git=False`; new
   `git_env`, `GITHUB_KEEP`, and a bound `merge_driver_pins(cwd, run, env)`),
   `.github/workflows/agent-sandbox-drift.yml`, vendored-dir lint exclusion as
   in step 5, and the verdict table recorded from the old code first,
   `tests/test_child_env.py` (existing cases unchanged; add the three new deny names, verdict table,
   `ANTHROPIC_API_KEY_FILE` unchanged).
   → verify by `pytest tests/test_child_env.py` plus the repo's backend suite
   subset that imports `core.child_env`; ruff and mypy per PFactory CI.
   Traps: do not edit `apps/web-server/server/services/agent_service.py`;
   `make_subprocess_env()` is unchanged.
7. PFactory git adoption (same worktree, after step 6):
   `apps/backend/tools/git_writer.py` (`_default_runner_fn` near line 132:
   `env=git_env(keep=GITHUB_KEEP)`; `write_tests_to_branch` near 155 and
   `write_paths_to_branch` near 321: compute `merge_driver_pins(repo_dir)` once,
   prefix `-c` pairs to every git argv, only when `not dry_run`, via the injected
   `runner_fn` when given; on `RuntimeError` return
   `GitWriteResult(ok=False, error=...)`, never raise;
   commit argv `-c commit.gpgSign=false`),
   `apps/backend/core/workspace/git_utils.py` (the `subprocess.run` sites at
   lines 116, 179, 194, 205, 240, 269, 391, 484: `env=git_env()`, pins on
   checkout/merge/diff, `--no-ext-diff --no-textconv` on diff/show/log),
   `apps/backend/merge/git_utils.py` (same pattern), a new
   `tests/test_git_utils_env.py` that patches `subprocess.run` and asserts each
   `core/workspace/git_utils.py` and `merge/git_utils.py` call carries
   `git_env()` env, the `-c key=` driver pins and `--no-ext-diff --no-textconv`
   on diff/show/log, and
   `apps/web-server/server/services/git_utils.py` `run_git_command` (line 60;
   used by `server/routes/git.py` for `fetch origin`): `env=git_env(keep=GITHUB_KEEP)`
   so authenticated fetch keeps `GH_TOKEN`/`GITHUB_TOKEN`, plus
   `-c core.gitProxy=` on fetch/pull/push; it runs git in the
   user's own project, so no driver enumeration there,
   `tests/test_git_writer.py` (the injected recorder bypasses `_default_runner_fn`,
   so add a test that patches `subprocess.run`, calls `_default_runner_fn`
   and inspects the real `env` argument: `GH_TOKEN` kept, `GIT_CONFIG_*` pins
   present; argv carries `-c commit.gpgSign=false`; a web-server test does the
   same for `run_git_command`; a temp repo with `merge.x.driver` and a `filter.x.clean` that writes a marker file
   proves neither runs). → verify by
   `pytest tests/test_git_writer.py tests/test_child_env.py` and the git_utils
   tests. Traps: dry-run argv logs in `git_writer` are asserted by existing
   tests: keep their order and add pins only to the executed argv, or update
   the assertions in the same commit.
8. TFactory (base `dev`, branch `fix/3709-agent-sandbox`): same files as 6
   and 7 for TFactory (`child_env.py` shim, `git_env`, vendored copy, drift
   workflow, `tools/git_writer.py` near lines 143, 244, 424, `core/workspace/git_utils.py`
   lines 116, 179, 194, 205, 242, 271, 395, 494, `merge/git_utils.py`,
   and the web-server helper `apps/web-server/server/routes/git.py`
   `run_git_command` (line 39; TFactory has no `services/git_utils.py`:
   `env=git_env(keep=GITHUB_KEEP)`) plus signing: in
   `_sign_enabled()` branches add `-c gpg.program=<global value, else gpg>`
   (looked up only when not `dry_run`, through the injected `runner_fn`)
   with `-S`, otherwise `-c commit.gpgSign=false`; keep
   `-c credential.https://github.com.helper=!gh auth git-credential` on the
   push exactly as at lines 373-385. The writer's `fetch` and
   `push` argv also get `-c core.gitProxy= -c remote.origin.uploadpack=git-upload-pack
   -c remote.origin.receivepack=git-receive-pack`, so a repo-local program
   there never runs with the token in env (add a test on the push argv). Tests: `tests/test_git_writer.py`,
   `tests/test_child_env.py` as in 6 and 7, plus a signing-off and a
   signing-on argv test. → verify by those suites, ruff, mypy.
   Traps: as 6 and 7.

## Tests

- Hub: `pytest shared/factory-sandbox/tests tests/test_check_factory_sandbox_drift.py -q`,
  `python scripts/check_factory_sandbox_drift.py --self-test`, `ruff check`,
  `ruff format --check`, `mypy` per `.github/workflows/contracts.yml`; hub CI
  green on the PR head SHA.
- Services: drift gate against the pinned hub SHA green; each service's own
  CI green on the PR head SHA; existing child_env, git_writer, git_utils and
  (AIFactory) merge-driver and git-metadata tests unchanged.
- Final review per repo: `codex review --base origin/<base>` plus agy plus a
  read against this plan (two rounds, three for security fixes).

## Rollback

Each PR is revertable alone. Services: revert the PR; the shim and vendored
copy go away and the previous `core/child_env.py` returns from git. Hub: revert
removes the package and gate; services pinned to it would then fail their drift
workflow, so revert the service PRs first. No data, schema or cluster change.
