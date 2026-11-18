---
status: draft
issue: 1959
author: olafkfreund
---

# Intent: gateway quota, spend attribution, failover and telemetry

## Problem

The first-party model gateway (AIFactory `apps/model-gateway/gateway.py`, about 170
lines) resolves class routes and answers `X-Model-Route`, and nothing else. Epic
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

- Stdlib only, single file in the image; no new dependency.
- Default off: unchanged config means unchanged responses. Keep the CR/LF header
  strip (AIFactory#2114) and the no-redirect opener.
- Unit tests use fake upstreams on loopback; no provider keys, no network.
- Nothing is turned on in the cluster; no secrets seeded; no gitops change.
- No prompt or completion text is ever logged or exported.
- Acceptance boxes needing live proof (pod UID unchanged, live failover, keys
  removed) stay owner-gated and unticked.

## Open questions

None. Owner delegation 2026-11-18 takes the recommended option for each design choice
(recorded in the spec).
