---
status: approved
issue: 1959
author: olafkfreund
---

# Intent: gateway quota, spend attribution, failover and telemetry

## Problem

The first-party model gateway (AIFactory `apps/model-gateway/gateway.py`, about 170
lines) authenticates callers, swaps the upstream key, resolves class routes and answers `X-Model-Route`, but has no quota, accounting, failover or telemetry. Epic
Factory#1959 (child of #1958) still needs, per the 2026-11-18 closeout comment: a
per-route quota, spend attribution per route and calling service, provider failover
in both directions with recovery, and telemetry normalised in the gateway. Without
them AC-3 (cost by route and caller, non-zero count) and AC-4 (failover and return)
cannot be proven, and one provider outage or one runaway caller stops or drains
every Factory service.

## Proposed outcome

With new config set, the gateway: answers 429 with `Retry-After` when a route is over
its request or token quota; counts tokens (buffered and streamed responses) and
prices them from the vendored catalog, exposing Prometheus counters labelled by route
and service on `/metrics`, with a self-test that fails on an empty result; tries an
ordered upstream list per route, fails over on 5xx, timeout or connection error (not
4xx), and returns to the primary after a cooldown; and emits OTLP spans carrying
`factory.genai.*` and `gen_ai.*` attributes. Prompt and completion logging stays off.
With none of the new config, behaviour is byte-for-byte today's.

## Affected users and systems

AIFactory `apps/model-gateway/gateway.py`, its tests and the gateway image stage of
the `Dockerfile`. Routes file format (`model-routes` ConfigMap, `GATEWAY_ROUTES_PATH`)
gains optional fields; factory-gitops is untouched (team gateway-gitops owns it).
Callers: CFactory, TFactory, AIFactory Jobs once the owner switches them on.

## Constraints

- Preserve today's behaviour: 503 unconfigured, 401, 400/413, `/healthz`, upstream error passthrough, 502 on unreachable.
- Stdlib only, single file in the image; no new dependency.
- Default off: unchanged config means unchanged responses. Keep the CR/LF header
  strip (AIFactory#2114) and the no-redirect opener.
- Unit tests use fake upstreams on loopback; no provider keys, no network.
- Nothing is turned on in the cluster; no secrets seeded; no gitops change.
- No prompt or completion text is ever logged or exported.
- Acceptance boxes needing live proof (pod UID unchanged, live failover, keys
  removed) stay owner-gated and unticked.

## Open questions

Resolved under owner delegation 2026-11-18 (Codex review of this draft, decisions recorded in the spec):
quota covers class routes only, concrete-model requests are metered but exempt;
service identity is the self-declared `X-Caller-Service` header (one shared client
token), so attribution is advisory and label cardinality is capped; token quota is
checked against tokens already consumed in a fixed window (concurrent in-flight
requests may overshoot) and missing usage is counted, not guessed; streaming means
parsing buffered SSE, true streaming stays out; failover accepts duplicate execution
and uses a per-upstream key from an env var name.
