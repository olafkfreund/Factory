---
status: approved
issue: 1959
spec: spec/2026-11-16-1959-tfactory-verify-gateway.md
coders:
  1: you
  2: you
  3: you
reviewers:
  - codex
---

# Plan: TFactory verify Jobs through the model gateway (flag, default off)

Approved spec decisions, carried over. Implemented in olafkfreund/TFactory
(base `dev`); these artifacts live in Factory. Env `TFACTORY_MODEL_GATEWAY_URL`
(origin, no `/v1`), default unset = no change. When set,
`_provider_env_entries()` drops `OPENAI_API_KEY`, `OPENAI_COMPATIBLE_API_KEY`,
`OPENAI_COMPATIBLE_BASE_URL`, `OLLAMA_API_KEY` from both branches (literal and
secretKeyRef), then emits `OPENAI_COMPATIBLE_BASE_URL={url}` (origin, provider appends `/v1`) and
`OPENAI_COMPATIBLE_API_KEY` = secretKeyRef (`TFACTORY_VERIFY_PROVIDER_SECRET_NAME`,
key `model-gateway-token`, optional) or the pod value of
`TFACTORY_MODEL_GATEWAY_TOKEN`; no token = key omitted; never a fallback.

## Steps

1. `apps/backend/agents/verify_dispatch.py` near `_provider_env_entries`: add
   `_GATEWAY_REPLACED` frozenset, skip those vars when the flag is set, append
   the two gateway entries. → verify by `nix develop -c apps/backend/.venv/bin/pytest tests/test_verify_dispatch.py -q`.
   Traps: ruff rules (no broad except); secret never in argv.
2. `tests/test_verify_dispatch.py`: add tests for flag off, flag on (literal
   mode, secret mode, no token). → verify by the same pytest command.
   Traps: clear the four vars with monkeypatch so host env does not leak.
3. `docs/environment-reference.md` and `.env.example`: document
   `TFACTORY_MODEL_GATEWAY_URL` / `TFACTORY_MODEL_GATEWAY_TOKEN`.
   → verify by `grep -c MODEL_GATEWAY docs/environment-reference.md .env.example`.

## Tests

`nix develop -c apps/backend/.venv/bin/pytest tests/test_verify_dispatch.py -q`
(the file skips if SQLAlchemy is missing; confirm it ran, not skipped); `ruff check` and `ruff format --check` on
touched files. Expect all green.

## Rollback

Revert the TFactory PR; the flag is unset everywhere so behaviour is unchanged.

## Deviations (implementation, 2026-11-16)

Found by `codex review`; code and this plan change in the same commit set.

- `OPENAI_API_KEY` is NOT dropped. The Codex provider seeds its auth from it and
  cannot use the gateway (plane C). Dropped: `OPENAI_COMPATIBLE_API_KEY`,
  `OPENAI_COMPATIBLE_BASE_URL` (direct), `OLLAMA_API_KEY`. The residual stays an
  owner decision in #1959.
- A missing token never omits `OPENAI_COMPATIBLE_API_KEY` (`phase_config` would
  fall back to `OPENAI_API_KEY`). No Secret: literal token, else the placeholder
  `gateway-token-not-configured` (gateway answers 401). With the Secret: the
  `secretKeyRef` is `optional: false`, so a Job without the key fails to start.
- All three steps were done by the lead; no external coder was used.
