---
status: approved
issue: 1959
intent: intent/2026-11-16-1959-aifactory-build-gateway.md
---

# Spec: AIFactory build Jobs through the model gateway (flag, default off)

## Design

In `apps/web-server/server/services/build_backend.py`, `build_job_env()` reads
`AIFACTORY_MODEL_GATEWAY_URL` (stripped, trailing `/` removed) and `AIFACTORY_MODEL_GATEWAY_TOKEN` (stripped). When set:
`OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL` and `OLLAMA_API_KEY` from the
control plane are not forwarded; instead `OPENAI_COMPATIBLE_BASE_URL` = the gateway origin
(the provider appends `/v1`) and `OPENAI_COMPATIBLE_API_KEY` = `AIFACTORY_MODEL_GATEWAY_TOKEN`,
or the placeholder `gateway-token-not-configured` when empty after stripping (gateway answers 401; the key
is never omitted because the provider would fall back to `OPENAI_API_KEY`). The two flag
variables are added to nothing else: they are read from the control-plane env only, so the
token reaches the Job only as the replaced `OPENAI_COMPATIBLE_API_KEY`. Same shape as
TFactory#1520 (`verify_dispatch.py`), so the two stay consistent. Build Jobs take literal
env, so no `secretKeyRef` mode is needed.

Guarantee, narrowed: the Job env no longer carries a direct OpenAI-compatible or Ollama key.
It does not force every call through the gateway:  prefers a saved
OpenAI-compatible endpoint over env, and the native `ollama` runtime reads
`OLLAMA_BASE_URL`/`OLLAMA_CLOUD_BASE_URL`, which stay. With the flag on, a build routed to
native authenticated Ollama Cloud loses its key and fails; route it as OpenAI-compatible
instead (as TFactory#1520 does). Both limits are listed under owner_actions in the PR.

## Alternatives rejected

- Dropping `OPENAI_API_KEY` too: Codex seeds auth from it; plane C is an owner decision.
- A shared module with TFactory: vendored-file byte checks and two repos make a copy cheaper.
- Failing the build when the token is empty: a 401 from the gateway is equally loud and
  keeps `build_job_env` pure.

## Risks

Flag off by default, so no behaviour change until the owner sets it. If set without the
gateway Secret/egress, builds on the OpenAI-compatible plane fail with 401/502 (intended,
no silent direct fallback). Anthropic plane B and CLI logins are untouched.

## Verification

Unit tests in `tests/test_build_backend_kubejob.py`: flag off keeps direct keys; flag on
swaps URL and token and drops the Ollama key; empty token gives the placeholder and never a
direct key. Then ruff check and format check.
