---
status: draft
issue: 1959
spec: spec/2026-11-16-1959-aifactory-build-gateway.md
coders:
  1: you
  2: you
reviewers:
  - codex
---

# Plan: AIFactory build Jobs through the model gateway (flag, default off)

Approved spec decisions, carried over. Code lands in olafkfreund/AIFactory (base `dev`);
these artifacts live in Factory. In `build_job_env()`: read `AIFACTORY_MODEL_GATEWAY_URL`
(strip, drop trailing `/`) and `AIFACTORY_MODEL_GATEWAY_TOKEN` (strip). Flag unset: no
change. Flag set: skip `OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL`,
`OLLAMA_API_KEY` in the passthrough loop; set `OPENAI_COMPATIBLE_BASE_URL` = origin and
`OPENAI_COMPATIBLE_API_KEY` = token or `gateway-token-not-configured`. Keep
`OPENAI_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_CLOUD_BASE_URL`. Guarantee is only "the replaced
credentials (OpenAI-compatible key/URL, Ollama key) are absent from the Job env"; `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY` stay (saved endpoints and native Ollama are not rerouted).

## Steps

1. `apps/web-server/server/services/build_backend.py` `build_job_env` (~line 358): add a
   `_GATEWAY_REPLACED` frozenset, skip those names when the flag is set, then set the two
   gateway entries. Placeholder never a direct key. → verify by
   `ruff check` and the step 2 tests. Traps: ruff `S105` noqa on token-name constants; use
   plain imports; never log the token.
2. `tests/test_build_backend_kubejob.py`: tests for flag off, flag on, empty or whitespace
   token, a whitespace-only URL (= flag off), a trailing slash, and a token without a URL (= flag off). Add an autouse fixture that clears both gateway vars for the whole module. Clear the flag vars and `_PASSTHROUGH_BUILD_ENV` with monkeypatch. → verify by
   `pytest tests/test_build_backend_kubejob.py -q`.

## Tests

`pytest tests/test_build_backend_kubejob.py -q` (confirm run, not skipped), `ruff check`
and `ruff format --check` on touched files. Expect green.

## Rollback

Revert the AIFactory PR; the flag is unset everywhere, so behaviour is unchanged.
