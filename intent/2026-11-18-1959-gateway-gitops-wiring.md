---
status: approved
issue: 1959
author: olafkfreund
---

# Intent: wire the 3.17.0 gateway features into factory-gitops, all off

## Problem

AIFactory 3.17.0 (AIFactory#2138) gave the model gateway per-route quota, `/metrics` spend counters, ordered upstream
failover and an OTLP span exporter. All of it is driven by environment variables and the routes file. The live gateway
(`sha-24184c6-gateway`, 3.15.0) has none of it, and factory-gitops has no way to express it: the Deployment sets neither
the new env nor a place for a second upstream key, the routes generator emits only `{class: model}` strings, the
NetworkPolicies block in-cluster egress to OpenObserve, and nothing says how to read the counters. The 17:15 comment on
Factory#1959 also left one risk open: whether OpenObserve accepts the gateway's OTLP JSON. And quota and counters are
per pod (2 replicas), which changes what AC-3 can prove.

## Proposed outcome

- The gateway runs the 3.17.0 image and the manifests carry every new knob, with every feature explicitly off: metrics
  `off`, no OTLP endpoint, no quota, no second upstream (empty route policy). Features turn on only when the owner
  seeds `model-gateway-secrets` (OTLP, second key) or merges a route-policy or metrics PR. Argo CD auto-syncs, prunes
  and self-heals, so two live effects happen on merge and are accepted: the 2 pods roll once for the image bump, and
  one additive NetworkPolicy allowing egress to OpenObserve takes effect (it only matters once an OTLP endpoint is set).
- A route's quota and upstreams can be expressed in git and flow into the `model-routes` ConfigMap through the same
  generator as today; with the committed (empty) policy the rendered ConfigMap is byte-identical to today's.
- A cluster-free test fails if a later change turns any of it on by default.
- docs/model-gateway.md says how to read `/metrics`, how to turn OTLP on, what OpenObserve accepts, and that quota and
  counters are per pod.
- Factory#1959 gets a status comment; no acceptance box is ticked without live proof.

## Affected users and systems

factory-gitops `apps/model-gateway`, `scripts/gen-model-routes.py`, `scripts/test-gateway-wiring.sh`,
`docs/model-gateway.md`; namespace `gateway` (2 pods roll once on the image bump); OpenObserve (`observe`, ns `factory`)
as a future OTLP target. Argo CD syncs this repo live (auto-sync, prune, self-heal).

## Constraints

- Do not create or read secrets; the owner seeds `model-gateway-secrets`. Every new env is a literal off value or an
  `optional: true` secretKeyRef.
- Never touch the live cluster except read-only `kubectl get`.
- Out of scope, owner-only: Secret seeding, Plane B bench test, AC-2 record run, key rotation.
- No ServiceMonitor: the cluster has no Prometheus Operator CRDs, and an unknown kind would fail Argo and kubeconform.

## Open questions

None for approval. OpenObserve OTLP JSON acceptance stays marked unverified: the docs may record only what the
pinned OpenObserve version's source shows (v0.90.3), and a live ingest proof is an owner step once an endpoint is set.
