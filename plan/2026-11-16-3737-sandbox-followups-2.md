---
status: draft
issue: 3737
spec: spec/2026-11-16-3737-sandbox-followups-2.md
coders:
  1: lead (a copy and a SHA edit; nothing to hand off)
  2: lead
  3: lead
  4: lead
  5: lead
  6: lead
  7: lead
reviewers:
  - codex  # independent read of each repo diff against this plan; agy is off by owner decision
---

# Plan: factory-sandbox follow-ups, second pass (#3737)

Self-contained summary. Hub commit to vendor: `92663f47d5db78e1ee7c5a7e89e365f5b4e1ea62`.
Four changes, per the spec: re-vendor in AIF/PF/TF; PF/TF runner env strip of
control-plane-only names (`RUNNER_STRIP`); PF/TF `PR_SET_DUMPABLE=0`; AIF AWS catalog env. Base `dev` for the three
services, `main` for Factory. Rebase on the current base before implementing and before the
last push. Branch `fix/3737-sandbox-followups-2` in each service; artifacts in Factory.

## Steps

1. Factory: this PR carries `intent/`, `spec/`, `plan/` only. Verify: `git diff --stat`
   shows three files. Traps: none.
2. AIFactory `apps/backend/agent_sandbox/{__init__,env,git_pins,policy}.py`, `.hub-sha`,
   `.github/workflows/agent-sandbox-drift.yml` (`HUB_SHA`): copy from the hub commit above.
   Fix `tests/test_agent_sandbox.py` and `tests/test_child_process_env.py` verdicts that move.
   Verify: drift script exit 0; `pytest tests/test_agent_sandbox.py tests/test_child_process_env.py`.
   Traps: ruff `as` alias sorting in parenthesised imports (use plain names); never
   hand-merge the generated autonomy matrix, regenerate it.
3. AIFactory `apps/backend/core/mcp_credentials.py` `_probe_aws` (lines ~270-310): add
   `AWS_SHARED_CREDENTIALS_FILE` (+ `AWS_CONFIG_FILE` if present) to the env_vars of the
   profile, `env:AWS_PROFILE` and default-file branches (and `AWS_PROFILE` itself in the `env:AWS_PROFILE` branch); test a non-default profile in `tests/test_catalog_creds_skip.py`
   or a new `tests/test_mcp_credentials_aws.py`. Verify: pytest those files.
   Traps: never print a credential value; the test uses a tmp HOME.
4. PFactory: re-vendor as step 2 (keep `_invariants.py`); fix its sandbox tests. Verify:
   drift script; `pytest tests/test_sandbox_credentials.py` and the child_env tests.
5. PFactory runner env: `apps/web-server/server/utils/subprocess_env.py`: add
   `RUNNER_STRIP = frozenset({"JWT_SECRET", "APP_JWT_SECRET", "APP_DATABASE_URL",
   "AIFACTORY_TOKEN", "AIFACTORY_MARKER_NONCE", "AIFACTORY_TRUSTED_CONTRACT",
   "APP_CFACTORY_READ_KEY", "CFACTORY_READ_KEY", "NIX_ACCESS_TOKENS", "NIX_CONFIG"})` and
   make `make_subprocess_env` drop names whose upper case is in it from the `os.environ`
   copy (before the Anthropic strip and `extra`). Nothing else changes. Tests (new
   `tests/test_runner_env_strip.py`): each strip name is dropped; `DATABASE_URL`,
   `APP_API_TOKEN`, `S3_SECRET_KEY`, `OPENAI_API_KEY`, `PFACTORY_MCP_KEY` pass;
   `ANTHROPIC_API_KEY` stripped by default and kept with the flag; `extra` wins.
   Verify: pytest that file. Traps: PF#1008 run guard (wave 3) may touch `run.py`; rebase
   first. Before editing, re-run the grep for each strip name; drop any with a runtime read (a prompt-text mention is not one).
6. PFactory dumpable: add `apps/backend/core/process_hardening.py`, call it first in
   `server/main.py` under `__main__`. Test: monkeypatch the libc call, assert fail-closed.
   Verify: pytest the new test.
7. TFactory: steps 4, 5 and 6 with the same `RUNNER_STRIP` (re-run the zero-read grep in
   TFactory; `tests/test_runner_env_strip.py` names `TFACTORY_MCP_KEY` instead of the PF key).
   Traps: TF#1510 run guard; `tools/runners/docker_runner.py` already has its own env list.

Then per repo: `codex review --base origin/<base>`, own read against this plan, rerun the
tests above plus the repo's lint (`ruff check`, `ruff format --check`), push, PR, wait for checks.

## Tests

`pytest` on the touched files per repo; drift script exit 0; `ruff check .`.

## Rollback

Revert each PR. The runner env change is isolated in `make_subprocess_env`; reverting it
restores `os.environ.copy()`.
