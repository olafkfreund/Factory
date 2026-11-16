---
status: draft
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
secretKeyRef), then emits `OPENAI_COMPATIBLE_BASE_URL={url}/v1` and
`OPENAI_COMPATIBLE_API_KEY` = secretKeyRef (`TFACTORY_VERIFY_PROVIDER_SECRET_NAME`,
key `model-gateway-token`, optional) or the pod value of
`TFACTORY_MODEL_GATEWAY_TOKEN`; no token = key omitted; never a fallback.

## Steps

1. `apps/backend/agents/verify_dispatch.py` near `_provider_env_entries`: add
   `_GATEWAY_REPLACED` frozenset, skip those vars when the flag is set, append
   the two gateway entries. → verify by `pytest tests/test_verify_dispatch.py -q`.
   Traps: ruff rules (no broad except); secret never in argv.
2. `tests/test_verify_dispatch.py`: add tests for flag off, flag on (literal
   mode, secret mode, no token). → verify by the same pytest command.
   Traps: clear the four vars with monkeypatch so host env does not leak.
3. `docs/environment-reference.md` and `.env.example`: document
   `TFACTORY_MODEL_GATEWAY_URL` / `TFACTORY_MODEL_GATEWAY_TOKEN`.
   → verify by `grep -c MODEL_GATEWAY docs/environment-reference.md .env.example`.

## Tests

`cd apps/backend && python -m pytest ../../tests/test_verify_dispatch.py -q`
(or the repo's Justfile equivalent); `ruff check` and `ruff format --check` on
touched files. Expect all green.

## Rollback

Revert the TFactory PR; the flag is unset everywhere so behaviour is unchanged.
