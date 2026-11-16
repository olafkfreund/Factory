---
status: draft
issue: 1959
author: olafkfreund
---

# Intent: AIFactory build Jobs call models through the gateway (stage 4 slice, flag off)

## Problem

Epic #1959 stage 4. With `AIFACTORY_BUILD_BACKEND=kubejob` AIFactory runs each build as a Kubernetes Job.
`build_backend.py` (`_PASSTHROUGH_BUILD_ENV`, `build_job_env`) copies
`OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_BASE_URL` and `OLLAMA_API_KEY` from the
control plane into every build Job as literal env (when set on the control plane). Migrating only the Deployment would
leave Jobs on direct keys, a half-migration that reads as success. TFactory verify Jobs
already have a flag for this (TFactory#1520); AIFactory build Jobs do not.

## Proposed outcome

With `AIFACTORY_MODEL_GATEWAY_URL` set, a build Job gets the gateway origin as
`OPENAI_COMPATIBLE_BASE_URL`, the gateway client token as `OPENAI_COMPATIBLE_API_KEY`, and
no direct `OPENAI_COMPATIBLE_*` or `OLLAMA_API_KEY` value. The token comes from `AIFACTORY_MODEL_GATEWAY_TOKEN` on the control plane; if it is empty the Job gets a placeholder the gateway rejects with 401, never a direct key. `OPENAI_API_KEY` (Codex seeds auth from it, plane C) and the Ollama base URLs (no key, local endpoints) stay. Unset (default) changes nothing.

## Affected users and systems

AIFactory build Jobs (`build_backend.py`). Not PFactory (separate issue scope), not the
Anthropic plane B, not the Codex/Gemini CLI login files (plane C, owner decision in #1959).

## Constraints

Default off; no fallback to a direct key when the token is missing; secrets never in argv
or logs; no live-cluster change (the manifest PR and the Secret stay with the owner).

## Open questions

None.
