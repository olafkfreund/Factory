---
status: draft
issue: 1959
author: olafkfreund
---

# Intent: wire the gateway clients (CFactory, TFactory, AIFactory) as optional, default-off env

## Problem

The gateway exists (`apps/model-gateway`, namespace `gateway`) and three clients carry a default-off flag: CFactory#513, TFactory#1520, AIFactory#2070. Nothing in `factory-gitops` sets those flags, so the epic's stage 1, 2 and 4 checkpoints cannot start. The last decision recorded a blocker, "no CFactory release exists, the live image is cfactory:0.1.0". That is stale: CFactory has no tags by design, `main` was promoted on 2026-11-17 (f4f6c9d, #513 included) and the live image is `cfactory:sha-630ee1d`, which contains #513; the live TFactory (`sha-2a95581`) and AIFactory (`sha-1d03c52`) images contain #1520 and #2070. Task Job pods also cannot reach the gateway: `factory-sandbox-jobs-egress` excludes private ranges, so a Job given the gateway URL would fail closed. And nothing proves the 401/200 contract after the owner seeds the Secret except prose in `docs/model-gateway.md`.

Separately, epic #1958 acceptance item 3 (a production change's evidence trail answers: control objectives, agent or human author, autonomy tier, approver) has not been assessed against the data that exists.

## Proposed outcome

- The three clients' URL and token env are present in the manifests but absent from the running containers, so nothing changes until the owner seeds `factory/factory-secrets` keys `MODEL_GATEWAY_CLIENT_TOKEN` and `MODEL_GATEWAY_URL` (and the gateway Secret from `docs/model-gateway.md`).
- Task Job pods may reach the gateway pods on 8080 and nothing else new (a narrow permission that takes effect when the policy syncs; no client routes through it until configured).
- A read-only script proves "401 without token, 200 with it" from a token file, never printing the token.
- A written assessment of #1958 item 3: what answers it today, what does not, with the gap recorded as a plan step for the owning repos.

## Affected users and systems

`factory-gitops` (cfactory, tfactory, aifactory manifests, factory-namespace NetworkPolicy, `docs/model-gateway.md`, a script); the owner, who seeds secrets; Factory docs (`intent/spec/plan`).

## Constraints

- Argo CD syncs `factory-gitops` live: every change must be inert until the keys exist. No secret value in git, no token minted, printed or read from `/run/agenix`.
- Do not point manifests at images that lack the flags (checked above: they do carry them).
- No live-cluster writes; read-only `kubectl get` only.
- Owner-only steps stay owner steps: creating the Secret, seeding keys, the egress-proof call, the Plane B bench test, provider-key revocation.

## Open questions

None. Decisions (owner delegation 2026-11-17): (1) no CFactory release is cut, because the promotion to `main` is the release process (RELEASE.md) and it already happened; (2) the URL is an optional Secret key rather than a manifest literal, because a literal would switch the clients on with no token and fail the copilot closed; (3) the Job-egress rule is added now: it takes effect on sync, but only towards the gateway pods on 8080, and no client uses it until configured; (4) activation also needs a client rollout after seeding (env from a Secret is read at container start), and CFactory only routes `ollama`, `openai` and `openai_compatible` copilot providers (the default `claude` path is unchanged), so URL plus token alone does not move every request. Codex review of this intent confirmed the premises against the code.
