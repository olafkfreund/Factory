---
status: draft
issue: 3737
intent: intent/2026-11-16-3737-sandbox-followups-2.md
---

# Spec: factory-sandbox follow-ups, second pass (#3737)

## Design

1. **Re-vendor.** Copy `shared/factory-sandbox/agent_sandbox/*` from hub commit
   `92663f47d5db78e1ee7c5a7e89e365f5b4e1ea62` (#3735, on `main`) to
   `apps/backend/agent_sandbox/` in AIFactory, PFactory, TFactory; write that SHA to
   `.hub-sha` and to `HUB_SHA` in `.github/workflows/agent-sandbox-drift.yml`. Only
   `env.py` differs from the current pin. PFactory's extra `_invariants.py` stays.
   Fix service tests whose verdict tables change (`*_KEY_FILE`, `GL_TOKEN`, proxy userinfo).
2. **Runner env, PFactory and TFactory.** Codex review of the first draft showed runners
   read far more denied names than a keep list can safely cover (S3 store credentials,
   `TFACTORY_VERIFY_*` Secret references, Confluence/GitBook/Notion tokens, operator-named
   env, the opt-in Anthropic key). So the scrub is a short strip list, not an allowlist.
   `server/utils/subprocess_env.py` gains `RUNNER_STRIP` and `make_subprocess_env` drops
   those names from the `os.environ` copy, then applies the existing Anthropic strip and
   `extra` exactly as today. `RUNNER_STRIP` holds only names with no read anywhere in
   `apps/backend` (grep of the name outside `core/child_env.py` and `agent_sandbox/`
   returned no runtime read in either service; a prompt-text example is not a read): `JWT_SECRET`, `APP_JWT_SECRET`,
   `APP_DATABASE_URL`, `AIFACTORY_TOKEN`, `AIFACTORY_MARKER_NONCE`,
   `AIFACTORY_TRUSTED_CONTRACT`, `APP_CFACTORY_READ_KEY`, `CFACTORY_READ_KEY`,
   `NIX_ACCESS_TOKENS`, `NIX_CONFIG`. Compared in upper case, as `child_env` does.
   Every other name, credentials included, passes as before. `DATABASE_URL`,
   `APP_API_TOKEN`, `S3_*`, MCP keys and provider keys stay: runners read them.
   Tightening further needs a per-runner inventory and is a separate change.
3. **Dumpable.** PF and TF get `core/process_hardening.py` with `make_non_dumpable` and
   `require_non_dumpable` (the AIFactory functions, without the stray-process code).
   `server/main.py` calls it first in `if __name__ == "__main__"` (the Dockerfile CMD is
   `python -m server.main`). It fails closed, as in AIFactory.
4. **AWS catalog residual (AIFactory).** `_probe_aws` returns
   `AWS_SHARED_CREDENTIALS_FILE` (and `AWS_CONFIG_FILE` when it exists) in `env_vars` for
   the profile, `env:AWS_PROFILE` and default-file branches; the `env:AWS_PROFILE` branch also
   returns `AWS_PROFILE` itself, which the agent allowlist does not pass. The server then finds the file
   under the private HOME, and the #3720 skip no longer drops it. `KUBECONFIG` already
   carries an absolute path, which the private HOME does not hide; no change.

## Alternatives rejected

- A full allowlist, or a keep list over the Policy deny set: the runners read about 100
  service-tuning names and many denied credential names; a miss breaks a live run with
  no test (Codex review of the first draft found four such misses).
- AgentHome in PF/TF for item 3: a larger lifecycle port than one `prctl`.
- Hub change for other remotes now: services cannot vendor it until it is on hub `main`,
  and the fetch call sites would still need wiring. Left as a follow-up.

## Risks

- A name in `RUNNER_STRIP` that a runner does read would break it. Mitigation: each name
  has zero reads in `apps/backend`; a test pins that each is dropped and others pass.
- `PR_SET_DUMPABLE=0` blocks `py-spy`/core dumps of the server; same as AIFactory.
- Callers that merge a backend `.env` after `make_subprocess_env` can re-add a stripped name.
  That file is operator-supplied runner config by design and is not changed here.
- Drift gate: each service PR pins a hub SHA that is on `main`.

## Verification

Per service: its pytest for the touched tests, `ruff`, and the drift script against the
hub tree (`scripts/check_factory_sandbox_drift.py --canonical shared/factory-sandbox/agent_sandbox
--service <repo>/apps/backend/agent_sandbox`). New tests for `RUNNER_STRIP` in `make_subprocess_env`,
`process_hardening` and the AWS probe. Required CI green on the exact head SHA.
