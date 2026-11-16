---
status: approved
issue: 3720
spec: spec/2026-11-16-3720-sandbox-followups.md
coders:
  1: lead    # small tricky logic in one hub file; lead writes it
  2: lead    # byte-for-byte copies, run by the lead
  3: lead    # one loop in AIFactory client.py plus a test
reviewers:
  - codex    # read-only: diff review per repo
---

# Plan: factory-sandbox follow-ups from #3709 (first pass)

Approved decisions (from the spec): credential names `(_KEY|_TOKEN)(_FILE)?$` and
`GL_TOKEN` denied; proxy userinfo stripped for agent envs only, replacement only for
allowed names, fail closed if `@` remains; `BLANK_BREAKS` git path names are not blanked;
AIFactory skips a stdio catalog server of a credential provider when the probe has no
`env_vars`, warning with id and source; everything else deferred to one new issue.
Bases: Factory `main`, AIFactory/PFactory/TFactory `dev`.

## Steps

1. Hub `shared/factory-sandbox/agent_sandbox/env.py`, `tests/test_env.py`, `README.md`:
   change `CREDENTIAL_NAME`; add `GL_TOKEN` to `BASE_DENY_EXACT`; add `BLANK_BREAKS`,
   `_PROXY_NAME`, `_strip_userinfo(value) -> str | None` (None = fail closed);
   `child_env` rewrites inherited proxy values when `agent=True`;
   `get_agent_env_blanks` skips `BLANK_BREAKS` and returns the stripped value for an
   allowed proxy name. Stripping is applied to inherited values only, before `keep`
   and `extra` are merged (those stay unchanged); non-agent children keep the value;
   a malformed value (an `@` left) is blank in the blanks and dropped by
   `child_env(agent=True)`. Tests: each rule, denied proxy stays blank, scheme-less,
   percent-encoded, IPv6, malformed. → `cd shared/factory-sandbox && python -m pytest tests`
   (and ruff as the Factory CI does). Merge this PR first (coordinator), then take its
   merge SHA as HUB.
   Traps: stdlib only; the hub copy is byte-checked by `scripts/check_factory_sandbox_drift.py`.
2. Each service (AIFactory, PFactory, TFactory) worktree off `origin/dev`: copy
   `agent_sandbox/*.py` from hub HUB, write HUB to `agent_sandbox/.hub-sha`, update the
   pinned SHA in `.github/workflows/agent-sandbox-drift.yml`; add the services' own
   test for one new rule if their policy tests list names. → service tests under
   `apps/backend/tests` for child_env/auth/sandbox, and the drift check run against a hub checkout at HUB:
   `python <hub>/scripts/check_factory_sandbox_drift.py --canonical <hub>/shared/factory-sandbox/agent_sandbox --service apps/backend/agent_sandbox` (flags as in the script's argparse).
   Traps: AIFactory autonomy matrix (regenerate, never hand-merge); PFactory keeps
   `_invariants.py`; ruff "as" aliases: plain names.
3. AIFactory `apps/backend/core/client.py` catalog loop (~L960-975) and a test in
   `apps/backend/tests`: skip and report as in the spec. New `apps/backend/tests/test_client_catalog_creds.py`
   (call the extracted helper, no SDK): provider stdio server without `env_vars`
   skipped; with `env_vars` kept; http and operator servers kept; the warning contains
   the id and source and no env value. → `pytest apps/backend/tests/test_client_catalog_creds.py`.
   Same PR as step 2 for AIFactory.
4. File the follow-up issue for the deferred items; each PR body links this plan.

## Tests

Hub pytest; each service's sandbox-related pytest and the drift script; each PR's CI.

## Rollback

Revert the PRs. Services return to hub bf3cd95 by reverting their vendoring commit.

## Deviations

- Step 2 (re-vendor) cannot start in this round: the service drift workflows need a hub
  SHA on `main`, and the lead does not merge. The coordinator re-vendors after the hub PR
  merges. Step 3 (AIFactory catalog skip) does not depend on the hub and ships on its own.
- Step 3: the helper is `unusable_credential_reason` in `agents/tools_pkg/mcp_catalog.py`
  and the test is `tests/test_catalog_creds_skip.py` (repo-root `tests/`, not
  `apps/backend/tests`). It logs a warning only (the ratchet counts a new `print`).
- Step 4: follow-up issue is olafkfreund/Factory#3737.
