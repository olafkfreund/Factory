---
status: draft
issue: 1959
author: olafkfreund
---

# Intent: TFactory verify Jobs call models through the gateway (stage 2, flag off)

## Problem

Epic #1959 stage 2: TFactory verify Jobs are separate pods. `verify_dispatch.py`
(`_SDK_PASSTHROUGH_ENV`, `_provider_env_entries`) copies `OPENAI_API_KEY`,
`OPENAI_COMPATIBLE_API_KEY`, `OLLAMA_API_KEY` and the OpenAI-compatible base
URL into every Job. Migrating only the Deployment would leave the Jobs on
direct keys, a half-migration that reads as success. The model gateway
(factory-gitops `apps/model-gateway`) exists and CFactory already uses it
behind a flag (CFactory#513), but TFactory cannot send a Job through it.

## Proposed outcome

With `TFACTORY_MODEL_GATEWAY_URL` set, a dispatched verify Job gets
`OPENAI_COMPATIBLE_BASE_URL={url}/v1` and a gateway client token as
`OPENAI_COMPATIBLE_API_KEY`, and carries no `OPENAI_API_KEY`, `OLLAMA_API_KEY`
or direct OpenAI-compatible key. Unset (the default) the Job env is
byte-identical to today. Nothing in the cluster changes in this round.

## Affected users and systems

TFactory `apps/backend/agents/verify_dispatch.py`, its tests and env docs.
Operators who later turn the flag on (owner step, needs the gateway Secret).

## Constraints

- Default off; no fallback to a direct key when the flag is on.
- No secret in any manifest; the token is read from the pod env or a
  `secretKeyRef`, like the other provider secrets.
- Gemini, Claude OAuth and CLI-login providers are unchanged (planes B/C).
- No live-cluster change, no credential created.

## Open questions

None. Enabling it needs the gateway Secret and egress decision (owner, in #1959).
