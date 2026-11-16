---
status: draft
issue: 1959
intent: intent/2026-11-16-1959-tfactory-verify-gateway.md
---

# Spec: TFactory verify Jobs through the model gateway (flag, default off)

## Design

In TFactory `apps/backend/agents/verify_dispatch.py`, `_provider_env_entries()`
reads a new pod env `TFACTORY_MODEL_GATEWAY_URL` (gateway origin, no `/v1`).

- Unset or blank: unchanged output.
- Set: skip `OPENAI_API_KEY`, `OPENAI_COMPATIBLE_API_KEY`,
  `OPENAI_COMPATIBLE_BASE_URL` and `OLLAMA_API_KEY` in the passthrough loop, for
  both the literal and the Secret-reference branch. Then emit
  `OPENAI_COMPATIBLE_BASE_URL={url}/v1` (plain value) and
  `OPENAI_COMPATIBLE_API_KEY` holding the gateway token: a `secretKeyRef`
  (name `TFACTORY_VERIFY_PROVIDER_SECRET_NAME`, key `model-gateway-token`,
  optional) when that Secret is configured, else the pod value of
  `TFACTORY_MODEL_GATEWAY_TOKEN`. With no token available the key is omitted,
  so a call fails with 401 at the gateway; there is never a fallback to a direct
  key.
- Gemini, Claude OAuth, `OLLAMA_BASE_URL` and the other passthrough vars are
  untouched.

The provider reads `OPENAI_COMPATIBLE_*` already (`phase_config.py`), so no
provider code changes. Docs: one row each in `docs/environment-reference.md`
and a commented line in `.env.example`.

## Alternatives rejected

- Change only the Deployment env in factory-gitops: leaves Jobs on direct keys
  (the half-migration the epic warns about).
- A new provider type for the gateway: more code; the OpenAI-compatible path
  already fits.
- Fall back to the direct key when the gateway is down: defeats the control.

## Risks

- Flag on while the gateway lacks its Secret: verify LLM calls fail (503/401).
  Mitigation: default off, owner enables after the epic's stage 1 steps.
- Dropping `OPENAI_API_KEY` disables the native OpenAI provider in Jobs while
  the flag is on. Intended; the gateway only speaks OpenAI-compatible chat.

## Verification

Unit tests on `_provider_env_entries` and `build_verify_job_manifest`: flag off
is identical to today; flag on has the four direct vars gone (literal and
Secret-reference modes), base URL and token present, token is a `secretKeyRef`
when the Secret is configured. Repo lint (ruff) clean.
